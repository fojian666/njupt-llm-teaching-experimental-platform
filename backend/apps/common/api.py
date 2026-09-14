"""API 层的公共件：鉴权、分页、统一响应结构。

放这里而不是在每个 api.py 里各写一份 —— 分页字段名、错误码这些一旦口径不一，
前端的封装层就得写一堆特判。
"""
import time
from typing import Any, Generic, Sequence, TypeVar

from django.http import HttpRequest
from ninja import Schema
from ninja.errors import HttpError

T = TypeVar("T")


def check_rate_limit(request: HttpRequest, action: str, limit_per_minute: int) -> None:
    """每用户每分钟的简单限流，超限抛 429。

    计数放在 Django 缓存里，默认是进程内的 locmem，单进程够用；
    多 worker 部署时把 CACHES 换成 Redis，计数即全局共享。
    limit_per_minute <= 0 表示不限制。
    """
    if limit_per_minute <= 0:
        return
    from django.core.cache import cache

    user = getattr(request, "user", None)
    who = user.id if user is not None and user.is_authenticated else "anon"
    key = f"ratelimit:{action}:{who}:{int(time.time() // 60)}"
    count = cache.get(key)
    if count is None:
        cache.set(key, 1, timeout=70)
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:  # 键刚好过期
            cache.set(key, 1, timeout=70)
            count = 1
    if count > limit_per_minute:
        raise HttpError(429, f"操作过于频繁：每分钟最多 {limit_per_minute} 次，请稍后再试")


# --------------------------------------------------------------------------
# 鉴权
# --------------------------------------------------------------------------
class SessionAuth:
    """基于 Django session 的鉴权。

    平台是校内教学系统，不做 JWT：前端用 Vite 代理把 /api 转到后端，
    同源 + sessionid cookie 就够，省掉跨域 cookie 与 CSRF 的一堆坑。
    """

    def __call__(self, request: HttpRequest):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return user


session_auth = SessionAuth()


def current_user(request: HttpRequest):
    """取当前登录用户，未登录直接 401。"""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise HttpError(401, "请先登录")
    return user


def require_manager(request: HttpRequest):
    """管理操作（上传、删除、配置）需要管理员或教师角色。

    学生的权限就是「问问题」，数据管理 / 配置中心这些入口对他们只读或不可见。
    """
    user = current_user(request)
    role = getattr(user, "role", "")
    if not (user.is_superuser or role in ("admin", "teacher")):
        raise HttpError(403, "当前账号没有管理权限")
    return user


# --------------------------------------------------------------------------
# 分页
# --------------------------------------------------------------------------
class PageIn(Schema):
    page: int = 1
    page_size: int = 20


class PageOut(Schema, Generic[T]):
    total: int = 0
    page: int = 1
    page_size: int = 20
    pages: int = 0
    items: list[T] = []


def paginate(queryset, page: int = 1, page_size: int = 20) -> dict:
    """对 queryset 做分页，返回 PageOut 需要的字段。顺序由 queryset 自己保证。"""
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 200))
    total = queryset.count()
    start = (page - 1) * page_size
    items = list(queryset[start : start + page_size])
    pages = (total + page_size - 1) // page_size
    return {"total": total, "page": page, "page_size": page_size, "pages": pages, "items": items}


def paginate_list(items: Sequence[Any], page: int = 1, page_size: int = 20) -> dict:
    """对已经在内存里的列表分页（例如聚合后的统计结果）。"""
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 200))
    total = len(items)
    start = (page - 1) * page_size
    pages = (total + page_size - 1) // page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "items": list(items[start : start + page_size]),
    }


# --------------------------------------------------------------------------
# 统一响应
# --------------------------------------------------------------------------
class OkOut(Schema):
    ok: bool = True
    message: str = ""


class IdOut(Schema):
    id: int
    message: str = ""


def ok(message: str = "", **extra) -> dict:
    return {"ok": True, "message": message, **extra}


def log_action(request, action: str, target_type: str = "", target_id: Any = "", **detail) -> None:
    """记一条操作日志。审计失败不该影响主流程，所以整段包起来。"""
    from apps.audit.models import OperationLog

    try:
        OperationLog.objects.create(
            user=getattr(request, "user", None) if getattr(request, "user", None) and request.user.is_authenticated else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id or ""),
            detail=detail or {},
            ip=_client_ip(request),
        )
    except Exception:  # noqa: BLE001
        pass


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None
