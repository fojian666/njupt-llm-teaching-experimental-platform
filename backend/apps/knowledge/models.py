"""知识管理：知识库 → 知识条目 → 切片。

对应演示视频的「数据管理 → 知识管理」：知识库详情（解析状态 / 是否有效）、
导入知识（已选列表）、切片列表、切片详情（文件名 + 章节路径 + 正文）。
"""
from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField


class KnowledgeBase(models.Model):
    """知识库 —— 检索的最小隔离单位，一个智能体可挂多个知识库。"""

    name = models.CharField("知识库名称", max_length=128)
    code = models.SlugField("标识", max_length=64, unique=True)
    description = models.TextField("描述", blank=True)

    embedding_model = models.ForeignKey(
        "configs.ModelConfig", on_delete=models.SET_NULL, related_name="knowledge_bases",
        null=True, blank=True, verbose_name="向量模型",
    )
    chunk_size = models.IntegerField("切片长度", default=settings.CHUNK_SIZE)
    chunk_overlap = models.IntegerField("切片重叠", default=settings.CHUNK_OVERLAP)
    chunk_strategy = models.CharField("切片策略", max_length=32, default="heading")

    is_active = models.BooleanField("是否启用", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="knowledge_bases", verbose_name="创建人",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "知识库"
        verbose_name_plural = "知识库"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def doc_count(self) -> int:
        return self.docs.count()

    @property
    def chunk_count(self) -> int:
        return Chunk.objects.filter(knowledge_doc__knowledge_base=self, is_active=True).count()


class KnowledgeDoc(models.Model):
    """知识库中的一条数据。演示里知识库详情表的一行即为本记录。"""

    class ParseStatus(models.TextChoices):
        PENDING = "pending", "待解析"
        PARSING = "parsing", "解析中"
        SUCCESS = "success", "解析成功"
        FAILED = "failed", "解析失败"

    knowledge_base = models.ForeignKey(
        KnowledgeBase, on_delete=models.CASCADE, related_name="docs", verbose_name="知识库"
    )
    data_resource = models.ForeignKey(
        "datasets.DataResource", on_delete=models.CASCADE, related_name="knowledge_docs",
        verbose_name="数据资源",
    )
    parse_status = models.CharField(
        "解析状态", max_length=16, choices=ParseStatus.choices, default=ParseStatus.PENDING
    )
    parse_message = models.TextField("解析信息", blank=True)
    is_active = models.BooleanField("是否有效", default=True)
    chunk_count = models.IntegerField("切片数", default=0)
    parsed_at = models.DateTimeField("解析时间", null=True, blank=True)
    created_at = models.DateTimeField("上传时间", auto_now_add=True)

    class Meta:
        verbose_name = "知识条目"
        verbose_name_plural = "知识条目"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["knowledge_base", "data_resource"], name="uniq_kb_resource"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.knowledge_base.name} / {self.data_resource.name}"

    @property
    def name(self) -> str:
        return self.data_resource.name

    @property
    def file_format(self) -> str:
        return self.data_resource.file_format


class Chunk(models.Model):
    """切片。演示里的「切片编号 / 内容 = 文件名 + 章节路径 + 正文」即本模型。"""

    knowledge_doc = models.ForeignKey(
        KnowledgeDoc, on_delete=models.CASCADE, related_name="chunks", verbose_name="知识条目"
    )
    seq = models.IntegerField("切片编号", default=0)
    content = models.TextField("切片内容")
    chapter_path = models.CharField("章节路径", max_length=512, blank=True)
    char_count = models.IntegerField("字符数", default=0)
    is_active = models.BooleanField("是否有效", default=True)
    embedding = VectorField(dimensions=settings.EMBEDDING_DIM, null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "切片"
        verbose_name_plural = "切片"
        ordering = ["knowledge_doc_id", "seq"]
        indexes = [
            models.Index(fields=["knowledge_doc", "seq"]),
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"#{self.seq} {self.content[:30]}"

    @property
    def source_name(self) -> str:
        return self.knowledge_doc.data_resource.name
