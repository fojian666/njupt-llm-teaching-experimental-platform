"""知识库相关的后台任务。

函数本身可以直接调用（线程模式），装饰器只是让它们也能进 Celery 队列。
Celery 未安装时装饰器是空操作 —— 不让一个可选依赖卡住主流程。
"""
from typing import Optional

try:  # pragma: no cover —— Celery 属于可选增强
    from celery import shared_task
except Exception:  # noqa: BLE001
    def shared_task(*dargs, **dkwargs):
        def wrapper(func):
            func.delay = None  # type: ignore[attr-defined]
            return func

        if dargs and callable(dargs[0]):
            return wrapper(dargs[0])
        return wrapper


@shared_task(name="knowledge.index_document")
def index_document_task(knowledge_doc_id: int, reindex: bool = False) -> dict:
    """解析 + 切片 + 向量化一个知识条目。"""
    from apps.knowledge.models import KnowledgeDoc
    from apps.configs.services import resolve_embedding
    from rag.pipeline import index_document

    doc = (
        KnowledgeDoc.objects.filter(id=knowledge_doc_id)
        .select_related("knowledge_base", "data_resource")
        .first()
    )
    if doc is None:
        return {"ok": False, "message": f"知识条目 {knowledge_doc_id} 不存在"}

    try:
        provider = resolve_embedding(doc.knowledge_base)
    except Exception as exc:  # noqa: BLE001
        doc.parse_status = KnowledgeDoc.ParseStatus.FAILED
        doc.parse_message = str(exc)
        doc.save(update_fields=["parse_status", "parse_message"])
        return {"ok": False, "message": str(exc)}

    report = index_document(doc, provider, reindex=reindex)
    return report.as_dict()


@shared_task(name="knowledge.embed_document")
def embed_document_task(knowledge_doc_id: int) -> dict:
    """只补向量 —— 切片已经在了，用来单独重跑向量化（换模型 / 补中断）。"""
    from apps.knowledge.models import Chunk, KnowledgeDoc
    from apps.configs.services import resolve_embedding
    from django.utils import timezone
    from rag.store import missing_embedding_ids, save_embeddings

    doc = (
        KnowledgeDoc.objects.filter(id=knowledge_doc_id)
        .select_related("knowledge_base")
        .first()
    )
    if doc is None:
        return {"ok": False, "message": f"知识条目 {knowledge_doc_id} 不存在"}

    pending = missing_embedding_ids(doc.id)
    if not pending:
        return {"ok": True, "message": "所有切片都已有向量", "embedded": 0}

    try:
        provider = resolve_embedding(doc.knowledge_base)
        rows = list(Chunk.objects.filter(id__in=pending).order_by("seq").values_list("id", "content"))
        vectors = provider.embed_batched([c for _i, c in rows])
        written = save_embeddings([(cid, vec) for (cid, _c), vec in zip(rows, vectors)])
    except Exception as exc:  # noqa: BLE001
        doc.parse_status = KnowledgeDoc.ParseStatus.PARSING
        doc.parse_message = f"向量化未完成：{exc}（可再次重试）"
        doc.save(update_fields=["parse_status", "parse_message"])
        return {"ok": False, "message": str(exc)}

    remaining = len(missing_embedding_ids(doc.id))
    if remaining == 0:
        doc.parse_status = KnowledgeDoc.ParseStatus.SUCCESS
        doc.parse_message = f"向量化完成，共 {written} 条。"
        doc.parsed_at = timezone.now()
        doc.save(update_fields=["parse_status", "parse_message", "parsed_at"])
    return {"ok": True, "embedded": written, "remaining": remaining}


@shared_task(name="knowledge.parse_resource")
def parse_resource_task(resource_id: int) -> dict:
    """只做解析（不落向量库），给「数据分类管理」页的「解析」按钮用。"""
    from apps.datasets.models import DataResource
    from rag.parsers import ParseError
    from rag.pipeline import mark_resource, parse_resource_data_resource

    res: Optional[DataResource] = DataResource.objects.filter(id=resource_id).first()
    if res is None:
        return {"ok": False, "message": f"数据资源 {resource_id} 不存在"}

    mark_resource(res, "parsing", "正在解析…")
    try:
        parsed = parse_resource_data_resource(res)
    except ParseError as exc:
        mark_resource(res, "failed", str(exc))
        return {"ok": False, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        mark_resource(res, "failed", f"解析失败：{exc}")
        return {"ok": False, "message": str(exc)}

    # parse_resource_data_resource 里已经把状态写成 success 了，这里只补时间戳
    mark_resource(res, "success", res.parse_message, touch_parsed_at=True)
    return {"ok": True, "char_count": parsed.char_count, "message": res.parse_message}
