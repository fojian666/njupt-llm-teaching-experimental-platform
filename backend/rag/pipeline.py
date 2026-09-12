"""入库流水线：解析 → 切片 → 向量化 → 落库。

一个知识条目从「上传」变成「可检索」要走完这里面的四步，任何一步失败都要把
**具体原因**写回 `parse_message`（前端的「解析信息」列直接展示它），
而不是丢一个堆栈给用户。

关键设计：**断点续跑**。向量化是最慢也最容易失败的一步（网络 + 限流），
所以切片先落库、向量分批补写，中途断了重跑只补 `embedding IS NULL` 的那些切片。
"""
import time
from dataclasses import dataclass, field

from .parsers import ParseError, parse_file
from .splitter import split
from .store import missing_embedding_ids, save_embeddings


@dataclass
class IndexReport:
    ok: bool = False
    chunk_count: int = 0
    embedded_count: int = 0
    char_count: int = 0
    elapsed_ms: int = 0
    message: str = ""
    meta: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "chunk_count": self.chunk_count,
            "embedded_count": self.embedded_count,
            "char_count": self.char_count,
            "elapsed_ms": self.elapsed_ms,
            "message": self.message,
            "meta": self.meta,
        }


def _progress_printer(done: int, total: int) -> None:
    print(f"[index] 向量化 {done}/{total}", flush=True)


def mark_resource(resource, status: str, message: str, *, touch_parsed_at: bool = False) -> None:
    """同步数据资源的解析状态。

    数据管理页和知识管理页展示的是同一份文件，状态必须一致 ——
    知识库里明明已经切片入库、数据列表却还写着「未解析」，用户只会以为系统坏了。
    """
    from django.utils import timezone

    resource.parse_status = status
    resource.parse_message = (message or "")[:2000]
    fields = ["parse_status", "parse_message"]
    if touch_parsed_at:
        resource.parsed_at = timezone.now()
        fields.append("parsed_at")
    resource.save(update_fields=fields)


def parse_resource_data_resource(resource, *, save: bool = True):
    """解析数据资源的源文件，返回 ParseResult。

    没有源文件时（例如 OCR 结果直接入库）退化为解析 `content_text`，
    这样「导入文本」和「上传文件」两条路走同一套下游逻辑。
    """
    from .parsers.plain import parse_text

    if resource.file:
        result = parse_file(resource.file.path, resource.file_format or None)
    elif (resource.content_text or "").strip():
        result = parse_text(resource.content_text, resource.file_format or "txt")
        result.meta["source"] = "content_text"
    else:
        raise ParseError("这条数据既没有源文件，也没有可解析的正文。")

    if result.meta.get("needs_ocr"):
        raise ParseError(result.meta.get("ocr_hint") or "该文件是扫描件，需要先做 OCR。")

    if not result.blocks:
        raise ParseError("没有解析出任何正文内容，请确认文件不是空文档或纯图片。")

    if save:
        resource.content_text = result.text
        resource.char_count = result.char_count
        resource.parse_status = "success"
        resource.parse_message = f"解析成功：{result.char_count} 字，{len(result.blocks)} 个结构块。"
        resource.save(
            update_fields=[
                "content_text", "char_count", "parse_status", "parse_message", "updated_at",
            ]
        )
    return result


def index_document(
    knowledge_doc,
    embedding_provider,
    *,
    reindex: bool = False,
    progress=None,
) -> IndexReport:
    """把一个知识条目完整灌进向量库。

    reindex=True 时清掉旧切片重来；否则只补没算向量的切片（断点续跑）。
    """
    from django.utils import timezone

    from apps.knowledge.models import Chunk, KnowledgeDoc

    started = time.monotonic()
    kb = knowledge_doc.knowledge_base
    resource = knowledge_doc.data_resource
    report = IndexReport()

    knowledge_doc.parse_status = KnowledgeDoc.ParseStatus.PARSING
    knowledge_doc.parse_message = "正在解析源文件…"
    knowledge_doc.save(update_fields=["parse_status", "parse_message"])

    def fail(message: str) -> IndexReport:
        """解析阶段失败：条目和数据资源一起标失败，两处口径保持一致。"""
        report.message = message
        knowledge_doc.parse_status = KnowledgeDoc.ParseStatus.FAILED
        knowledge_doc.parse_message = message
        knowledge_doc.save(update_fields=["parse_status", "parse_message"])
        mark_resource(resource, "failed", message)
        return report

    # ---- 1. 解析 ----
    try:
        parsed = parse_resource_data_resource(resource)
    except ParseError as exc:
        return fail(str(exc))
    except Exception as exc:  # noqa: BLE001
        return fail(f"解析失败：{exc}")

    report.char_count = parsed.char_count
    report.meta.update({k: v for k, v in parsed.meta.items() if isinstance(v, (int, str, float, bool))})

    # ---- 2. 切片 ----
    chunks = split(
        parsed.blocks,
        chunk_size=kb.chunk_size,
        overlap=kb.chunk_overlap,
        strategy=kb.chunk_strategy,
    )
    if not chunks:
        return fail("解析成功但没有切出任何切片，请检查切片长度设置。")

    if reindex:
        Chunk.objects.filter(knowledge_doc=knowledge_doc).delete()

    # 已有切片就不重建，直接进入补向量阶段 —— 这就是断点续跑
    existing = Chunk.objects.filter(knowledge_doc=knowledge_doc).count()
    if existing == 0:
        Chunk.objects.bulk_create(
            [
                Chunk(
                    knowledge_doc=knowledge_doc,
                    seq=c.seq,
                    content=c.content,
                    chapter_path=c.chapter_path[:512],
                    char_count=c.char_count,
                )
                for c in chunks
            ],
            batch_size=200,
        )
        existing = Chunk.objects.filter(knowledge_doc=knowledge_doc).count()

    report.chunk_count = existing

    # ---- 3. 向量化（只补缺失） ----
    pending = missing_embedding_ids(knowledge_doc.id)
    if pending:
        knowledge_doc.parse_message = f"切片完成（{existing} 条），正在生成向量…"
        knowledge_doc.save(update_fields=["parse_message"])
        try:
            pending_chunks = list(
                Chunk.objects.filter(id__in=pending).order_by("seq").values_list("id", "content")
            )
            vectors = embedding_provider.embed_batched(
                [c for _cid, c in pending_chunks],
                progress=progress or _progress_printer,
            )
            report.embedded_count = save_embeddings(
                [(cid, vec) for (cid, _c), vec in zip(pending_chunks, vectors)]
            )
        except Exception as exc:  # noqa: BLE001
            # 切片已经落库了，向量可以稍后重试，所以标成「解析中」而不是「失败」
            report.message = f"切片已生成，但向量化未完成：{exc}"
            knowledge_doc.parse_status = KnowledgeDoc.ParseStatus.PARSING
            knowledge_doc.parse_message = report.message + "（可点「重新解析」续跑）"
            knowledge_doc.chunk_count = report.chunk_count
            knowledge_doc.save(update_fields=["parse_status", "parse_message", "chunk_count"])
            report.elapsed_ms = int((time.monotonic() - started) * 1000)
            return report

    # ---- 4. 收尾 ----
    report.ok = True
    report.elapsed_ms = int((time.monotonic() - started) * 1000)
    report.message = (
        f"解析成功：{report.char_count} 字，{report.chunk_count} 个切片，"
        f"向量 {report.embedded_count} 条，耗时 {report.elapsed_ms / 1000:.1f} 秒。"
    )
    knowledge_doc.parse_status = KnowledgeDoc.ParseStatus.SUCCESS
    knowledge_doc.parse_message = report.message
    knowledge_doc.chunk_count = report.chunk_count
    knowledge_doc.parsed_at = timezone.now()
    knowledge_doc.save(
        update_fields=["parse_status", "parse_message", "chunk_count", "parsed_at"]
    )
    return report


def index_many(knowledge_docs, embedding_provider, *, reindex: bool = False) -> list[IndexReport]:
    """批量入库。单个失败不影响后面的 —— 演示里一次导入多份资料很常见。"""
    out: list[IndexReport] = []
    for doc in knowledge_docs:
        try:
            out.append(index_document(doc, embedding_provider, reindex=reindex))
        except Exception as exc:  # noqa: BLE001
            report = IndexReport(message=f"入库异常：{exc}")
            out.append(report)
    return out
