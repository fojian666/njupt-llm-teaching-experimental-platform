"""问答记录与审计接口。

对应演示视频的「问答记录」模块：问题 / 回答 / 引用来源 / 评价 / 耗时，
以及管理端的操作日志。
"""
from typing import List, Optional

from django.db.models import Avg, Count, Q
from django.utils.dateparse import parse_date
from ninja import Router, Schema

from apps.agents.models import Agent, Conversation, Message
from apps.audit.models import MessageFeedback, OperationLog
from apps.common.api import current_user, paginate

router = Router(tags=["问答记录"])


class QARecordOut(Schema):
    id: int
    conversation_id: int
    conversation_title: str
    agent_id: int
    agent_name: str
    user_name: str
    question: str
    answer: str
    citation_count: int
    cited_count: int
    citations: List[dict] = []
    model_name: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    is_error: bool
    feedback: Optional[str] = None
    feedback_comment: str = ""
    created_at: str


class LogOut(Schema):
    id: int
    user_name: str
    action: str
    target_type: str
    target_id: str
    detail: dict
    ip: Optional[str] = None
    created_at: str


@router.get("/records")
def list_records(
    request,
    agent_id: int = 0,
    feedback: str = "",
    keyword: str = "",
    date_from: str = "",
    date_to: str = "",
    only_error: bool = False,
    page: int = 1,
    page_size: int = 20,
):
    """问答记录列表。一行 = 一问一答。"""
    current_user(request)

    qs = (
        Message.objects.filter(role=Message.Role.ASSISTANT)
        .select_related("conversation", "conversation__agent", "conversation__user")
        .order_by("-created_at")
    )
    if agent_id:
        qs = qs.filter(conversation__agent_id=agent_id)
    if keyword:
        qs = qs.filter(Q(content__icontains=keyword) | Q(conversation__title__icontains=keyword))
    if only_error:
        qs = qs.filter(is_error=True)
    if date_from:
        d = parse_date(date_from)
        if d:
            qs = qs.filter(created_at__date__gte=d)
    if date_to:
        d = parse_date(date_to)
        if d:
            qs = qs.filter(created_at__date__lte=d)
    if feedback:
        qs = qs.filter(feedback__rating=feedback)

    result = paginate(qs, page, page_size)
    items = result["items"]
    if not items:
        result["items"] = []
        return result

    # 一问一答配对：把这一页涉及到的会话的用户消息一次取回，再在内存里配对，
    # 避免每条回答都去打一次「上一条用户消息」的查询
    conv_ids = {m.conversation_id for m in items}
    user_msgs = list(
        Message.objects.filter(conversation_id__in=conv_ids, role=Message.Role.USER)
        .order_by("created_at")
        .values("conversation_id", "content", "created_at")
    )
    by_conv: dict[int, list[dict]] = {}
    for um in user_msgs:
        by_conv.setdefault(um["conversation_id"], []).append(um)

    rows = []
    for m in items:
        question = ""
        for um in by_conv.get(m.conversation_id, []):
            if um["created_at"] <= m.created_at:
                question = um["content"]
            else:
                break
        citations = m.citations or []
        fb = getattr(m, "feedback", None)
        rows.append(
            {
                "id": m.id,
                "conversation_id": m.conversation_id,
                "conversation_title": m.conversation.title or "未命名会话",
                "agent_id": m.conversation.agent_id,
                "agent_name": m.conversation.agent.name,
                "user_name": m.conversation.user.name if m.conversation.user else "—",
                "question": question,
                "answer": m.content,
                "citation_count": len(citations),
                "cited_count": sum(1 for c in citations if c.get("cited")),
                "citations": citations,
                "model_name": m.model_name,
                "latency_ms": m.latency_ms,
                "prompt_tokens": m.prompt_tokens,
                "completion_tokens": m.completion_tokens,
                "is_error": m.is_error,
                "feedback": fb.rating if fb else None,
                "feedback_comment": fb.comment if fb else "",
                "created_at": m.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    result["items"] = rows
    return result


@router.get("/logs")
def list_logs(request, action: str = "", user_id: int = 0, page: int = 1, page_size: int = 20):
    current_user(request)
    qs = OperationLog.objects.select_related("user").order_by("-created_at")
    if action:
        qs = qs.filter(action=action)
    if user_id:
        qs = qs.filter(user_id=user_id)

    result = paginate(qs, page, page_size)
    result["items"] = [
        {
            "id": log.id,
            "user_name": log.user.name if log.user else "系统",
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "detail": log.detail or {},
            "ip": log.ip,
            "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for log in result["items"]
    ]
    return result


@router.get("/logs/actions")
def log_actions(request):
    """操作类型的多选项，用于筛选框。"""
    current_user(request)
    rows = OperationLog.objects.values("action").annotate(n=Count("id")).order_by("-n")
    return {"items": [{"action": r["action"], "count": r["n"]} for r in rows]}


@router.get("/stats")
def qa_stats(request, days: int = 7):
    """问答概览：质检用得到的几个数。"""
    current_user(request)
    from datetime import timedelta

    from django.utils import timezone

    since = timezone.now() - timedelta(days=max(1, min(days, 90)))
    assistant = Message.objects.filter(role=Message.Role.ASSISTANT)
    recent = assistant.filter(created_at__gte=since)

    total = assistant.count()
    liked = MessageFeedback.objects.filter(rating=MessageFeedback.Rating.LIKE).count()
    disliked = MessageFeedback.objects.filter(rating=MessageFeedback.Rating.DISLIKE).count()
    rated = liked + disliked

    return {
        "total_qa": total,
        "recent_qa": recent.count(),
        "error_qa": assistant.filter(is_error=True).count(),
        "conversations": Conversation.objects.filter(is_deleted=False).count(),
        "agents": Agent.objects.count(),
        "liked": liked,
        "disliked": disliked,
        "satisfaction": round(liked / rated, 3) if rated else None,
        "avg_latency_ms": int(recent.aggregate(v=Avg("latency_ms"))["v"] or 0),
        "avg_citations": round(
            (sum(len(m.citations or []) for m in recent.only("citations")) / max(1, recent.count())), 2
        ),
        "by_agent": [
            {"agent_id": r["conversation__agent_id"], "name": r["conversation__agent__name"], "count": r["n"]}
            for r in recent.values("conversation__agent_id", "conversation__agent__name").annotate(n=Count("id"))
        ],
    }
