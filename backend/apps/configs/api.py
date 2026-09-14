"""配置中心接口：模型供应商 / 模型 / 系统参数。

对应演示视频的「配置中心」。这一层是纯管理面，写操作都要求管理员或教师角色。
"""
from typing import Annotated, Optional

from django.conf import settings
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.pagination import paginate as ninja_paginate  # noqa: F401  （保留给后续分页）
from pydantic import StringConstraints

from apps.common.api import current_user, log_action, require_manager
from .models import ModelConfig, ModelProvider, SystemConfig
from .services import available_llms, default_model

router = Router(tags=["配置中心"])


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------
class ProviderIn(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    base_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    api_key: str = ""
    is_active: bool = True
    sort: int = 0
    remark: str = ""


class ProviderOut(Schema):
    id: int
    name: str
    code: str
    base_url: str
    has_key: bool
    key_hint: str
    is_active: bool
    sort: int
    remark: str
    model_count: int


class ModelIn(Schema):
    provider_id: int
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    model_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    kind: str = "llm"
    dimension: Optional[int] = None
    max_tokens: int = 4096
    temperature: float = 0.3
    is_default: bool = False
    is_active: bool = True
    sort: int = 0


class ModelOut(Schema):
    id: int
    provider_id: int
    provider_name: str
    name: str
    model_id: str
    kind: str
    kind_label: str
    dimension: Optional[int] = None
    max_tokens: int
    temperature: float
    is_default: bool
    is_active: bool
    sort: int


class SysConfigIn(Schema):
    value: dict = {}
    group: str = "general"
    description: str = ""


class SysConfigOut(Schema):
    id: int
    key: str
    value: dict
    group: str
    description: str


# --------------------------------------------------------------------------
# 供应商
# --------------------------------------------------------------------------
def _mask(key: str) -> str:
    """Key 只回显尾巴几位 —— 配置页能看出「填过没有」，但拿不到完整密钥。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "已配置"
    return f"{key[:4]}****{key[-4:]}"


def _provider_out(p: ModelProvider) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "code": p.code,
        "base_url": p.base_url,
        "has_key": bool(p.api_key),
        "key_hint": _mask(p.api_key),
        "is_active": p.is_active,
        "sort": p.sort,
        "remark": p.remark,
        "model_count": p.models.count(),
    }


def _model_out(m: ModelConfig) -> dict:
    return {
        "id": m.id,
        "provider_id": m.provider_id,
        "provider_name": m.provider.name,
        "name": m.name,
        "model_id": m.model_id,
        "kind": m.kind,
        "kind_label": m.get_kind_display(),
        "dimension": m.dimension,
        "max_tokens": m.max_tokens,
        "temperature": m.temperature,
        "is_default": m.is_default,
        "is_active": m.is_active,
        "sort": m.sort,
    }


@router.get("/providers", response=list[ProviderOut])
def list_providers(request):
    current_user(request)
    return [_provider_out(p) for p in ModelProvider.objects.all()]


def _check_embedding_dim(kind: str, dimension: int | None) -> None:
    """向量模型维度必须与数据库列一致。

    维度不一致时数据库层会直接报维度不匹配，错误信息跟"配置填错了"毫无关联，
    排查成本高。这里前置拦住，把问题在保存配置的那一刻说清楚。
    """
    if kind != "embedding":
        return
    expected = getattr(settings, "EMBEDDING_DIM", None)
    if not expected:
        return
    if dimension is None:
        raise HttpError(400, f"向量模型必须填写向量维度，且需与知识库一致（当前为 {expected}）")
    if int(dimension) != int(expected):
        raise HttpError(
            400,
            f"向量维度不一致：模型填的是 {dimension}，知识库切片向量列是 {expected}。"
            f"换用其它维度的模型需要重建迁移并重新向量化全部切片。",
        )


@router.post("/providers", response=ProviderOut)
def create_provider(request, payload: ProviderIn):
    require_manager(request)
    if ModelProvider.objects.filter(code=payload.code).exists():
        raise HttpError(400, f"供应商标识 {payload.code} 已存在")
    p = ModelProvider.objects.create(**payload.model_dump())
    log_action(request, "create_provider", "ModelProvider", p.id, name=p.name)
    return _provider_out(p)


@router.patch("/providers/{provider_id}", response=ProviderOut)
def update_provider(request, provider_id: int, payload: ProviderIn):
    require_manager(request)
    p = ModelProvider.objects.filter(id=provider_id).first()
    if p is None:
        raise HttpError(404, "供应商不存在")
    data = payload.model_dump()
    # 前端回显的是掩码，空串或掩码值都不该覆盖真实 Key
    if not data.get("api_key") or "*" in (data.get("api_key") or ""):
        data.pop("api_key", None)
    for k, v in data.items():
        setattr(p, k, v)
    p.save()
    log_action(request, "update_provider", "ModelProvider", p.id, name=p.name)
    return _provider_out(p)


@router.delete("/providers/{provider_id}")
def delete_provider(request, provider_id: int):
    require_manager(request)
    p = ModelProvider.objects.filter(id=provider_id).first()
    if p is None:
        raise HttpError(404, "供应商不存在")
    if p.models.exists():
        raise HttpError(400, "该供应商下还有模型，请先删除模型")
    name = p.name
    p.delete()
    log_action(request, "delete_provider", "ModelProvider", provider_id, name=name)
    return {"ok": True, "message": f"已删除供应商 {name}"}


# --------------------------------------------------------------------------
# 模型
# --------------------------------------------------------------------------
@router.get("/models", response=list[ModelOut])
def list_models(request, kind: str = ""):
    current_user(request)
    qs = ModelConfig.objects.select_related("provider").all()
    if kind:
        qs = qs.filter(kind=kind)
    return [_model_out(m) for m in qs]


@router.post("/models", response=ModelOut)
def create_model(request, payload: ModelIn):
    require_manager(request)
    provider = ModelProvider.objects.filter(id=payload.provider_id).first()
    if provider is None:
        raise HttpError(404, "供应商不存在")
    _check_embedding_dim(payload.kind, payload.dimension)
    if ModelConfig.objects.filter(
        provider=provider, model_id=payload.model_id, kind=payload.kind
    ).exists():
        raise HttpError(400, "同供应商下已有同名同类型的模型")
    data = payload.model_dump()
    data.pop("provider_id")
    m = ModelConfig.objects.create(provider=provider, **data)
    log_action(request, "create_model", "ModelConfig", m.id, name=m.name, kind=m.kind)
    return _model_out(m)


@router.patch("/models/{model_id}", response=ModelOut)
def update_model(request, model_id: int, payload: ModelIn):
    require_manager(request)
    m = ModelConfig.objects.filter(id=model_id).select_related("provider").first()
    if m is None:
        raise HttpError(404, "模型不存在")
    data = payload.model_dump()
    provider_id = data.pop("provider_id", None)
    _check_embedding_dim(data.get("kind", m.kind), data.get("dimension", m.dimension))
    if provider_id and provider_id != m.provider_id:
        provider = ModelProvider.objects.filter(id=provider_id).first()
        if provider is None:
            raise HttpError(404, "供应商不存在")
        m.provider = provider
    for k, v in data.items():
        setattr(m, k, v)
    m.save()
    log_action(request, "update_model", "ModelConfig", m.id, name=m.name)
    return _model_out(m)


@router.delete("/models/{model_id}")
def delete_model(request, model_id: int):
    require_manager(request)
    m = ModelConfig.objects.filter(id=model_id).first()
    if m is None:
        raise HttpError(404, "模型不存在")
    name = m.name
    m.delete()
    log_action(request, "delete_model", "ModelConfig", model_id, name=name)
    return {"ok": True, "message": f"已删除模型 {name}"}


# --------------------------------------------------------------------------
# 前端下拉与系统参数
# --------------------------------------------------------------------------
@router.get("/llm-options")
def llm_options(request):
    """对话页的模型选择器。没有配置中心记录时退回环境变量里的默认模型。"""
    current_user(request)
    items = available_llms()
    if not items:
        from django.conf import settings

        items = [
            {
                "id": 0,
                "name": f"{settings.LLM_MODEL}（环境变量）",
                "model_id": settings.LLM_MODEL,
                "provider": "环境变量",
                "is_default": True,
            }
        ]
    return {"items": items, "default_id": next((i["id"] for i in items if i["is_default"]), items[0]["id"])}


@router.get("/status")
def config_status(request):
    """给前端一个「能不能调模型」的体检结果，避免用户对着报错瞎猜。"""
    current_user(request)
    from django.conf import settings

    llm_cfg = default_model("llm")
    emb_cfg = default_model("embedding")
    return {
        "llm": {
            "source": "配置中心" if llm_cfg else "环境变量",
            "model": llm_cfg.model_id if llm_cfg else settings.LLM_MODEL,
            "has_key": bool(llm_cfg.provider.api_key) if llm_cfg else bool(settings.LLM_API_KEY),
        },
        "embedding": {
            "source": "配置中心" if emb_cfg else "环境变量",
            "model": emb_cfg.model_id if emb_cfg else settings.EMBEDDING_MODEL,
            "dimension": (emb_cfg.dimension if emb_cfg and emb_cfg.dimension else settings.EMBEDDING_DIM),
            "has_key": bool(emb_cfg.provider.api_key) if emb_cfg else bool(settings.EMBEDDING_API_KEY),
        },
    }


@router.get("/system", response=list[SysConfigOut])
def list_system_configs(request, group: str = ""):
    current_user(request)
    qs = SystemConfig.objects.all()
    if group:
        qs = qs.filter(group=group)
    return [
        {
            "id": c.id,
            "key": c.key,
            "value": c.value,
            "group": c.group,
            "description": c.description,
        }
        for c in qs
    ]


@router.put("/system/{key}", response=SysConfigOut)
def upsert_system_config(request, key: str, payload: SysConfigIn):
    require_manager(request)
    cfg, _created = SystemConfig.objects.update_or_create(
        key=key,
        defaults={
            "value": payload.value,
            "group": payload.group,
            "description": payload.description,
        },
    )
    log_action(request, "update_system_config", "SystemConfig", cfg.id, key=key)
    return {
        "id": cfg.id,
        "key": cfg.key,
        "value": cfg.value,
        "group": cfg.group,
        "description": cfg.description,
    }
