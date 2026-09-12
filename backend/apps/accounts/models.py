from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """平台用户。角色决定可访问的管理端范围。"""

    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        TEACHER = "teacher", "教师"
        STUDENT = "student", "学生"

    role = models.CharField("角色", max_length=16, choices=Role.choices, default=Role.STUDENT)
    display_name = models.CharField("显示名", max_length=64, blank=True)
    phone = models.CharField("手机号", max_length=20, blank=True)
    last_login_ip = models.GenericIPAddressField("最后登录 IP", null=True, blank=True)

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = "用户"
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return self.name

    @property
    def name(self) -> str:
        return self.display_name or self.first_name or self.username

    @property
    def is_manager(self) -> bool:
        return self.is_superuser or self.role == self.Role.ADMIN
