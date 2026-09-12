"""账号相关接口：登录 / 登出 / 当前用户。"""
from django.contrib.auth import authenticate, login, logout
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.common.api import current_user

router = Router(tags=["账号"])


class LoginIn(Schema):
    username: str
    password: str


class UserOut(Schema):
    id: int
    username: str
    name: str
    role: str
    role_label: str
    is_manager: bool
    email: str = ""


def _user_out(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role": user.role,
        "role_label": user.get_role_display(),
        "is_manager": bool(user.is_manager or user.is_superuser),
        "email": user.email or "",
    }


@router.post("/login", response=UserOut, auth=None)
def do_login(request, payload: LoginIn):
    user = authenticate(request, username=payload.username, password=payload.password)
    if user is None:
        raise HttpError(401, "用户名或密码不正确")
    if not user.is_active:
        raise HttpError(403, "该账号已被停用")

    login(request, user)

    # 记一下登录 IP，方便管理员排查异常登录
    ip = (request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR") or "")
    if ip:
        user.last_login_ip = ip.split(",")[0].strip()
        user.save(update_fields=["last_login_ip"])
    return _user_out(user)


@router.post("/logout", auth=None)
def do_logout(request):
    logout(request)
    return {"ok": True, "message": "已退出登录"}


@router.get("/me", response=UserOut)
def me(request):
    return _user_out(current_user(request))
