from django.apps import AppConfig


class AuditConfigConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    verbose_name = "问答记录与审计"
