"""把「配置中心」里的记录翻译成可直接调用的模型客户端。

这是 ORM 与 rag 层之间唯一的接缝：rag 层不认识 ModelConfig，
应用层也不关心 httpx 怎么拼 URL。缺 Key 的情况在这里统一拦下并给出人话提示，
免得每一处调用点各写一套报错。
"""
from typing import TYPE_CHECKING

from rag.providers import (
    EmbeddingProvider,
    LLMProvider,
    OpenAICompatEmbedding,
    OpenAICompatLLM,
    OpenAICompatRerank,
    ProviderError,
    RerankProvider,
    embedding_from_settings,
    llm_from_settings,
    missing_key_hint,
)

if TYPE_CHECKING:  # pragma: no cover
    from .models import ModelConfig


def default_model(kind: str) -> "ModelConfig | None":
    """取该类型的默认启用模型。默认标记由 ModelConfig.save() 保证唯一。"""
    from .models import ModelConfig

    qs = ModelConfig.objects.filter(kind=kind, is_active=True, provider__is_active=True)
    return qs.filter(is_default=True).first() or qs.order_by("sort", "id").first()


def _embedding_from_config(cfg: "ModelConfig") -> OpenAICompatEmbedding:
    provider = cfg.provider
    if not provider.api_key:
        raise ProviderError(missing_key_hint("embedding"))
    return OpenAICompatEmbedding(
        base_url=provider.base_url,
        api_key=provider.api_key,
        model=cfg.model_id,
        dimension=cfg.dimension or 0,
        name=cfg.name or cfg.model_id,
    )


def resolve_embedding(knowledge_base=None) -> EmbeddingProvider:
    """确定用哪个向量模型：知识库指定 > 配置中心默认 > 环境变量。

    注意第三级的兜底是刻意的：seed_demo 会建好供应商与模型记录但不填 Key，
    如果这时直接报错，.env 里配好的 Key 就永远用不上了。
    所以规则是「有 Key 的优先」，谁有 Key 用谁，都没有才报错。
    """
    cfg = getattr(knowledge_base, "embedding_model", None) if knowledge_base else None
    if cfg is not None and not (cfg.is_active and cfg.provider.is_active):
        cfg = None
    cfg = cfg or default_model("embedding")
    if cfg is not None and cfg.provider.api_key:
        return _embedding_from_config(cfg)

    provider = embedding_from_settings()
    if not provider.api_key:
        raise ProviderError(missing_key_hint("embedding"))
    return provider


def resolve_llm(model_config: "ModelConfig | None" = None) -> LLMProvider:
    """确定用哪个大模型：调用方指定 > 配置中心默认 > 环境变量。规则同 resolve_embedding。"""
    cfg = model_config
    if cfg is not None and (not cfg.is_active or not cfg.provider.is_active):
        cfg = None
    cfg = cfg or default_model("llm")

    if cfg is not None and cfg.provider.api_key:
        return OpenAICompatLLM(
            base_url=cfg.provider.base_url,
            api_key=cfg.provider.api_key,
            model=cfg.model_id,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            name=cfg.name or cfg.model_id,
        )

    provider = llm_from_settings()
    if not provider.api_key:
        raise ProviderError(missing_key_hint("llm"))
    return provider


def resolve_rerank() -> RerankProvider | None:
    """重排模型是可选增强，没配就返回 None，调用方自行跳过。"""
    cfg = default_model("rerank")
    if cfg is None or not cfg.provider.api_key:
        return None
    return OpenAICompatRerank(
        base_url=cfg.provider.base_url,
        api_key=cfg.provider.api_key,
        model=cfg.model_id,
        name=cfg.name or cfg.model_id,
    )


def available_llms() -> list[dict]:
    """前端模型下拉的选项。"""
    from .models import ModelConfig

    rows = (
        ModelConfig.objects.filter(kind=ModelConfig.Kind.LLM, is_active=True, provider__is_active=True)
        .select_related("provider")
        .order_by("-is_default", "sort", "id")
    )
    return [
        {
            "id": cfg.id,
            "name": cfg.name,
            "model_id": cfg.model_id,
            "provider": cfg.provider.name,
            "is_default": cfg.is_default,
        }
        for cfg in rows
    ]
