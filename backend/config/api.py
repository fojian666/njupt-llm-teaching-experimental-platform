"""API 入口：一个 NinjaAPI 实例 + 各模块路由。

选 Django Ninja 而不是 DRF 的原因：基于类型标注自动生成 OpenAPI 文档，
带 /docs 交互式调试页，且性能接近原生——对一个要长期演进的教学平台，
「接口即文档」比多写一堆 serializer 值钱得多。

鉴权统一挂在实例上（默认全部需要登录），登录接口单独 auth=None 放行。
"""
from ninja import NinjaAPI

from apps.accounts.api import router as accounts_router
from apps.agents.api import router as agents_router
from apps.audit.api import router as audit_router
from apps.common.api import session_auth
from apps.configs.api import router as configs_router
from apps.datasets.api import router as datasets_router
from apps.knowledge.api import router as knowledge_router

api = NinjaAPI(
    title="物联网学科大模型教学实验平台 API",
    version="1.0.0",
    description=(
        "行业大模型管理平台后端接口。\n\n"
        "模块：数据管理（分类管理 / 知识管理）、智能体中心（智能体广场 / 对话）、"
        "配置中心（模型供应商 / 模型）、问答记录。"
    ),
    auth=session_auth,
    urls_namespace="api",
)

api.add_router("/auth", accounts_router)
api.add_router("/datasets", datasets_router)
api.add_router("/knowledge", knowledge_router)
api.add_router("/agents", agents_router)
api.add_router("/configs", configs_router)
api.add_router("/audit", audit_router)


@api.get("/ping", auth=None, tags=["系统"])
def ping(request):
    """探活。不带鉴权，方便前端启动时判断后端在不在。"""
    return {"ok": True, "message": "pong", "version": "1.0.0"}
