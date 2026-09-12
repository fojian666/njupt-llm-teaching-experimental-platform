"""生成器：拼装提示词、流式产出回答、抽取引用编号。

把「检索到的东西」变成「有出处的回答」的关键在两处：
1. **提示词里给每段资料编号**，并要求模型在句末标注 [1][2] —— 否则引用无从追溯；
2. **只把模型真正引用过的资料标为「已引用」**，其余仍列在来源面板里备查，
   避免出现「来源列了 5 条、回答只用了 1 条」却看起来一样可信的错觉。
"""
import re
import time
from dataclasses import dataclass, field
from typing import Iterator, Sequence

from .providers import ChatMessage, LLMProvider
from .retriever import ChunkHit

# 模型吐出的引用标记：[1]、[2,3]、[1][3] 都算
_CITATION = re.compile(r"\[(\d{1,2}(?:\s*[,，]\s*\d{1,2})*)\]")

DEFAULT_WELCOME = "您好，我是物联网学科智能助手"

BASE_RULES = """你是「物联网学科大模型教学实验平台」的学科助理，服务于高校物联网相关专业的教师与学生。

回答要求：
1. 使用简体中文，条理清晰；能分点就分点，公式、代码与专业术语保持原样不做翻译。
2. 引用参考资料中的结论时，必须在相应句子末尾标注来源编号，例如 [1] 或 [2,3]。
3. 不要输出与问题无关的寒暄，也不要复述题目。"""

STRICT_RULE = """4. 严格依据【参考资料】作答。资料未涉及的内容不要凭常识补全，直接说明「现有资料未涵盖该部分」，并指出可能需要补充哪类资料。
5. 若多份资料说法不一致，明确指出分歧并分别标注各自的来源编号。"""

LOOSE_RULE = """4. 以【参考资料】为主要依据；资料不足时可以结合通用专业知识补充，但必须把「资料依据」与「模型补充」分开表述，后者不能标注来源编号。"""


def default_system_prompt(retrieval_first: bool = True) -> str:
    rules = STRICT_RULE if retrieval_first else LOOSE_RULE
    return f"{BASE_RULES}\n{rules}"


@dataclass
class AnswerEvent:
    """流式回答过程中向前端推送的事件。

    前端的 SSE handler 按 type 分派，所以类型名要保持稳定：
      reasoning  —— 思考过程增量（推理模型才有）
      delta      —— 正文增量
      citations  —— 引用来源（回答结束后一次性给全）
      done       —— 收尾，带耗时与 token 用量
      error      —— 出错，text 里是给人看的说明
    """

    type: str
    text: str = ""
    data: dict = field(default_factory=dict)


def build_context(hits: Sequence[ChunkHit]) -> str:
    """把召回切片拼成带编号的参考资料块。"""
    parts: list[str] = []
    for i, hit in enumerate(hits, start=1):
        head = f"【资料 {i}】来源：{hit.source_name}"
        if hit.chapter_path:
            head += f" —— {hit.chapter_path}"
        parts.append(f"{head}\n{hit.content}")
    return "\n\n".join(parts)


def build_messages(
    question: str,
    hits: Sequence[ChunkHit],
    *,
    system_prompt: str = "",
    retrieval_first: bool = True,
    history: Sequence[tuple[str, str]] | None = None,
) -> list[ChatMessage]:
    """组装最终发给大模型的消息序列。"""
    system = (system_prompt or "").strip() or default_system_prompt(retrieval_first)
    messages = [ChatMessage("system", system)]

    for role, content in (history or []):
        if role in ("user", "assistant") and content.strip():
            messages.append(ChatMessage(role, content.strip()))

    if hits:
        context = build_context(hits)
        user = (
            f"【参考资料】\n{context}\n\n"
            f"【用户问题】\n{question}\n\n"
            "请依据上述资料回答，并在引用处标注编号。"
        )
    else:
        # 没有召回结果时也要把话说清楚，否则模型会自己编一套「资料」出来
        user = (
            "【参考资料】\n（本次没有检索到相关资料）\n\n"
            f"【用户问题】\n{question}\n\n"
            "请说明现有资料未涵盖该问题，并给出可补充的资料方向，不要编造具体结论。"
        )
    messages.append(ChatMessage("user", user))
    return messages


def extract_cited_indices(answer: str) -> list[int]:
    """从回答里抽出模型真正引用过的资料编号（去重、升序、越界忽略）。"""
    found: set[int] = set()
    for m in _CITATION.finditer(answer or ""):
        for piece in re.split(r"[,，]", m.group(1)):
            piece = piece.strip()
            if piece.isdigit():
                found.add(int(piece))
    return sorted(found)


def attach_citation_flags(citations: list[dict], cited: Sequence[int]) -> list[dict]:
    """给来源列表打上「是否被回答引用」的标记。"""
    cited_set = set(cited)
    out = []
    for item in citations:
        item = dict(item)
        item["cited"] = item.get("index") in cited_set
        out.append(item)
    return out


class Generator:
    """把检索结果喂给大模型，流式吐回答案。"""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def stream_answer(
        self,
        question: str,
        hits: Sequence[ChunkHit],
        *,
        citations: list[dict] | None = None,
        system_prompt: str = "",
        retrieval_first: bool = True,
        history: Sequence[tuple[str, str]] | None = None,
    ) -> Iterator[AnswerEvent]:
        started = time.monotonic()
        messages = build_messages(
            question,
            hits,
            system_prompt=system_prompt,
            retrieval_first=retrieval_first,
            history=history,
        )

        answer_parts: list[str] = []
        usage = None
        try:
            for delta in self.llm.stream(messages):
                if delta.reasoning:
                    yield AnswerEvent("reasoning", text=delta.reasoning)
                if delta.content:
                    answer_parts.append(delta.content)
                    yield AnswerEvent("delta", text=delta.content)
                if delta.usage:
                    usage = delta.usage
        except Exception as exc:  # noqa: BLE001 —— 任何异常都要变成前端能看懂的事件
            yield AnswerEvent("error", text=str(exc))
            return

        answer = "".join(answer_parts)
        cited = extract_cited_indices(answer)
        if citations:
            yield AnswerEvent(
                "citations",
                data={"items": attach_citation_flags(citations, cited), "cited": cited},
            )

        yield AnswerEvent(
            "done",
            data={
                "answer": answer,
                "cited": cited,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "model_name": self.llm.model,
            },
        )


def fallback_answer(question: str, reason: str) -> str:
    """模型不可用时给用户一段能读的说明，而不是一个 500。"""
    return (
        f"暂时无法生成回答：{reason}\n\n"
        f"你的问题是「{question}」，检索到的资料已列在右侧来源面板中，可先直接查阅。"
    )
