"""智能体中心：智能体 → 会话 → 消息。

对应演示视频的「智能体中心 → 智能体广场」与体验页
（模型选择器 / 知识库选择器 / 流式回答 / 检索来源面板 / 检索优先开关）。
"""
from django.conf import settings
from django.db import models


class Agent(models.Model):
    """智能体。演示例：自然资源智能问答。"""

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已发布"
        DISABLED = "disabled", "已停用"

    name = models.CharField("智能体名称", max_length=128)
    code = models.SlugField("标识", max_length=64, unique=True)
    avatar = models.CharField("头像", max_length=255, blank=True)
    description = models.TextField("简介", blank=True)
    welcome_message = models.CharField(
        "欢迎语", max_length=255, default="您好，我是物联网学科智能助手"
    )
    suggested_questions = models.JSONField("推荐问题", default=list, blank=True)
    system_prompt = models.TextField("系统提示词", blank=True)

    model = models.ForeignKey(
        "configs.ModelConfig", on_delete=models.SET_NULL, related_name="agents",
        null=True, blank=True, verbose_name="默认模型",
    )
    knowledge_bases = models.ManyToManyField(
        "knowledge.KnowledgeBase", blank=True, related_name="agents", verbose_name="关联知识库"
    )

    top_k = models.IntegerField("召回条数", default=settings.RETRIEVAL_TOP_K)
    score_threshold = models.FloatField("相似度阈值", default=settings.RETRIEVAL_SCORE_THRESHOLD)
    temperature = models.FloatField("温度", default=0.3)
    retrieval_first = models.BooleanField(
        "检索优先", default=True, help_text="开启后严格基于检索结果作答，关闭则允许模型自由发挥"
    )

    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="agents", verbose_name="创建人",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "智能体"
        verbose_name_plural = "智能体"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def conversation_count(self) -> int:
        return self.conversations.count()

    def message_count(self) -> int:
        """累计问答条数（用户提问 + 助手回答都算），供智能体页头的使用统计展示。"""
        return Message.objects.filter(conversation__agent=self, conversation__is_deleted=False).count()


class Conversation(models.Model):
    """一次会话（对话页左侧的历史条目）。"""

    agent = models.ForeignKey(
        Agent, on_delete=models.CASCADE, related_name="conversations", verbose_name="智能体"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations",
        verbose_name="用户",
    )
    title = models.CharField("会话标题", max_length=255, blank=True)
    model_name = models.CharField("使用的模型", max_length=128, blank=True)
    knowledge_base_names = models.JSONField("使用的知识库", default=list, blank=True)
    is_deleted = models.BooleanField("已删除", default=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "会话"
        verbose_name_plural = "会话"
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["-updated_at"])]

    def __str__(self) -> str:
        return self.title or f"会话 {self.pk}"


class Message(models.Model):
    """一问一答。assistant 消息携带引用来源，对应演示右侧的「检索来源」面板。"""

    class Role(models.TextChoices):
        USER = "user", "用户"
        ASSISTANT = "assistant", "助手"
        SYSTEM = "system", "系统"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages", verbose_name="会话"
    )
    role = models.CharField("角色", max_length=16, choices=Role.choices)
    content = models.TextField("内容", blank=True)
    reasoning = models.TextField("思考过程", blank=True)
    citations = models.JSONField(
        "引用来源", default=list, blank=True,
        help_text="[{index, chunk_id, source_name, chapter_path, snippet, score}]",
    )
    model_name = models.CharField("模型", max_length=128, blank=True)
    prompt_tokens = models.IntegerField("输入 tokens", default=0)
    completion_tokens = models.IntegerField("输出 tokens", default=0)
    latency_ms = models.IntegerField("耗时(毫秒)", default=0)
    is_error = models.BooleanField("是否出错", default=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "消息"
        verbose_name_plural = "消息"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self) -> str:
        return f"[{self.role}] {self.content[:30]}"
