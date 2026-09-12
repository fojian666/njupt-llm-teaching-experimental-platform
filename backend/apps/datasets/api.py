"""数据管理接口：分类树 / 标签 / 数据资源。

对应演示视频的「数据管理 → 数据分类管理」：
左侧分类树、右侧数据列表、上传、解析、打标、删除。
"""
from typing import List, Optional

from django.db.models import Count, Q
from ninja import File, Form, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.common.api import current_user, log_action, require_manager
from apps.common.tasks import run_task
from apps.knowledge.tasks import parse_resource_task
from rag.parsers import detect_format, supported_formats

from .models import DataCategory, DataResource, DataTag

router = Router(tags=["数据管理"])


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------
class CategoryIn(Schema):
    name: str
    code: str = ""
    parent_id: Optional[int] = None
    sort: int = 0
    remark: str = ""


class CategoryOut(Schema):
    id: int
    name: str
    code: str
    parent_id: Optional[int] = None
    sort: int
    remark: str
    full_path: str
    resource_count: int
    children: List["CategoryOut"] = []


CategoryOut.model_rebuild()


class TagIn(Schema):
    name: str
    color: str = "#378ADD"


class TagOut(Schema):
    id: int
    name: str
    color: str
    resource_count: int


class ResourceOut(Schema):
    id: int
    name: str
    category_id: Optional[int] = None
    category_path: str
    upload_method: str
    upload_method_label: str
    file_format: str
    file_size: int
    file_size_label: str
    tags: List[str]
    parse_status: str
    parse_status_label: str
    parse_message: str
    char_count: int
    source_note: str
    created_at: str
    updated_at: str


class ResourceDetailOut(ResourceOut):
    content_preview: str = ""
    in_knowledge_bases: List[str] = []


class ResourceUpdateIn(Schema):
    name: Optional[str] = None
    category_id: Optional[int] = None
    tags: Optional[List[str]] = None
    source_note: Optional[str] = None


# --------------------------------------------------------------------------
# 分类树
# --------------------------------------------------------------------------
@router.get("/categories", response=List[CategoryOut])
def list_categories(request):
    """返回整棵树。分类数量在几十到几百量级，一次给全比按需展开简单得多。"""
    current_user(request)
    counts = {
        row["category_id"]: row["n"]
        for row in DataResource.objects.filter(is_deleted=False, category__isnull=False)
        .values("category_id")
        .annotate(n=Count("id"))
    }

    nodes: dict[int, dict] = {}
    for c in DataCategory.objects.all():
        nodes[c.id] = {
            "id": c.id,
            "name": c.name,
            "code": c.code,
            "parent_id": c.parent_id,
            "sort": c.sort,
            "remark": c.remark,
            "full_path": c.full_path,
            "resource_count": counts.get(c.id, 0),
            "children": [],
        }

    roots: list[dict] = []
    for node in nodes.values():
        parent = nodes.get(node["parent_id"]) if node["parent_id"] else None
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)
    return roots


@router.post("/categories", response=CategoryOut)
def create_category(request, payload: CategoryIn):
    require_manager(request)
    parent = None
    if payload.parent_id:
        parent = DataCategory.objects.filter(id=payload.parent_id).first()
        if parent is None:
            raise HttpError(404, "上级分类不存在")
    if DataCategory.objects.filter(parent=parent, name=payload.name).exists():
        raise HttpError(400, "同级下已有同名分类")

    c = DataCategory.objects.create(
        name=payload.name, code=payload.code, parent=parent, sort=payload.sort, remark=payload.remark
    )
    log_action(request, "create_category", "DataCategory", c.id, name=c.name)
    return {
        "id": c.id, "name": c.name, "code": c.code, "parent_id": c.parent_id,
        "sort": c.sort, "remark": c.remark, "full_path": c.full_path,
        "resource_count": 0, "children": [],
    }


@router.patch("/categories/{category_id}", response=CategoryOut)
def update_category(request, category_id: int, payload: CategoryIn):
    require_manager(request)
    c = DataCategory.objects.filter(id=category_id).first()
    if c is None:
        raise HttpError(404, "分类不存在")

    # 不能把节点挂到自己或自己的后代下面，否则分类树会出现环
    if payload.parent_id:
        if payload.parent_id == c.id:
            raise HttpError(400, "不能把分类挂到自己下面")
        if payload.parent_id in c.descendant_ids(include_self=False):
            raise HttpError(400, "不能把分类挂到自己的子分类下面")
        parent = DataCategory.objects.filter(id=payload.parent_id).first()
        if parent is None:
            raise HttpError(404, "上级分类不存在")
        c.parent = parent

    c.name = payload.name
    c.code = payload.code
    c.sort = payload.sort
    c.remark = payload.remark
    c.save()
    log_action(request, "update_category", "DataCategory", c.id, name=c.name)
    return {
        "id": c.id, "name": c.name, "code": c.code, "parent_id": c.parent_id,
        "sort": c.sort, "remark": c.remark, "full_path": c.full_path,
        "resource_count": c.resources.filter(is_deleted=False).count(), "children": [],
    }


@router.delete("/categories/{category_id}")
def delete_category(request, category_id: int):
    require_manager(request)
    c = DataCategory.objects.filter(id=category_id).first()
    if c is None:
        raise HttpError(404, "分类不存在")
    if c.children.exists():
        raise HttpError(400, "请先删除子分类")
    if c.resources.filter(is_deleted=False).exists():
        raise HttpError(400, "该分类下还有数据，请先移走或删除")
    name = c.name
    c.delete()
    log_action(request, "delete_category", "DataCategory", category_id, name=name)
    return {"ok": True, "message": f"已删除分类 {name}"}


# --------------------------------------------------------------------------
# 标签
# --------------------------------------------------------------------------
@router.get("/tags", response=List[TagOut])
def list_tags(request):
    current_user(request)
    return [
        {"id": t.id, "name": t.name, "color": t.color, "resource_count": t.resources.filter(is_deleted=False).count()}
        for t in DataTag.objects.all()
    ]


@router.post("/tags", response=TagOut)
def create_tag(request, payload: TagIn):
    require_manager(request)
    tag, created = DataTag.objects.get_or_create(name=payload.name, defaults={"color": payload.color})
    if not created and payload.color != tag.color:
        tag.color = payload.color
        tag.save(update_fields=["color"])
    return {"id": tag.id, "name": tag.name, "color": tag.color, "resource_count": 0}


@router.delete("/tags/{tag_id}")
def delete_tag(request, tag_id: int):
    require_manager(request)
    tag = DataTag.objects.filter(id=tag_id).first()
    if tag is None:
        raise HttpError(404, "标签不存在")
    name = tag.name
    tag.delete()
    log_action(request, "delete_tag", "DataTag", tag_id, name=name)
    return {"ok": True, "message": f"已删除标签 {name}"}


# --------------------------------------------------------------------------
# 数据资源
# --------------------------------------------------------------------------
def _size_label(size: int) -> str:
    if not size:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size / 1:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _resource_out(r: DataResource) -> dict:
    from apps.knowledge.models import KnowledgeDoc

    return {
        "id": r.id,
        "name": r.name,
        "category_id": r.category_id,
        "category_path": r.category.full_path if r.category else "未分类",
        "upload_method": r.upload_method,
        "upload_method_label": r.get_upload_method_display(),
        "file_format": r.file_format or "-",
        "file_size": r.file_size,
        "file_size_label": _size_label(r.file_size),
        "tags": [t.name for t in r.tags.all()],
        "parse_status": r.parse_status,
        "parse_status_label": r.get_parse_status_display(),
        "parse_message": r.parse_message,
        "char_count": r.char_count,
        "source_note": r.source_note,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
        "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M"),
        "_kb_names": list(
            KnowledgeDoc.objects.filter(data_resource=r)
            .values_list("knowledge_base__name", flat=True)
        ),
    }


def _strip_internal(data: dict) -> dict:
    data.pop("_kb_names", None)
    return data


@router.get("/resources")
def list_resources(
    request,
    category_id: int = 0,
    include_children: bool = True,
    tag: str = "",
    status: str = "",
    keyword: str = "",
    method: str = "",
    page: int = 1,
    page_size: int = 20,
):
    current_user(request)
    from apps.common.api import paginate

    qs = DataResource.objects.filter(is_deleted=False).select_related("category").prefetch_related("tags")

    if category_id:
        if include_children:
            cat = DataCategory.objects.filter(id=category_id).first()
            ids = cat.descendant_ids() if cat else [category_id]
        else:
            ids = [category_id]
        qs = qs.filter(category_id__in=ids)
    if tag:
        qs = qs.filter(tags__name=tag)
    if status:
        qs = qs.filter(parse_status=status)
    if method:
        qs = qs.filter(upload_method=method)
    if keyword:
        qs = qs.filter(Q(name__icontains=keyword) | Q(source_note__icontains=keyword))

    result = paginate(qs.order_by("-created_at"), page, page_size)
    rows = []
    for r in result["items"]:
        data = _resource_out(r)
        data["in_knowledge_bases"] = data.pop("_kb_names", [])
        rows.append(data)
    result["items"] = rows
    return result


@router.get("/resources/{resource_id}", response=ResourceDetailOut)
def get_resource(request, resource_id: int):
    current_user(request)
    r = (
        DataResource.objects.filter(id=resource_id, is_deleted=False)
        .select_related("category")
        .prefetch_related("tags")
        .first()
    )
    if r is None:
        raise HttpError(404, "数据不存在")
    data = _resource_out(r)
    data["in_knowledge_bases"] = data.pop("_kb_names", [])
    data["content_preview"] = (r.content_text or "")[:20000]
    return data


@router.post("/resources/upload", response=ResourceDetailOut)
def upload_resource(
    request,
    file: File[UploadedFile],
    name: str = Form(""),
    category_id: int = Form(0),
    tags: str = Form(""),
    source_note: str = Form(""),
    upload_method: str = Form("upload"),
):
    """上传一个数据文件。

    `tags` 是逗号分隔的字符串而不是数组 —— multipart 表单里传数组各家前端写法不一，
    用字符串最省事，后端拆开即可。
    """
    user = require_manager(request)

    fmt = detect_format(file.name)
    if not fmt:
        raise HttpError(
            400,
            f"不支持的文件类型：{file.name}。当前支持 {', '.join(supported_formats())}",
        )
    max_bytes = 200 * 1024 * 1024
    if file.size and file.size > max_bytes:
        raise HttpError(400, f"文件过大（{_size_label(file.size)}），上限 200 MB")

    category = DataCategory.objects.filter(id=category_id).first() if category_id else None
    resource = DataResource.objects.create(
        name=(name or file.name).strip(),
        category=category,
        upload_method=upload_method if upload_method in dict(DataResource.UploadMethod.choices) else "upload",
        file=file,
        file_format=fmt,
        file_size=file.size or 0,
        source_note=source_note,
        parse_status=DataResource.ParseStatus.NOT_PARSED,
        created_by=user,
    )
    for tag_name in [t.strip() for t in (tags or "").split(",") if t.strip()]:
        tag_obj, _ = DataTag.objects.get_or_create(name=tag_name)
        resource.tags.add(tag_obj)

    log_action(request, "upload_resource", "DataResource", resource.id, name=resource.name, fmt=fmt)
    data = _resource_out(resource)
    data["in_knowledge_bases"] = data.pop("_kb_names", [])
    data["content_preview"] = ""
    return data


@router.patch("/resources/{resource_id}", response=ResourceDetailOut)
def update_resource(request, resource_id: int, payload: ResourceUpdateIn):
    require_manager(request)
    r = DataResource.objects.filter(id=resource_id, is_deleted=False).first()
    if r is None:
        raise HttpError(404, "数据不存在")

    if payload.name is not None:
        r.name = payload.name.strip() or r.name
    if payload.category_id is not None:
        r.category = DataCategory.objects.filter(id=payload.category_id).first() if payload.category_id else None
    if payload.source_note is not None:
        r.source_note = payload.source_note
    r.save()

    if payload.tags is not None:
        r.tags.clear()
        for tag_name in [t.strip() for t in payload.tags if t.strip()]:
            tag_obj, _ = DataTag.objects.get_or_create(name=tag_name)
            r.tags.add(tag_obj)

    log_action(request, "update_resource", "DataResource", r.id, name=r.name)
    data = _resource_out(r)
    data["in_knowledge_bases"] = data.pop("_kb_names", [])
    data["content_preview"] = (r.content_text or "")[:20000]
    return data


@router.post("/resources/{resource_id}/parse")
def parse_resource(request, resource_id: int):
    """解析源文件（只解析，不建向量库）。"""
    require_manager(request)
    r = DataResource.objects.filter(id=resource_id, is_deleted=False).first()
    if r is None:
        raise HttpError(404, "数据不存在")
    if not r.file and not r.content_text:
        raise HttpError(400, "这条数据没有源文件，无法解析")

    mode = run_task(parse_resource_task, r.id)
    log_action(request, "parse_resource", "DataResource", r.id, name=r.name, mode=mode)
    return {"ok": True, "message": "已开始解析，请稍后刷新查看状态", "mode": mode, "status": "parsing"}


@router.delete("/resources/{resource_id}")
def delete_resource(request, resource_id: int):
    """软删除。已被知识库引用的数据不允许删 —— 删了会让切片变成孤儿。"""
    require_manager(request)
    r = DataResource.objects.filter(id=resource_id, is_deleted=False).first()
    if r is None:
        raise HttpError(404, "数据不存在")

    in_use = r.knowledge_docs.filter(is_active=True).count()
    if in_use:
        raise HttpError(400, f"该数据已被 {in_use} 个知识库引用，请先在知识管理中移除")

    r.is_deleted = True
    r.save(update_fields=["is_deleted", "updated_at"])
    log_action(request, "delete_resource", "DataResource", r.id, name=r.name)
    return {"ok": True, "message": f"已删除 {r.name}"}


@router.post("/resources/batch-delete")
def batch_delete_resources(request, ids: List[int]):
    require_manager(request)
    deleted, blocked = 0, []
    for r in DataResource.objects.filter(id__in=ids, is_deleted=False):
        if r.knowledge_docs.filter(is_active=True).exists():
            blocked.append(r.name)
            continue
        r.is_deleted = True
        r.save(update_fields=["is_deleted", "updated_at"])
        deleted += 1
    log_action(request, "batch_delete_resources", "DataResource", ",".join(map(str, ids)), deleted=deleted)
    return {
        "ok": True,
        "message": f"已删除 {deleted} 条" + (f"，{len(blocked)} 条被知识库引用未删除" if blocked else ""),
        "blocked": blocked,
    }


@router.get("/stats")
def dataset_stats(request):
    """数据管理页顶部的统计卡片。"""
    current_user(request)
    qs = DataResource.objects.filter(is_deleted=False)
    by_status = {row["parse_status"]: row["n"] for row in qs.values("parse_status").annotate(n=Count("id"))}
    return {
        "total": qs.count(),
        "categories": DataCategory.objects.count(),
        "tags": DataTag.objects.count(),
        "char_total": sum(qs.values_list("char_count", flat=True)),
        "by_status": by_status,
        "by_format": {
            (row["file_format"] or "未知"): row["n"]
            for row in qs.values("file_format").annotate(n=Count("id"))
        },
    }


@router.get("/formats")
def list_formats(request):
    current_user(request)
    return {"supported": supported_formats()}
