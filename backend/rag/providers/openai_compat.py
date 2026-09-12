"""OpenAI 兼容协议的模型客户端。

DeepSeek、通义千问（compatible-mode）、Kimi、智谱、vLLM / Ollama 都提供
`/chat/completions` 与 `/embeddings` 两个同构接口，所以一个实现就能覆盖全部云端供应商。
只用 httpx，不引 openai SDK —— 少一个依赖，也少一层黑盒。
"""
import json
from typing import Iterator, Sequence

import httpx

from .base import (
    ChatDelta,
    ChatMessage,
    EmbeddingProvider,
    LLMProvider,
    ProviderError,
    RerankProvider,
    Usage,
)

# 连接超时压短（连不上就该立刻报错），读超时放长（大模型流式吐字本来就慢）
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 300.0
EMBED_TIMEOUT = 120.0


def _join(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _explain(status: int, body: str) -> str:
    """把接口的错误响应翻译成能看懂的话。"""
    snippet = (body or "").strip()[:300]
    if status in (401, 403):
        return f"模型接口鉴权失败（HTTP {status}），请检查配置中心里的 API Key。{snippet}"
    if status == 404:
        return f"模型接口地址不存在（HTTP 404），请检查 base_url 与 model 名称。{snippet}"
    if status == 429:
        return f"模型接口限流或余额不足（HTTP 429）。{snippet}"
    return f"模型接口返回错误（HTTP {status}）。{snippet}"


class OpenAICompatEmbedding(EmbeddingProvider):
    """OpenAI 兼容协议的向量模型。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimension: int = 0,
        batch_size: int = 10,
        name: str = "",
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.dimension = dimension
        self.batch_size = max(1, batch_size)
        self.name = name or model

    def _post_embeddings(self, payload: dict):
        try:
            return httpx.post(
                _join(self.base_url, "embeddings"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=httpx.Timeout(EMBED_TIMEOUT, connect=CONNECT_TIMEOUT),
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"连接向量模型失败：{exc}") from exc

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        texts = [t if t.strip() else " " for t in texts]
        if not texts:
            return []

        payload: dict = {"model": self.model, "input": list(texts)}
        # 支持自定义输出维度的模型（通义 v3 / OpenAI v3）要显式指定，
        # 否则拿到 1536 维而库里是 1024 维，写进去直接报维度不匹配。
        # 但硅基流动等固定维度模型不认这个参数（HTTP 400），失败时自动去参重试。
        if self.dimension:
            payload["dimensions"] = self.dimension

        resp = self._post_embeddings(payload)
        if resp.status_code >= 400 and "dimensions" in payload:
            payload.pop("dimensions")
            resp = self._post_embeddings(payload)
        if resp.status_code >= 400 and any(len(t) > 500 for t in payload["input"]):
            # BGE 系列输入上限 512 token，硅基流动对超长输入报 400 而不是自动截断；
            # 500 字符以内必然安全（中文一字约一 token）
            payload["input"] = [t[:500] for t in payload["input"]]
            resp = self._post_embeddings(payload)

        if resp.status_code >= 400:
            raise ProviderError(_explain(resp.status_code, resp.text), status=resp.status_code)

        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError("向量模型返回的不是合法 JSON") from exc

        items = data.get("data") or []
        # 有的网关会打乱顺序，按 index 排回来才与入参一一对应
        items = sorted(items, key=lambda it: it.get("index", 0))
        vectors = [it.get("embedding") or [] for it in items]
        if not vectors:
            raise ProviderError("向量模型返回了空结果，请检查模型名与账户额度")

        got = len(vectors[0])
        if self.dimension and got != self.dimension:
            raise ProviderError(
                f"向量维度不匹配：期望 {self.dimension} 维，实际返回 {got} 维。"
                "请在配置中心修正该向量模型的维度，并重建迁移。"
            )
        return vectors


class OpenAICompatLLM(LLMProvider):
    """OpenAI 兼容协议的大语言模型。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        name: str = "",
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.name = name or model

    def _payload(self, messages: Sequence[ChatMessage], stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [m.as_dict() for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, messages: Sequence[ChatMessage]) -> tuple[str, Usage]:
        try:
            resp = httpx.post(
                _join(self.base_url, "chat/completions"),
                headers=self._headers,
                json=self._payload(messages, stream=False),
                timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"连接大模型失败：{exc}") from exc

        if resp.status_code >= 400:
            raise ProviderError(_explain(resp.status_code, resp.text), status=resp.status_code)

        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError("大模型返回的不是合法 JSON") from exc

        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("大模型没有返回任何回答")
        content = (choices[0].get("message") or {}).get("content") or ""
        raw_usage = data.get("usage") or {}
        return content, Usage(
            int(raw_usage.get("prompt_tokens") or 0),
            int(raw_usage.get("completion_tokens") or 0),
        )

    def stream(self, messages: Sequence[ChatMessage]) -> Iterator[ChatDelta]:
        payload = self._payload(messages, stream=True)
        # 让接口在最后一个 chunk 里带上 token 用量
        payload["stream_options"] = {"include_usage": True}

        try:
            with httpx.stream(
                "POST",
                _join(self.base_url, "chat/completions"),
                headers=self._headers,
                json=payload,
                timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
            ) as resp:
                if resp.status_code >= 400:
                    resp.read()
                    raise ProviderError(
                        _explain(resp.status_code, resp.text), status=resp.status_code
                    )

                for line in resp.iter_lines():
                    delta = _parse_sse_line(line)
                    if delta is not None:
                        yield delta
        except httpx.HTTPError as exc:
            raise ProviderError(f"大语言模型流式连接中断：{exc}") from exc


def _parse_sse_line(line: str) -> ChatDelta | None:
    """解析一行 SSE。

    协议形如：
        data: {"choices":[{"delta":{"content":"物"}}]}
        data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{...}}
        data: [DONE]
    返回 None 表示这行没有可用内容（心跳、空行、[DONE]）。
    """
    line = (line or "").strip()
    if not line or not line.startswith("data:"):
        return None
    body = line[5:].strip()
    if not body or body == "[DONE]":
        return None

    try:
        chunk = json.loads(body)
    except ValueError:
        return None

    usage = None
    raw_usage = chunk.get("usage")
    if raw_usage:
        usage = Usage(
            int(raw_usage.get("prompt_tokens") or 0),
            int(raw_usage.get("completion_tokens") or 0),
        )

    choices = chunk.get("choices") or []
    if not choices:
        # 有些供应商单独发一个只带 usage 的收尾 chunk，不产生正文
        return ChatDelta(usage=usage) if usage else None

    choice = choices[0]
    delta = choice.get("delta") or choice.get("message") or {}
    return ChatDelta(
        content=delta.get("content") or "",
        reasoning=delta.get("reasoning_content") or delta.get("reasoning") or "",
        finish=bool(choice.get("finish_reason")),
        usage=usage,
    )


class OpenAICompatRerank(RerankProvider):
    """重排模型。用兼容 /rerank 协议的接口（通义、Jina、BGE 服务化都支持）。"""

    def __init__(self, *, base_url: str, api_key: str, model: str, name: str = ""):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.name = name or model

    def rerank(self, query: str, documents: Sequence[str], top_n: int = 5):
        if not documents:
            return []
        try:
            resp = httpx.post(
                _join(self.base_url, "rerank"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "query": query,
                    "documents": list(documents),
                    "top_n": min(top_n, len(documents)),
                },
                timeout=httpx.Timeout(EMBED_TIMEOUT, connect=CONNECT_TIMEOUT),
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"连接重排模型失败：{exc}") from exc

        if resp.status_code >= 400:
            raise ProviderError(_explain(resp.status_code, resp.text), status=resp.status_code)

        results = (resp.json().get("results") or [])
        return [(int(r.get("index", 0)), float(r.get("relevance_score") or 0.0)) for r in results]
