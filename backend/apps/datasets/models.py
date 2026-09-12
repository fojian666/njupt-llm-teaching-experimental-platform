"""数据管理：分类树 + 数据资源 + 标签。

对应演示视频的「数据管理 → 数据分类管理」页面：
左侧分类树、右侧数据列表（数据名称 / 数据分类 / 上传方式 / 数据格式 / 数据标签 / 解析状态 / 上传时间）。
"""
from django.conf import settings
from django.db import models


class DataCategory(models.Model):
    """数据分类树节点。演示里为「调查监测 / 空间规划 / 01法律法规 / 不动产登记 → 01法律…」。"""

    name = models.CharField("分类名称", max_length=128)
    code = models.CharField("分类编码", max_length=64, blank=True)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, related_name="children",
        null=True, blank=True, verbose_name="上级分类",
    )
    sort = models.IntegerField("排序", default=0)
    remark = models.CharField("备注", max_length=255, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "数据分类"
        verbose_name_plural = "数据分类"
        ordering = ["sort", "id"]
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="uniq_category_sibling_name"),
        ]

    def __str__(self) -> str:
        return self.full_path

    @property
    def full_path(self) -> str:
        """从根到当前的完整路径，用于列表展示与切片溯源。"""
        names, node, guard = [], self, 0
        while node is not None and guard < 32:
            names.append(node.name)
            node = node.parent
            guard += 1
        return " / ".join(reversed(names))

    def descendant_ids(self, include_self: bool = True) -> list[int]:
        """含自身在内的所有后代 id —— 分类树筛选时用。"""
        ids = [self.id] if include_self else []
        stack = list(self.children.all())
        while stack:
            node = stack.pop()
            ids.append(node.id)
            stack.extend(node.children.all())
        return ids


class DataTag(models.Model):
    """数据标签，用于跨分类的自由标注。"""

    name = models.CharField("标签名", max_length=64, unique=True)
    color = models.CharField("颜色", max_length=16, default="#378ADD")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "数据标签"
        verbose_name_plural = "数据标签"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class DataResource(models.Model):
    """一条数据资源 —— 可以是上传的文件，也可以是外部导入的语料。"""

    class UploadMethod(models.TextChoices):
        UPLOAD = "upload", "本地上传"
        BATCH = "batch", "批量导入"
        OCR = "ocr", "OCR 导入"
        URL = "url", "链接采集"

    class ParseStatus(models.TextChoices):
        NOT_PARSED = "not_parsed", "未解析"
        PENDING = "pending", "待解析"
        PARSING = "parsing", "解析中"
        SUCCESS = "success", "解析成功"
        FAILED = "failed", "解析失败"

    name = models.CharField("数据名称", max_length=255)
    category = models.ForeignKey(
        DataCategory, on_delete=models.SET_NULL, related_name="resources",
        null=True, blank=True, verbose_name="数据分类",
    )
    upload_method = models.CharField(
        "上传方式", max_length=16, choices=UploadMethod.choices, default=UploadMethod.UPLOAD
    )
    file = models.FileField("源文件", upload_to="sources/%Y/%m/", blank=True, null=True)
    file_format = models.CharField("数据格式", max_length=16, blank=True)
    file_size = models.BigIntegerField("文件大小(字节)", default=0)
    tags = models.ManyToManyField(DataTag, blank=True, related_name="resources", verbose_name="数据标签")

    parse_status = models.CharField(
        "解析状态", max_length=16, choices=ParseStatus.choices, default=ParseStatus.NOT_PARSED
    )
    parse_message = models.TextField("解析信息", blank=True)
    parsed_at = models.DateTimeField("解析时间", null=True, blank=True)
    content_text = models.TextField("解析后正文", blank=True)
    char_count = models.IntegerField("字符数", default=0)

    source_note = models.CharField("来源说明", max_length=255, blank=True)
    is_deleted = models.BooleanField("已删除", default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="resources", verbose_name="创建人",
    )
    created_at = models.DateTimeField("上传时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "数据资源"
        verbose_name_plural = "数据资源"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["parse_status"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def tag_names(self) -> list[str]:
        return [t.name for t in self.tags.all()]
