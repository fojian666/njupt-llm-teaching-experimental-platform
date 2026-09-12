"""模型调用的统一接口。

上层（检索器 / 生成器 / 入库流水线）只认这里的抽象，不关心背后是 DeepSeek 还是通义千问。
换供应商 = 改配置中心里的一条记录，业务代码一行不动 —— 这是「配置中心」这个模块存在的意义。
"""
from dataclasses import dataclass
from typing import Iterator, Sequence


class ProviderError(RuntimeError):
    """模型调用失败。

    message 会原样透到前端的错误提示里，所以要写人话，别把 HTTP 状态码裸奔出去。
    """

    def __init__(self, message: str, *, status: int | None = None, detail: str = ""):
        super().__init__(message)
        self.status = status
        self.detail = detail


@dataclass
class ChatMessage:
    role: str  # system / user / assistant
    content: str

    def as_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.prompt_tokens + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
        )


@dataclass
class ChatDelta:
    """流式返回的一小段增量。

    reasoning 单独拿出来放 —— DeepSeek-R1 这类推理模型会先吐思考过程，
    前端要能把「思考中」和「正文」分开展示，混在一起会很乱。
    """

    content: str = ""
    reasoning: str = ""
    finish: bool = False
    usage: Usage | None = None


class EmbeddingProvider:
    """向量模型：把文本批量转成向量。"""

    name: str = ""
    model: str = ""
    dimension: int = 0
    batch_size: int = 10  # 通义 text-embedding-v3 单次最多 10 条，取最小值最稳

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_one(self, text: str) -> list[float]:
        vectors = self.embed([text])
        if not vectors:
            raise ProviderError("向量模型没有返回结果")
        return vectors[0]

    def embed_batched(self, texts: Sequence[str], progress=None) -> list[list[float]]:
        """按 batch_size 分批调用，避免一次性把 500 条切片甩给接口被限流。

        progress: 可选回调 (done: int, total: int)，供后台任务上报进度。
        """
        out: list[list[float]] = []
        total = len(texts)
        step = max(1, self.batch_size)
        for start in range(0, total, step):
            out.extend(self.embed(list(texts[start : start + step])))
            if progress is not None:
                progress(min(start + step, total), total)
        if len(out) != total:
            raise ProviderError(
                f"向量条数对不上：送了 {total} 条，只返回 {len(out)} 条",
            )
        return out


class LLMProvider:
    """大语言模型：一次性对话 + 流式对话。"""

    name: str = ""
    model: str = ""
    temperature: float = 0.3
    max_tokens: int = 4096

    def chat(self, messages: Sequence[ChatMessage]) -> tuple[str, Usage]:
        raise NotImplementedError

    def stream(self, messages: Sequence[ChatMessage]) -> Iterator[ChatDelta]:
        raise NotImplementedError


class RerankProvider:
    """重排模型：对候选切片做精排。首期未接入，留好接口。"""

    name: str = ""
    model: str = ""

    def rerank(self, query: str, documents: Sequence[str], top_n: int = 5) -> list[tuple[int, float]]:
        """返回 [(原文下标, 相关度分数)]，按分数从高到低。"""
        raise NotImplementedError
