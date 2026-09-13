"""知识管理接口：知识库 / 知识条目 / 切片 / 检索调试。

对应演示视频的「数据管理 → 知识管理」：
知识库详情（解析状态、是否有效）、导入知识、切片列表、切片详情（文件名 + 章节路径 + 正文）。
"""
from typing import Annotated, List, Optional

from django.db.models import Count, Q
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import StringConstraints

from apps.common.api import current_user, log_action, paginate, require_manager
from apps.common.tasks import run_task
from apps.knowledge.tasks import embed_document_task, index_document_task

from .models import Chunk, KnowledgeBase, KnowledgeDoc

router = Router(tags=["知识管理"])


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------
class KBIn(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    code: str = ""
    description: str = ""
    embedding_model_id: Optional[int] = None
    chunk_size: int = 500
    chunk_overlap: int = 80
    chunk_strategy: str = "heading"
    is_active: bool = True


class KBOut(Schema):
    id: int
    name: str
    code: str
    description: str
    embedding_model_id: Optional[int] = None
    embedding_model_name: str
    chunk_size: int
    chunk_overlap: int
    chunk_strategy: str
    is_active: bool
    doc_count: int
    chunk_count: int
    created_at: str
    # 改切片参数 / 换向量模型后提示需要重建，平时为空
    warning: str = ""


class DocOut(Schema):
    id: int
    knowledge_base_id: int
    resource_id: int
    name: str
    file_format: str
    category_path: str
    tags: List[str]
    parse_status: str
    parse_status_label: str
    parse_message: str
    is_active: bool
    chunk_count: int
    char_count: int
    parsed_at: Optional[str] = None
    created_at: str


class ImportIn(Schema):
    resource_ids: List[int]


class ChunkOut(Schema):
    id: int
    seq: int
    chapter_path: str
    content: str
    char_count: int
    has_embedding: bool


class SearchIn(Schema):
    query: str
    knowledge_base_ids: List[int] = []
    top_k: int = 5
    alpha: float = 0.7
    use_keyword: bool = True
    score_threshold: float = 0.0


# --------------------------------------------------------------------------
# 知识库
# --------------------------------------------------------------------------
def _kb_out(kb: KnowledgeBase) -> dict:
    return {
        "id": kb.id,
        "name": kb.name,
        "code": kb.code,
        "description": kb.description,
        "embedding_model_id": kb.embedding_model_id,
        "embedding_model_name": kb.embedding_model.name if kb.embedding_model else "（按配置中心默认）",
        "chunk_size": kb.chunk_size,
        "chunk_overlap": kb.chunk_overlap,
        "chunk_strategy": kb.chunk_strategy,
        "is_active": kb.is_active,
        "doc_count": kb.doc_count,
        "chunk_count": kb.chunk_count,
        "created_at": kb.created_at.strftime("%Y-%m-%d %H:%M"),
    }


@router.get("/bases", response=List[KBOut])
def list_bases(request):
    current_user(request)
    return [_kb_out(kb) for kb in KnowledgeBase.objects.select_related("embedding_model").all()]


@router.post("/bases", response=KBOut)
def create_base(request, payload: KBIn):
    user = require_manager(request)
    from apps.configs.models import ModelConfig

    code = payload.code or f"kb-{int(timezone.now().timestamp())}"
    if KnowledgeBase.objects.filter(code=code).exists():
        raise HttpError(400, f"知识库标识 {code} 已存在")

    kb = KnowledgeBase.objects.create(
        name=payload.name,
        code=code,
        description=payload.description,
        embedding_model=ModelConfig.objects.filter(id=payload.embedding_model_id).first(),
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
        chunk_strategy=payload.chunk_strategy,
        is_active=payload.is_active,
        created_by=user,
    )
    log_action(request, "create_kb", "KnowledgeBase", kb.id, name=kb.name)
    return _kb_out(kb)


@router.patch("/bases/{kb_id}", response=KBOut)
def update_base(request, kb_id: int, payload: KBIn):
    require_manager(request)
    from apps.configs.models import ModelConfig

    kb = KnowledgeBase.objects.filter(id=kb_id).first()
    if kb is None:
        raise HttpError(404, "知识库不存在")

    # 改切片参数或换向量模型都会让已有切片失效，所以必须提示重建
    needs_reindex = (
        payload.chunk_size != kb.chunk_size
        or payload.chunk_overlap != kb.chunk_overlap
        or payload.chunk_strategy != kb.chunk_strategy
    )

    kb.name = payload.name
    kb.description = payload.description
    kb.embedding_model = ModelConfig.objects.filter(id=payload.embedding_model_id).first()
    kb.chunk_size = payload.chunk_size
    kb.chunk_overlap = payload.chunk_overlap
    kb.chunk_strategy = payload.chunk_strategy
    kb.is_active = payload.is_active
    kb.save()
    log_action(request, "update_kb", "KnowledgeBase", kb.id, name=kb.name, needs_reindex=needs_reindex)

    data = _kb_out(kb)
    if needs_reindex and kb.chunk_count:
        data["warning"] = "切片参数已变更，请对知识库内的数据重新解析以生效"
    return data


@router.delete("/bases/{kb_id}")
def delete_base(request, kb_id: int):
    require_manager(request)
    kb = KnowledgeBase.objects.filter(id=kb_id).first()
    if kb is None:
        raise HttpError(404, "知识库不存在")
    if kb.agents.exists():
        raise HttpError(400, "该知识库已被智能体引用，请先在智能体中解除关联")
    name = kb.name
    kb.delete()
    log_action(request, "delete_kb", "KnowledgeBase", kb_id, name=name)
    return {"ok": True, "message": f"已删除知识库 {name}"}


# --------------------------------------------------------------------------
# 知识条目
# --------------------------------------------------------------------------
def _doc_out(doc: KnowledgeDoc) -> dict:
    res = doc.data_resource
    return {
        "id": doc.id,
        "knowledge_base_id": doc.knowledge_base_id,
        "resource_id": res.id,
        "name": res.name,
        "file_format": res.file_format or "-",
        "category_path": res.category.full_path if res.category else "未分类",
        "tags": [t.name for t in res.tags.all()],
        "parse_status": doc.parse_status,
        "parse_status_label": doc.get_parse_status_display(),
        "parse_message": doc.parse_message,
        "is_active": doc.is_active,
        "chunk_count": doc.chunk_count,
        "char_count": res.char_count,
        "parsed_at": doc.parsed_at.strftime("%Y-%m-%d %H:%M") if doc.parsed_at else None,
        "created_at": doc.created_at.strftime("%Y-%m-%d %H:%M"),
    }


@router.get("/bases/{kb_id}/docs")
def list_docs(request, kb_id: int, status: str = "", keyword: str = "", page: int = 1, page_size: int = 20):
    current_user(request)
    if not KnowledgeBase.objects.filter(id=kb_id).exists():
        raise HttpError(404, "知识库不存在")

    qs = (
        KnowledgeDoc.objects.filter(knowledge_base_id=kb_id)
        .select_related("data_resource", "data_resource__category")
        .prefetch_related("data_resource__tags")
    )
    if status:
        qs = qs.filter(parse_status=status)
    if keyword:
        qs = qs.filter(data_resource__name__icontains=keyword)

    result = paginate(qs.order_by("-created_at"), page, page_size)
    result["items"] = [_doc_out(d) for d in result["items"]]
    return result


@router.post("/bases/{kb_id}/import")
def import_resources(request, kb_id: int, payload: ImportIn):
    """把「数据管理」里的数据导入知识库并开始解析。已在库里的会跳过。"""
    require_manager(request)
    from apps.datasets.models import DataResource

    kb = KnowledgeBase.objects.filter(id=kb_id).first()
    if kb is None:
        raise HttpError(404, "知识库不存在")

    created, skipped = [], []
    for res in DataResource.objects.filter(id__in=payload.resource_ids, is_deleted=False):
        doc, is_new = KnowledgeDoc.objects.get_or_create(
            knowledge_base=kb, data_resource=res, defaults={"parse_status": KnowledgeDoc.ParseStatus.PENDING}
        )
        if is_new:
            created.append(doc)
        else:
            skipped.append(res.name)

    for doc in created:
        run_task(index_document_task, doc.id, True)

    log_action(request, "import_to_kb", "KnowledgeBase", kb.id, count=len(created))
    return {
        "ok": True,
        "message": f"已导入 {len(created)} 条数据"
        + (f"，{len(skipped)} 条此前已在库中" if skipped else ""),
        "imported": len(created),
        "skipped": skipped,
        "doc_ids": [d.id for d in created],
    }


@router.post("/docs/{doc_id}/reparse")
def reparse_doc(request, doc_id: int, reindex: bool = True):
    """重新解析。reindex=True 会清掉旧切片重建（换了切片参数时用）。"""
    require_manager(request)
    doc = KnowledgeDoc.objects.filter(id=doc_id).first()
    if doc is None:
        raise HttpError(404, "知识条目不存在")

    doc.parse_status = KnowledgeDoc.ParseStatus.PARSING
    doc.parse_message = "已排队，正在重新解析…"
    doc.save(update_fields=["parse_status", "parse_message"])

    mode = run_task(index_document_task, doc.id, reindex)
    log_action(request, "reparse_doc", "KnowledgeDoc", doc.id, reindex=reindex, mode=mode)
    return {"ok": True, "message": "已开始重新解析", "mode": mode}


@router.post("/docs/{doc_id}/embed")
def embed_doc(request, doc_id: int):
    """只补向量：中断后续跑，或换了向量模型后重算。"""
    require_manager(request)
    doc = KnowledgeDoc.objects.filter(id=doc_id).first()
    if doc is None:
        raise HttpError(404, "知识条目不存在")

    mode = run_task(embed_document_task, doc.id)
    log_action(request, "embed_doc", "KnowledgeDoc", doc.id, mode=mode)
    return {"ok": True, "message": "已开始生成向量", "mode": mode}


@router.post("/docs/{doc_id}/toggle")
def toggle_doc(request, doc_id: int):
    """切换「是否有效」。无效条目不参与检索，但切片保留。"""
    require_manager(request)
    doc = KnowledgeDoc.objects.filter(id=doc_id).first()
    if doc is None:
        raise HttpError(404, "知识条目不存在")
    doc.is_active = not doc.is_active
    doc.save(update_fields=["is_active"])
    log_action(request, "toggle_doc", "KnowledgeDoc", doc.id, is_active=doc.is_active)
    return {"ok": True, "is_active": doc.is_active, "message": "已启用" if doc.is_active else "已停用"}


@router.delete("/docs/{doc_id}")
def delete_doc(request, doc_id: int):
    require_manager(request)
    doc = KnowledgeDoc.objects.filter(id=doc_id).select_related("data_resource").first()
    if doc is None:
        raise HttpError(404, "知识条目不存在")
    name = doc.data_resource.name
    doc.delete()  # 切片随 KnowledgeDoc 级联删除
    log_action(request, "delete_doc", "KnowledgeDoc", doc_id, name=name)
    return {"ok": True, "message": f"已从知识库移除 {name}"}


# --------------------------------------------------------------------------
# 切片
# --------------------------------------------------------------------------
@router.get("/docs/{doc_id}/chunks")
def list_chunks(request, doc_id: int, chapter: str = "", keyword: str = "", page: int = 1, page_size: int = 20):
    """切片列表。切片详情弹窗展示的「文件名 + 章节路径 + 正文」就是这里的数据。"""
    current_user(request)
    if not KnowledgeDoc.objects.filter(id=doc_id).exists():
        raise HttpError(404, "知识条目不存在")

    qs = Chunk.objects.filter(knowledge_doc_id=doc_id)
    if chapter:
        qs = qs.filter(chapter_path__startswith=chapter)
    if keyword:
        qs = qs.filter(content__icontains=keyword)

    result = paginate(qs.order_by("seq"), page, page_size)
    result["items"] = [
        {
            "id": c.id,
            "seq": c.seq,
            "chapter_path": c.chapter_path,
            "content": c.content,
            "char_count": c.char_count,
            "has_embedding": c.embedding is not None,
        }
        for c in result["items"]
    ]
    return result


@router.get("/chunks/{chunk_id}", response=ChunkOut)
def get_chunk(request, chunk_id: int):
    current_user(request)
    c = (
        Chunk.objects.filter(id=chunk_id)
        .select_related("knowledge_doc", "knowledge_doc__data_resource")
        .first()
    )
    if c is None:
        raise HttpError(404, "切片不存在")
    return {
        "id": c.id,
        "seq": c.seq,
        "chapter_path": c.chapter_path,
        "content": c.content,
        "char_count": c.char_count,
        "has_embedding": c.embedding is not None,
    }


@router.get("/docs/{doc_id}/outline")
def doc_outline(request, doc_id: int):
    """按章节聚合切片，给「数据详情」页做章节导航。"""
    current_user(request)
    rows = (
        Chunk.objects.filter(knowledge_doc_id=doc_id)
        .values("chapter_path")
        .annotate(n=Count("id"))
        .order_by("chapter_path")
    )
    return {
        "items": [
            {"chapter_path": r["chapter_path"] or "（无章节）", "chunk_count": r["n"]} for r in rows
        ]
    }


# --------------------------------------------------------------------------
# 检索调试
# --------------------------------------------------------------------------
@router.post("/search")
def search(request, payload: SearchIn):
    """检索调试接口。

    参数直接暴露给使用者（alpha / use_keyword / top_k），
    这样调参时能立刻看出「向量分与关键词分各贡献了多少」，不用靠猜。
    """
    current_user(request)
    from apps.configs.services import resolve_embedding
    from rag.retriever import RetrieveOptions, Retriever, citations_from_hits

    try:
        provider = resolve_embedding()
    except Exception as exc:  # noqa: BLE001
        raise HttpError(400, str(exc))

    retriever = Retriever(provider)
    result = retriever.retrieve(
        payload.query,
        RetrieveOptions(
            top_k=payload.top_k,
            alpha=payload.alpha,
            use_keyword=payload.use_keyword,
            score_threshold=payload.score_threshold,
            knowledge_base_ids=payload.knowledge_base_ids or None,
        ),
    )
    return {
        "query": payload.query,
        "vector_count": result.vector_count,
        "lexical_count": result.lexical_count,
        "note": result.note,
        "items": citations_from_hits(result.hits),
    }


@router.get("/stats")
def knowledge_stats(request):
    current_user(request)
    return {
        "bases": KnowledgeBase.objects.count(),
        "docs": KnowledgeDoc.objects.count(),
        "chunks": Chunk.objects.count(),
        "embedded_chunks": Chunk.objects.exclude(embedding=None).count(),
        "active_docs": KnowledgeDoc.objects.filter(is_active=True).count(),
        "by_status": {
            row["parse_status"]: row["n"]
            for row in KnowledgeDoc.objects.values("parse_status").annotate(n=Count("id"))
        },
    }
