"""问答记录与操作审计。"""
from django.conf import settings
from django.db import models


class MessageFeedback(models.Model):
    """对某条回答的赞 / 踩，支撑「问答记录」模块的质量分析。"""

    class Rating(models.TextChoices):
        LIKE = "like", "赞"
        DISLIKE = "dislike", "踩"

    message = models.OneToOneField(
        "agents.Message", on_delete=models.CASCADE, related_name="feedback", verbose_name="消息"
    )
    rating = models.CharField("评价", max_length=16, choices=Rating.choices)
    comment = models.CharField("备注", max_length=500, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="feedbacks", verbose_name="用户",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "回答评价"
        verbose_name_plural = "回答评价"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_rating_display()} - {self.message_id}"


class OperationLog(models.Model):
    """管理端操作留痕：上传、删除、重新解析、导入知识等。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="operation_logs", verbose_name="操作人",
    )
    action = models.CharField("操作", max_length=64)
    target_type = models.CharField("对象类型", max_length=64, blank=True)
    target_id = models.CharField("对象 ID", max_length=64, blank=True)
    detail = models.JSONField("详情", default=dict, blank=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    created_at = models.DateTimeField("操作时间", auto_now_add=True)

    class Meta:
        verbose_name = "操作日志"
        verbose_name_plural = "操作日志"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"]), models.Index(fields=["action"])]

    def __str__(self) -> str:
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M:%S}"
