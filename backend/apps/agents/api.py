"""智能体中心接口：智能体 / 会话 / 流式问答 / 引用来源。

对应演示视频的「智能体中心 → 智能体广场」与体验页：
模型选择器、知识库选择器、流式回答、检索来源面板、检索优先开关。

问答走 SSE（Server-Sent Events）而不是 WebSocket：单向推送、原生重连、
能直接复用 HTTP 鉴权，正是这个场景最合适的形态。
"""
import json
import time
from typing import Annotated, List, Optional

from django.conf import settings
from django.db import close_old_connections
from django.db.models import Count
from django.http import StreamingHttpResponse
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import StringConstraints

from apps.common.api import check_rate_limit, current_user, log_action, paginate, require_manager

from .models import Agent, Conversation, Message

router = Router(tags=["智能体中心"])


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------
class AgentIn(Schema):
    # 必填校验放 Schema 层：ninja 的 required 只拦"字段缺失"，不拦空串，
    # 空名字智能体就是这么建出来的。strip_whitespace 让纯空格也过不去。
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    code: str = ""
    avatar: str = ""
    description: str = ""
    welcome_message: str = "您好，我是物联网学科智能助手"
    suggested_questions: List[str] = []
    system_prompt: str = ""
    model_id: Optional[int] = None
    knowledge_base_ids: List[int] = []
    top_k: int = 5
    score_threshold: float = 0.0
    temperature: float = 0.3
    retrieval_first: bool = True
    status: str = "draft"


class AgentOut(Schema):
    id: int
    name: str
    code: str
    avatar: str
    description: str
    welcome_message: str
    suggested_questions: List[str]
    system_prompt: str
    model_id: Optional[int] = None
    model_name: str
    knowledge_base_ids: List[int]
    knowledge_base_names: List[str]
    top_k: int
    score_threshold: float
    temperature: float
    retrieval_first: bool
    status: str
    status_label: str
    conversation_count: int
    message_count: int
    created_at: str


class ChatIn(Schema):
    # 长度上限不是形式主义：问题会原样进提示词并送去调用模型，
    # 放进 20 万字符（实测可行）等于把成本和上游报错风险交给调用方。
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    conversation_id: Optional[int] = None
    model_config_id: Optional[int] = None
    knowledge_base_ids: List[int] = []
    top_k: Optional[int] = None
    score_threshold: Optional[float] = None
    alpha: float = 0.7
    use_keyword: bool = True
    retrieval_first: Optional[bool] = None


class ConversationOut(Schema):
    id: int
    agent_id: int
    agent_name: str
    title: str
    model_name: str
    knowledge_base_names: List[str]
    message_count: int
    created_at: str
    updated_at: str


class CitationOut(Schema):
    index: int
    chunk_id: int
    source_name: str
    chapter_path: str
    snippet: str
    content: str = ""
    score: float = 0.0
    vector_score: float = 0.0
    lexical_score: float = 0.0
    cited: bool = False


class MessageOut(Schema):
    id: int
    role: str
    content: str
    reasoning: str
    citations: List[dict] = []
    model_name: str
    latency_ms: int
    is_error: bool
    feedback: Optional[str] = None
    created_at: str


class FeedbackIn(Schema):
    rating: str
    comment: str = ""


# --------------------------------------------------------------------------
# 智能体
# --------------------------------------------------------------------------
def _agent_out(a: Agent) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "code": a.code,
        "avatar": a.avatar,
        "description": a.description,
        "welcome_message": a.welcome_message,
        "suggested_questions": a.suggested_questions or [],
        "system_prompt": a.system_prompt,
        "model_id": a.model_id,
        "model_name": a.model.name if a.model else "（默认模型）",
        "knowledge_base_ids": list(a.knowledge_bases.values_list("id", flat=True)),
        "knowledge_base_names": list(a.knowledge_bases.values_list("name", flat=True)),
        "top_k": a.top_k,
        "score_threshold": a.score_threshold,
        "temperature": a.temperature,
        "retrieval_first": a.retrieval_first,
        "status": a.status,
        "status_label": a.get_status_display(),
        "conversation_count": a.conversation_count,
        "message_count": a.message_count(),
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M"),
    }


def _apply_kbs(agent: Agent, kb_ids: List[int]) -> None:
    if kb_ids:
        agent.knowledge_bases.set(kb_ids)
    else:
        agent.knowledge_bases.clear()


@router.get("/", response=List[AgentOut])
def list_agents(request, status: str = "", keyword: str = ""):
    current_user(request)
    qs = Agent.objects.select_related("model").prefetch_related("knowledge_bases")
    if status:
        qs = qs.filter(status=status)
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    return [_agent_out(a) for a in qs]


@router.get("/square")
def agent_square(request, keyword: str = ""):
    """智能体广场：只列已发布的，学生看到的就是这个列表。"""
    current_user(request)
    qs = Agent.objects.filter(status=Agent.Status.PUBLISHED).select_related("model").prefetch_related("knowledge_bases")
    if keyword:
        qs = qs.filter(name__icontains=keyword)
    return {"items": [_agent_out(a) for a in qs]}


@router.get("/{agent_id}", response=AgentOut)
def get_agent(request, agent_id: int):
    current_user(request)
    a = (
        Agent.objects.filter(id=agent_id)
        .select_related("model")
        .prefetch_related("knowledge_bases")
        .first()
    )
    if a is None:
        raise HttpError(404, "智能体不存在")
    return _agent_out(a)


@router.post("/", response=AgentOut)
def create_agent(request, payload: AgentIn):
    user = require_manager(request)
    from apps.configs.models import ModelConfig

    code = payload.code or f"agent-{int(time.time())}"
    if Agent.objects.filter(code=code).exists():
        raise HttpError(400, f"智能体标识 {code} 已存在")

    a = Agent.objects.create(
        name=payload.name,
        code=code,
        avatar=payload.avatar,
        description=payload.description,
        welcome_message=payload.welcome_message,
        suggested_questions=payload.suggested_questions,
        system_prompt=payload.system_prompt,
        model=ModelConfig.objects.filter(id=payload.model_id).first(),
        top_k=payload.top_k,
        score_threshold=payload.score_threshold,
        temperature=payload.temperature,
        retrieval_first=payload.retrieval_first,
        status=payload.status,
        created_by=user,
    )
    _apply_kbs(a, payload.knowledge_base_ids)
    log_action(request, "create_agent", "Agent", a.id, name=a.name)
    return _agent_out(a)


@router.patch("/{agent_id}", response=AgentOut)
def update_agent(request, agent_id: int, payload: AgentIn):
    require_manager(request)
    from apps.configs.models import ModelConfig

    a = Agent.objects.filter(id=agent_id).first()
    if a is None:
        raise HttpError(404, "智能体不存在")

    a.name = payload.name
    a.avatar = payload.avatar
    a.description = payload.description
    a.welcome_message = payload.welcome_message
    a.suggested_questions = payload.suggested_questions
    a.system_prompt = payload.system_prompt
    a.model = ModelConfig.objects.filter(id=payload.model_id).first()
    a.top_k = payload.top_k
    a.score_threshold = payload.score_threshold
    a.temperature = payload.temperature
    a.retrieval_first = payload.retrieval_first
    a.status = payload.status
    a.save()
    _apply_kbs(a, payload.knowledge_base_ids)
    log_action(request, "update_agent", "Agent", a.id, name=a.name)
    return _agent_out(a)


@router.post("/{agent_id}/publish", response=AgentOut)
def publish_agent(request, agent_id: int, status: str = "published"):
    require_manager(request)
    a = Agent.objects.filter(id=agent_id).first()
    if a is None:
        raise HttpError(404, "智能体不存在")
    if status not in dict(Agent.Status.choices):
        raise HttpError(400, f"无效的状态：{status}")
    if status == Agent.Status.PUBLISHED and not a.knowledge_bases.exists() and not a.system_prompt:
        raise HttpError(400, "发布前请至少关联一个知识库或填写系统提示词")
    a.status = status
    a.save(update_fields=["status", "updated_at"])
    log_action(request, "publish_agent", "Agent", a.id, status=status)
    return _agent_out(a)


@router.delete("/{agent_id}")
def delete_agent(request, agent_id: int):
    require_manager(request)
    a = Agent.objects.filter(id=agent_id).first()
    if a is None:
        raise HttpError(404, "智能体不存在")
    if a.conversations.exists():
        raise HttpError(400, "该智能体已有问答记录，请先停用而非删除")
    name = a.name
    a.delete()
    log_action(request, "delete_agent", "Agent", agent_id, name=name)
    return {"ok": True, "message": f"已删除智能体 {name}"}


# --------------------------------------------------------------------------
# 会话
# --------------------------------------------------------------------------
def _conversation_out(c: Conversation) -> dict:
    return {
        "id": c.id,
        "agent_id": c.agent_id,
        "agent_name": c.agent.name,
        "title": c.title or "新会话",
        "model_name": c.model_name,
        "knowledge_base_names": c.knowledge_base_names or [],
        "message_count": c.messages.count(),
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M"),
        "updated_at": c.updated_at.strftime("%Y-%m-%d %H:%M"),
    }


@router.get("/{agent_id}/conversations", response=List[ConversationOut])
def list_conversations(request, agent_id: int):
    user = current_user(request)
    qs = (
        Conversation.objects.filter(agent_id=agent_id, user=user, is_deleted=False)
        .select_related("agent")
        .order_by("-updated_at")
    )
    return [_conversation_out(c) for c in qs]


@router.post("/{agent_id}/conversations", response=ConversationOut)
def create_conversation(request, agent_id: int):
    user = current_user(request)
    a = Agent.objects.filter(id=agent_id).first()
    if a is None:
        raise HttpError(404, "智能体不存在")
    c = Conversation.objects.create(
        agent=a,
        user=user,
        title="",
        model_name=a.model.name if a.model else "",
        knowledge_base_names=list(a.knowledge_bases.values_list("name", flat=True)),
    )
    return _conversation_out(c)


@router.patch("/conversations/{conversation_id}")
def rename_conversation(request, conversation_id: int, title: str):
    user = current_user(request)
    c = Conversation.objects.filter(id=conversation_id, user=user).first()
    if c is None:
        raise HttpError(404, "会话不存在")
    c.title = title.strip()[:255]
    c.save(update_fields=["title", "updated_at"])
    return {"ok": True, "title": c.title}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(request, conversation_id: int):
    user = current_user(request)
    c = Conversation.objects.filter(id=conversation_id, user=user).first()
    if c is None:
        raise HttpError(404, "会话不存在")
    c.is_deleted = True
    c.save(update_fields=["is_deleted", "updated_at"])
    return {"ok": True, "message": "已删除会话"}


@router.get("/conversations/{conversation_id}/messages", response=List[MessageOut])
def list_messages(request, conversation_id: int):
    user = current_user(request)
    c = Conversation.objects.filter(id=conversation_id, user=user).first()
    if c is None:
        raise HttpError(404, "会话不存在")
    out = []
    for m in c.messages.all():
        fb = getattr(m, "feedback", None)
        out.append(
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "reasoning": m.reasoning,
                "citations": m.citations or [],
                "model_name": m.model_name,
                "latency_ms": m.latency_ms,
                "is_error": m.is_error,
                "feedback": fb.rating if fb else None,
                "created_at": m.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return out


@router.post("/messages/{message_id}/feedback")
def message_feedback(request, message_id: int, payload: FeedbackIn):
    """赞 / 踩。只允许评价自己会话里的回答，重复评价覆盖。

    归属校验不能省：问答记录里的满意度是教学评估数据，
    放开的话任何登录用户都能给别人的回答刷赞或刷踩。
    """
    from apps.audit.models import MessageFeedback

    user = current_user(request)
    if payload.rating not in dict(MessageFeedback.Rating.choices):
        raise HttpError(400, f"无效的评价：{payload.rating}")
    m = (
        Message.objects.filter(id=message_id)
        .select_related("conversation")
        .first()
    )
    if m is None:
        raise HttpError(404, "消息不存在")
    if m.conversation.user_id != user.id:
        # 返回 404 而不是 403：不暴露"这条消息存在但不属于你"
        raise HttpError(404, "消息不存在")

    MessageFeedback.objects.update_or_create(
        message=m,
        defaults={"rating": payload.rating, "comment": payload.comment, "user": user},
    )
    return {"ok": True, "message": "感谢反馈"}


# --------------------------------------------------------------------------
# 流式问答
# --------------------------------------------------------------------------
def _sse(event: str, data: dict) -> str:
    """SSE 帧。data 里可能含换行（引用正文），必须转义否则会截断事件。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _history_for(conversation: Conversation, limit: int = 6) -> list[tuple[str, str]]:
    """取最近若干轮对话作为上下文。

    只带 3 轮（6 条）：把整段历史塞进提示词会让 token 暴涨，而且对教材问答
    几乎没有增益 —— 追问通常只依赖前一两轮。
    """
    rows = list(
        conversation.messages.exclude(role=Message.Role.SYSTEM).order_by("-created_at").values_list("role", "content")[:limit]
    )
    return [(role, content) for role, content in reversed(rows)]


def _resolve_model_config(payload_id: Optional[int], agent: Agent):
    from apps.configs.models import ModelConfig

    if payload_id:
        cfg = ModelConfig.objects.filter(id=payload_id, kind=ModelConfig.Kind.LLM).first()
        if cfg is not None:
            return cfg
    return agent.model


@router.post("/{agent_id}/chat")
def chat(request, agent_id: int, payload: ChatIn):
    """流式问答。返回 text/event-stream。

    事件序列：
      start → (reasoning | delta)* → citations → done
    出错时插入 error 事件，但**不中断连接** —— 前端已经渲染了一半的回答不该被清掉。
    """
    user = current_user(request)
    # 流式问答消耗 token，按用户限流，避免单个账号无限发起
    check_rate_limit(request, "chat", getattr(settings, "CHAT_RATE_LIMIT_PER_MINUTE", 0))
    agent = (
        Agent.objects.filter(id=agent_id)
        .select_related("model")
        .prefetch_related("knowledge_bases")
        .first()
    )
    if agent is None:
        raise HttpError(404, "智能体不存在")

    question = (payload.question or "").strip()
    if not question:
        raise HttpError(400, "问题不能为空")

    # ---- 会话：有就沿用，没有就新建 ----
    conversation = None
    if payload.conversation_id:
        conversation = Conversation.objects.filter(
            id=payload.conversation_id, user=user, agent=agent
        ).first()
    if conversation is None:
        conversation = Conversation.objects.create(
            agent=agent,
            user=user,
            title=question[:50],
            knowledge_base_names=list(agent.knowledge_bases.values_list("name", flat=True)),
        )

    kb_ids = payload.knowledge_base_ids or list(agent.knowledge_bases.values_list("id", flat=True))
    model_cfg = _resolve_model_config(payload.model_config_id, agent)
    model_label = (model_cfg.name if model_cfg else agent.model.name if agent.model else "默认模型")
    conversation.model_name = model_label
    conversation.save(update_fields=["model_name", "updated_at"])

    Message.objects.create(conversation=conversation, role=Message.Role.USER, content=question)
    history = _history_for(conversation)

    top_k = payload.top_k or agent.top_k
    threshold = payload.score_threshold if payload.score_threshold is not None else agent.score_threshold
    retrieval_first = payload.retrieval_first if payload.retrieval_first is not None else agent.retrieval_first

    def event_stream():
        from apps.configs.services import resolve_embedding, resolve_llm
        from rag.generator import Generator, attach_citation_flags, fallback_answer
        from rag.providers import ProviderError
        from rag.retriever import RetrieveOptions, Retriever, citations_from_hits

        answer_parts: list[str] = []
        reasoning_parts: list[str] = []
        citations: list[dict] = []
        cited: list[int] = []
        stats: dict = {}
        error_message = ""
        started = time.monotonic()

        yield _sse("start", {"conversation_id": conversation.id, "model": model_label})
        try:
            # ---- 检索 ----
            try:
                retriever = Retriever(resolve_embedding())
                result = retriever.retrieve(
                    question,
                    RetrieveOptions(
                        top_k=top_k,
                        alpha=payload.alpha,
                        use_keyword=payload.use_keyword,
                        score_threshold=threshold,
                        knowledge_base_ids=kb_ids or None,
                    ),
                )
                hits = result.hits
                citations = citations_from_hits(hits)
            except ProviderError as exc:
                # 向量模型不可用时关键词检索还能兜住，所以退化为空检索而不是直接失败
                hits = []
                citations = []
                result = None
                yield _sse("notice", {"message": f"检索降级：{exc}"})

            yield _sse(
                "retrieval",
                {
                    "count": len(citations),
                    "vector_count": getattr(result, "vector_count", 0),
                    "lexical_count": getattr(result, "lexical_count", 0),
                    "note": getattr(result, "note", ""),
                },
            )
            if citations:
                # 生成前的引用列表先全部标成「未引用」，等回答结束再按实际引用更新，
                # 两次事件的字段结构保持一致，前端不用做特判
                yield _sse("citations", {"items": attach_citation_flags(citations, []), "cited": []})

            # ---- 生成 ----
            try:
                llm = resolve_llm(model_cfg)
            except ProviderError as exc:
                # 模型不可用也要把 done 发出去 —— 前端靠它收尾，缺了这个会一直转圈
                error_message = str(exc)
                yield _sse("error", {"message": error_message})
                answer_parts.append(fallback_answer(question, error_message))
                yield _sse("delta", {"text": answer_parts[-1]})
                yield _sse(
                    "done",
                    {
                        "conversation_id": conversation.id,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                        "cited": [],
                        "model": model_label,
                        "is_error": True,
                    },
                )
                return

            # 生成阶段可能持续几十秒，这期间不需要数据库连接 ——
            # 主动把连接还回池里，避免并发问答把 Postgres 的 max_connections 占满。
            # 后面若要写回消息，Django 会自己重开连接。
            close_old_connections()

            generator = Generator(llm)
            finished = False
            for ev in generator.stream_answer(
                question,
                hits,
                citations=citations,
                system_prompt=agent.system_prompt,
                retrieval_first=retrieval_first,
                history=history,
            ):
                if ev.type == "delta":
                    answer_parts.append(ev.text)
                    yield _sse("delta", {"text": ev.text})
                elif ev.type == "reasoning":
                    reasoning_parts.append(ev.text)
                    yield _sse("reasoning", {"text": ev.text})
                elif ev.type == "citations":
                    citations = ev.data.get("items", citations)
                    cited = ev.data.get("cited", [])
                    yield _sse("citations", {"items": citations, "cited": cited})
                elif ev.type == "done":
                    finished = True
                    stats = ev.data
                    yield _sse(
                        "done",
                        {
                            "conversation_id": conversation.id,
                            "latency_ms": stats.get("latency_ms", 0),
                            "prompt_tokens": stats.get("prompt_tokens", 0),
                            "completion_tokens": stats.get("completion_tokens", 0),
                            "cited": cited,
                            "model": stats.get("model_name", model_label),
                        },
                    )
                elif ev.type == "error":
                    error_message = ev.text
                    yield _sse("error", {"message": error_message})

            # 生成中途出错时收不到 done 事件，这里补一个，保证前端一定能收尾
            if not finished:
                yield _sse(
                    "done",
                    {
                        "conversation_id": conversation.id,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                        "cited": cited,
                        "model": model_label,
                        "is_error": True,
                    },
                )
        except GeneratorExit:
            # 用户中途关页面：已生成的部分照样存下来，比丢掉强
            error_message = error_message or "客户端提前断开"
            raise
        except Exception as exc:  # noqa: BLE001
            error_message = f"问答过程出错：{exc}"
            yield _sse("error", {"message": error_message})
        finally:
            _persist_answer(
                conversation=conversation,
                question=question,
                answer="".join(answer_parts),
                reasoning="".join(reasoning_parts),
                citations=citations,
                cited=cited,
                model_label=stats.get("model_name") or model_label,
                latency_ms=stats.get("latency_ms") or int((time.monotonic() - started) * 1000),
                prompt_tokens=stats.get("prompt_tokens", 0),
                completion_tokens=stats.get("completion_tokens", 0),
                is_error=bool(error_message),
            )
            # 流结束立即归还连接：这条连接从生成到落库一直挂着，
            # 不主动关会一直占着，并发下很快撞连接上限
            close_old_connections()

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    # 注意：不能设 Connection: keep-alive —— wsgiref 禁止应用写 hop-by-hop 头，会直接 500
    # 关掉 nginx 之类的缓冲，否则流式会被攒成一坨再吐出来
    response["X-Accel-Buffering"] = "no"
    return response


def _persist_answer(
    *,
    conversation: Conversation,
    question: str,
    answer: str,
    reasoning: str,
    citations: list[dict],
    cited: list[int],
    model_label: str,
    latency_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
    is_error: bool,
) -> None:
    """把这一轮问答落库。会话标题用第一句话生成，方便历史列表辨认。"""
    from rag.generator import attach_citation_flags

    body = (answer or "").strip() or "（没有生成内容）"
    Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=body,
        reasoning=reasoning or "",
        citations=attach_citation_flags(citations, cited) if citations else [],
        model_name=model_label,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        is_error=is_error,
    )
    if not conversation.title:
        conversation.title = question[:50]
    conversation.save(update_fields=["title", "model_name", "updated_at"])


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------
@router.get("/stats/overview")
def agent_stats(request):
    user = current_user(request)
    return {
        "agents": Agent.objects.count(),
        "published": Agent.objects.filter(status=Agent.Status.PUBLISHED).count(),
        "conversations": Conversation.objects.filter(is_deleted=False).count(),
        "messages": Message.objects.count(),
        "my_conversations": Conversation.objects.filter(user=user, is_deleted=False).count(),
    }
