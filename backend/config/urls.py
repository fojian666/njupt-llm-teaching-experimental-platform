from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from config.api import api


def health(_request):
    """健康检查，用于前端/运维探活。"""
    return JsonResponse({"status": "ok", "service": "iot-edu-platform"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", health, name="healthz"),
    # 全部业务接口挂在 /api 下，OpenAPI 文档见 /api/docs
    path("api/", api.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
