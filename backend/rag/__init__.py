"""RAG 服务层 —— 平台的知识底座。

分层（依赖方向自上而下，绝不反向）：

    pipeline     入库流水线：解析 → 切片 → 向量化 → 落库
    retriever    混合检索：向量召回 + 关键词召回 → 融合排序
    generator    生成：拼提示词 → 流式调用 → 抽取引用
    store        存储访问（pgvector + 关键词粗筛）
    splitter     切片
    parsers      各格式解析
    providers    模型调用（OpenAI 兼容协议）
    tokenizer    零依赖字符 bigram 分词

约定：本包**不在导入期**依赖 Django ORM，模型只在方法内部延迟导入。
这样解析、切片、融合排序这些纯逻辑可以脱离 Django 单独测试，
将来要把检索服务拆成独立的 FastAPI 进程也不用重写。
"""
from .generator import (
    AnswerEvent,
    Generator,
    attach_citation_flags,
    build_context,
    build_messages,
    default_system_prompt,
    extract_cited_indices,
    fallback_answer,
)
from .pipeline import IndexReport, index_document, index_many
from .providers import (
    ChatMessage,
    EmbeddingProvider,
    LLMProvider,
    ProviderError,
    embedding_from_settings,
    llm_from_settings,
    missing_key_hint,
)
from .retriever import RetrieveOptions, Retriever, citations_from_hits
from .splitter import ChunkData, split
from .store import ChunkHit, SearchResult

__all__ = [
    "AnswerEvent",
    "ChunkData",
    "ChunkHit",
    "ChatMessage",
    "EmbeddingProvider",
    "Generator",
    "IndexReport",
    "LLMProvider",
    "ProviderError",
    "RetrieveOptions",
    "Retriever",
    "SearchResult",
    "attach_citation_flags",
    "build_context",
    "build_messages",
    "citations_from_hits",
    "default_system_prompt",
    "embedding_from_settings",
    "extract_cited_indices",
    "fallback_answer",
    "index_document",
    "index_many",
    "llm_from_settings",
    "missing_key_hint",
    "split",
]
