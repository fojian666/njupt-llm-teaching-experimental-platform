"""演示数据初始化：把工作区里的资料灌成一个「打开就能用」的平台。

用法：
    python manage.py seed_demo                 # 建账号 + 分类 + 模型配置 + 导入全部资料
    python manage.py seed_demo --skip-index    # 只建元数据，不做切片与向量化（没配 Key 时用）
    python manage.py seed_demo --reset         # 先清空业务数据再灌（不动用户表）

设计取舍：**资料来自工作区里真实存在的文件**，不造假数据。
演示时点开任意一条都能溯源到原始文档，这比编几条漂亮假数据有说服力得多。
"""
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

WORKSPACE = Path(settings.BASE_DIR).resolve().parent  # 仓库根目录：从 settings 推导，别人 clone 到哪都成立
OCR_DIR = WORKSPACE / "ocr" / "物联网工程导论第2版"
SAMPLE_DIR = WORKSPACE / "示例语料"

# (相对仓库根的路径, 分类路径, 上传方式, 标签, 来源说明)
DATASETS = [
    ("0.1-物联网学院简介-2025.8.17(2).docx", "01 学院概况", "upload", ["学院简介"], "学院对外简介材料"),
    ("3-2025级-物联网工程专业培养方案20250813.docx", "02 培养方案/物联网工程", "upload", ["2025级", "培养方案"], "2025 级物联网工程专业培养方案"),
    ("1-2025级-网络工程专业培养方案.docx", "02 培养方案/网络工程", "upload", ["2025级", "培养方案"], "2025 级网络工程专业培养方案"),
    ("5-地理信息科学专业培养方案.doc", "02 培养方案/地理信息科学", "upload", ["2025级", "培养方案"], "2025 级地理信息科学专业培养方案"),
    ("物联网概论(第3版) (韩毅刚,肖纯贤) (z-library.sk, 1lib.sk, z-lib.sk).epub", "03 专业教材/物联网概论", "upload", ["核心教材"], "物联网概论（第3版）"),
    ("物联网工程导论 第2版 (吴功宜) (z-library.sk, 1lib.sk, z-lib.sk).pdf", "03 专业教材/物联网工程导论", "ocr", ["核心教材", "扫描件"], "扫描版教材，需先 OCR"),
    # 原创示例语料：随仓库分发，clone 后无需任何外部素材也能把问答链路跑通
    ("示例语料/01-物联网感知层技术概览.md", "05 原创示例语料", "upload", ["原创示例"], "平台自带的原创教学语料，可自由替换"),
    ("示例语料/02-物联网网络层与通信技术.md", "05 原创示例语料", "upload", ["原创示例"], "平台自带的原创教学语料，可自由替换"),
    ("示例语料/03-物联网数据处理与安全.md", "05 原创示例语料", "upload", ["原创示例"], "平台自带的原创教学语料，可自由替换"),
    ("示例语料/04-物联网典型应用案例选讲.md", "05 原创示例语料", "upload", ["原创示例"], "平台自带的原创教学语料，可自由替换"),
]

# (上级分类路径, 分类名称, 排序) —— 必须父级在前，这样一次遍历就能建完整棵树
CATEGORIES = [
    ("", "01 学院概况", 1),
    ("", "02 培养方案", 2),
    ("02 培养方案", "物联网工程", 1),
    ("02 培养方案", "网络工程", 2),
    ("02 培养方案", "地理信息科学", 3),
    ("", "03 专业教材", 3),
    ("03 专业教材", "物联网工程导论", 1),
    ("03 专业教材", "物联网概论", 2),
    ("", "04 规章制度", 4),
    ("", "05 原创示例语料", 5),
]

# 演示账号与密码。登录页上写的就是这几个，改这里必须同步改前端登录页的提示。
DEMO_USERS = [
    ("admin", "admin123", "admin", "平台管理员", True),
    ("teacher", "teacher123", "teacher", "张老师", False),
    ("student", "student123", "student", "李同学", False),
]


class Command(BaseCommand):
    help = "初始化演示数据：账号、分类、标签、模型配置、资料与知识库"

    def add_arguments(self, parser):
        parser.add_argument("--skip-index", action="store_true", help="不做切片与向量化")
        parser.add_argument("--reset", action="store_true", help="先清空业务数据")
        parser.add_argument("--reset-passwords", action="store_true",
                            help="把演示账号的密码强制重置为约定值（admin123 等）")

    def handle(self, *args, **options):
        from apps.accounts.models import User
        from apps.agents.models import Agent
        from apps.audit.models import MessageFeedback, OperationLog
        from apps.configs.models import ModelConfig, ModelProvider
        from apps.datasets.models import DataCategory, DataResource, DataTag
        from apps.knowledge.models import Chunk, KnowledgeBase, KnowledgeDoc

        skip_index = options["skip_index"]
        if options["reset"]:
            self.stdout.write(self.style.WARNING("清空既有业务数据…"))
            Chunk.objects.all().delete()
            KnowledgeDoc.objects.all().delete()
            KnowledgeBase.objects.all().delete()
            Agent.objects.all().delete()
            DataResource.objects.all().delete()
            DataTag.objects.all().delete()
            DataCategory.objects.all().delete()
            MessageFeedback.objects.all().delete()
            OperationLog.objects.all().delete()

        # ---------------- 账号 ----------------
        for username, password, role, display, is_staff in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"role": role, "display_name": display, "is_staff": is_staff, "is_superuser": is_staff},
            )
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(f"  建账号 {username} / {password}")
            elif options["reset_passwords"]:
                user.set_password(password)
                user.save()
                self.stdout.write(f"  重置密码 {username} / {password}")
            elif not user.check_password(password):
                # 密码对不上是个隐蔽的坑：登录页写着 admin123，库里却是旧的 admin123456，
                # 表现就是"演示时怎么都登不进去"。这里明确提示，并给出修复命令。
                self.stdout.write(self.style.WARNING(
                    f"  账号 {username} 已存在，但密码与演示约定（{password}）不一致"
                    f"；如需重置：python manage.py seed_demo --reset-passwords"
                ))
            else:
                self.stdout.write(f"  账号已存在 {username}")

        # ---------------- 分类树 ----------------
        cache: dict[str, DataCategory] = {}
        for parent_path, name, sort in CATEGORIES:
            parent = cache.get(parent_path)
            node, _ = DataCategory.objects.get_or_create(
                name=name, parent=parent, defaults={"sort": sort}
            )
            cache[f"{parent_path}/{name}" if parent_path else name] = node
        self.stdout.write(f"  分类 {DataCategory.objects.count()} 个")

        # ---------------- 模型供应商与模型 ----------------
        deepseek, _ = ModelProvider.objects.get_or_create(
            code="deepseek",
            defaults={
                "name": "DeepSeek",
                "base_url": "https://api.deepseek.com/v1",
                "remark": "OpenAI 兼容协议",
                "sort": 1,
            },
        )
        dashscope, _ = ModelProvider.objects.get_or_create(
            code="dashscope",
            defaults={
                "name": "通义千问（DashScope）",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "remark": "向量模型走这里",
                "sort": 2,
            },
        )
        ModelConfig.objects.get_or_create(
            provider=deepseek, model_id="deepseek-chat", kind="llm",
            defaults={"name": "DeepSeek-V3", "is_default": True, "sort": 1, "max_tokens": 4096},
        )
        ModelConfig.objects.get_or_create(
            provider=deepseek, model_id="deepseek-reasoner", kind="llm",
            defaults={"name": "DeepSeek-R1", "sort": 2, "max_tokens": 8192},
        )
        ModelConfig.objects.get_or_create(
            provider=dashscope, model_id="text-embedding-v3", kind="embedding",
            defaults={"name": "通义 text-embedding-v3", "is_default": True, "dimension": settings.EMBEDDING_DIM},
        )
        self.stdout.write(f"  模型 {ModelConfig.objects.count()} 个")

        # ---------------- 标签 ----------------
        tag_map = {}
        for name, color in [
            ("核心教材", "#378ADD"), ("培养方案", "#1D9E75"), ("2025级", "#BA7517"),
            ("扫描件", "#D4537E"), ("学院简介", "#7F77DD"), ("原创示例", "#5B8FF9"),
        ]:
            tag_map[name], _ = DataTag.objects.get_or_create(name=name, defaults={"color": color})

        # ---------------- 资料导入 ----------------
        kb, _ = KnowledgeBase.objects.get_or_create(
            code="iot-teaching",
            defaults={
                "name": "物联网学科教学知识库",
                "description": "教材与培养方案，支撑学科问答",
                "chunk_size": settings.CHUNK_SIZE,
                "chunk_overlap": settings.CHUNK_OVERLAP,
                "chunk_strategy": "heading",
            },
        )

        with transaction.atomic():
            for rel_path, category_path, method, tags, note in DATASETS:
                src = WORKSPACE / rel_path
                filename = Path(rel_path).name
                if not src.exists():
                    self.stdout.write(self.style.WARNING(f"  缺失文件，跳过：{rel_path}"))
                    continue

                resource, created = DataResource.objects.get_or_create(
                    name=filename,
                    defaults={
                        "category": cache.get(category_path),
                        "upload_method": method,
                        "file_format": _ext(filename),
                        "source_note": note,
                    },
                )
                if created or not resource.file:
                    rel = _store(src, filename)
                    resource.file = rel
                    resource.file_size = src.stat().st_size
                    resource.category = cache.get(category_path)
                    resource.save()
                for t in tags:
                    resource.tags.add(tag_map[t])

                doc, _ = KnowledgeDoc.objects.get_or_create(knowledge_base=kb, data_resource=resource)
                self.stdout.write(f"  资料 {filename}")

            # OCR 成果单独作为一条数据 —— 演示「OCR 导入」这条上传方式
            ocr_txt = OCR_DIR / "物联网工程导论-第2版-全文.txt"
            if ocr_txt.exists():
                name = "物联网工程导论-第2版-全文（OCR）.txt"
                resource, created = DataResource.objects.get_or_create(
                    name=name,
                    defaults={
                        "category": cache.get("03 专业教材/物联网工程导论"),
                        "upload_method": "ocr",
                        "file_format": "txt",
                        "source_note": "由扫描版 PDF 经 macOS Vision OCR 得到，338 页 / 33 万字",
                    },
                )
                if created or not resource.file:
                    resource.file = _store(ocr_txt, name)
                    resource.file_size = ocr_txt.stat().st_size
                    resource.category = cache.get("03 专业教材/物联网工程导论")
                    resource.save()
                for t in ("核心教材", "扫描件"):
                    resource.tags.add(tag_map[t])
                KnowledgeDoc.objects.get_or_create(knowledge_base=kb, data_resource=resource)
                self.stdout.write(f"  资料 {name}")

        # ---------------- 智能体 ----------------
        agent, _ = Agent.objects.get_or_create(
            code="iot-qa",
            defaults={
                "name": "物联网学科智能问答",
                "description": "基于教材与培养方案，回答物联网专业的课程、概念与技术问题",
                "welcome_message": "您好，我是物联网学科智能助手，可以回答教材概念、课程设置与培养方案相关问题。",
                "suggested_questions": [
                    "物联网的体系结构分为哪几层？",
                    "RFID 系统由哪几部分组成？",
                    "物联网工程专业的核心课程有哪些？",
                    "ZigBee 技术有什么特点？",
                ],
                "system_prompt": "",
                "top_k": settings.RETRIEVAL_TOP_K,
                "retrieval_first": True,
                "status": "published",
                "created_by": User.objects.filter(username="admin").first(),
            },
        )
        agent.knowledge_bases.set([kb])
        self.stdout.write(f"  智能体 {agent.name}（{agent.get_status_display()}）")

        # ---------------- 入库 ----------------
        if skip_index:
            self.stdout.write(self.style.WARNING("按参数要求跳过切片与向量化（--skip-index）"))
        else:
            self._index_all(kb)

        self.stdout.write(self.style.SUCCESS("\n演示数据就绪。"))
        self.stdout.write("  登录账号：admin / admin123（管理员）")
        self.stdout.write("            teacher / teacher123（教师）")
        self.stdout.write("            student / student123（学生）")

    # ------------------------------------------------------------------
    def _index_all(self, kb):
        from apps.configs.services import resolve_embedding
        from apps.knowledge.models import KnowledgeDoc
        from rag.pipeline import index_document

        try:
            provider = resolve_embedding(kb)
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(self.style.ERROR(f"向量模型不可用，跳过向量化：{exc}"))
            self.stdout.write("  补齐 backend/.env 里的 EMBEDDING_API_KEY 后执行：")
            self.stdout.write("  python manage.py seed_demo --reset")
            return

        self.stdout.write("\n开始解析与向量化…")
        for doc in KnowledgeDoc.objects.filter(knowledge_base=kb).select_related("data_resource"):
            name = doc.data_resource.name
            report = index_document(doc, provider, reindex=True)
            flag = self.style.SUCCESS("OK") if report.ok else self.style.ERROR("FAIL")
            self.stdout.write(f"  [{flag}] {name}")
            self.stdout.write(f"         {report.message}")


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def _store(src: Path, filename: str) -> str:
    """把源文件放进 MEDIA_ROOT，返回相对路径（可直接赋给 FileField）。"""
    rel = f"sources/{filename}"
    dest = Path(settings.MEDIA_ROOT) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        shutil.copyfile(src, dest)
    return rel
