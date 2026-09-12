"""模型供应商的构造入口。

两种来源，优先级从高到低：
1. 配置中心的 `ModelConfig` 记录（由 apps/configs/services.py 查询后传进来）
2. 环境变量默认值（settings.LLM_* / EMBEDDING_*）—— 没配 Key 也能把工程跑起来

本包本身不碰 ORM，保持可独立拆分。
"""
from .base import (
    ChatDelta,
    ChatMessage,
    EmbeddingProvider,
    LLMProvider,
    ProviderError,
    RerankProvider,
    Usage,
)
from .openai_compat import (
    OpenAICompatEmbedding,
    OpenAICompatLLM,
    OpenAICompatRerank,
)

__all__ = [
    "ChatDelta",
    "ChatMessage",
    "EmbeddingProvider",
    "LLMProvider",
    "ProviderError",
    "RerankProvider",
    "Usage",
    "OpenAICompatEmbedding",
    "OpenAICompatLLM",
    "OpenAICompatRerank",
    "embedding_from_settings",
    "llm_from_settings",
    "missing_key_hint",
]


def embedding_from_settings() -> OpenAICompatEmbedding:
    """按环境变量构造向量模型。"""
    from django.conf import settings

    return OpenAICompatEmbedding(
        base_url=settings.EMBEDDING_BASE_URL,
        api_key=settings.EMBEDDING_API_KEY,
        model=settings.EMBEDDING_MODEL,
        dimension=settings.EMBEDDING_DIM,
        name=settings.EMBEDDING_MODEL,
    )


def llm_from_settings() -> OpenAICompatLLM:
    """按环境变量构造大语言模型。"""
    from django.conf import settings

    return OpenAICompatLLM(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=0.3,
        max_tokens=4096,
        name=settings.LLM_MODEL,
    )


def missing_key_hint(provider: str) -> str:
    """没配 Key 时的统一提示语 —— 前后端共用同一句话，避免口径不一。"""
    key = "EMBEDDING_API_KEY" if provider == "embedding" else "LLM_API_KEY"
    return (
        f"尚未配置 {provider} 模型的 API Key，暂时无法调用云端模型。"
        f"请在 backend/.env 中填写 {key}，或在「配置中心 → 模型供应商」里补充后重试。"
    )
