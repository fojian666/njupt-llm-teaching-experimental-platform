"""配置中心：模型供应商、具体模型、系统参数。"""
from django.db import models


class ModelProvider(models.Model):
    """模型供应商 —— 一条记录 = 一组可复用的接入信息（base_url + api_key）。"""

    name = models.CharField("供应商名称", max_length=64)
    code = models.SlugField("标识", max_length=64, unique=True)
    base_url = models.CharField("接口地址", max_length=255, help_text="OpenAI 兼容协议的 base_url")
    api_key = models.CharField("API Key", max_length=255, blank=True)
    is_active = models.BooleanField("是否启用", default=True)
    sort = models.IntegerField("排序", default=0)
    remark = models.CharField("备注", max_length=255, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "模型供应商"
        verbose_name_plural = "模型供应商"
        ordering = ["sort", "id"]

    def __str__(self) -> str:
        return f"{self.name}（{self.code}）"


class ModelConfig(models.Model):
    """具体可调用的模型。演示视频里对话页可切换的 DeepSeek-V3 / Qwen3-30B 就是这里的记录。"""

    class Kind(models.TextChoices):
        LLM = "llm", "大语言模型"
        EMBEDDING = "embedding", "向量模型"
        RERANK = "rerank", "重排模型"

    provider = models.ForeignKey(
        ModelProvider, on_delete=models.CASCADE, related_name="models", verbose_name="供应商"
    )
    name = models.CharField("显示名", max_length=64, help_text="前端下拉里展示的名字")
    model_id = models.CharField("模型标识", max_length=128, help_text="调用时传给接口的 model 参数")
    kind = models.CharField("类型", max_length=16, choices=Kind.choices, default=Kind.LLM)
    dimension = models.IntegerField("向量维度", null=True, blank=True, help_text="仅向量模型需要")
    max_tokens = models.IntegerField("最大输出长度", default=4096)
    temperature = models.FloatField("温度", default=0.3)
    is_default = models.BooleanField("是否默认", default=False)
    is_active = models.BooleanField("是否启用", default=True)
    sort = models.IntegerField("排序", default=0)
    extra = models.JSONField("扩展参数", default=dict, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "模型"
        verbose_name_plural = "模型"
        ordering = ["kind", "sort", "id"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "model_id", "kind"], name="uniq_provider_model_kind"),
        ]

    def __str__(self) -> str:
        return f"{self.name}（{self.get_kind_display()}）"

    def save(self, *args, **kwargs):
        # 同一类型下保证只有一个默认模型
        if self.is_default:
            ModelConfig.objects.filter(kind=self.kind).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class SystemConfig(models.Model):
    """键值型系统参数：检索默认参数、切片默认参数等，改配置不用改代码。"""

    key = models.SlugField("配置键", max_length=128, unique=True)
    value = models.JSONField("配置值", default=dict, blank=True)
    group = models.CharField("分组", max_length=64, default="general")
    description = models.CharField("说明", max_length=255, blank=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "系统参数"
        verbose_name_plural = "系统参数"
        ordering = ["group", "key"]

    def __str__(self) -> str:
        return self.key
