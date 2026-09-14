"""接口层的回归测试。

这一层专门守「结构不被无意破坏」，都是这几类：
1. **路由可达性** —— 字面路由必须能命中，不被 /{id} 动态路由抢走（历史上 batch-delete
   与 batch-parse 都因此静默返回 405，界面上一直没人点过）；
2. **必填校验** —— 空字符串要 422，而不是建出一条空名记录；
3. **权限边界** —— 学生账号不能碰管理接口；
4. **软删除不变量** —— 删掉的数据不能再出现在列表/统计里。

测试不依赖外部模型接口：需要向量的地方一律用假 provider。
"""
from django.test import TestCase

from apps.accounts.models import User
from apps.agents.models import Agent, Message
from apps.common.tasks import run_task
from apps.datasets.models import DataCategory, DataResource
from apps.knowledge.models import Chunk, KnowledgeBase, KnowledgeDoc


class RouteReachabilityTest(TestCase):
    """字面路由不能被动态路由遮蔽：POST 到 /resources/batch-* 必须是 200/400/403，
    绝不能是 405 Method Not Allowed。"""

    def setUp(self):
        self.admin = User.objects.create_user(username="t_admin", password="pw123456", role="admin")
        self.client.force_login(self.admin)

    def test_batch_endpoints_are_reachable(self):
        cases = [
            ("/api/datasets/resources/batch-parse", {"ids": []}),
            ("/api/datasets/resources/batch-tags", {"ids": []}),
            ("/api/datasets/resources/batch-move", {"ids": [], "category_id": 0}),
        ]
        for path, payload in cases:
            with self.subTest(path=path):
                resp = self.client.post(path, payload, content_type="application/json")
                self.assertNotEqual(resp.status_code, 405, f"{path} 被动态路由遮蔽了")

    def test_resource_detail_route_still_works(self):
        r = DataResource.objects.create(name="路由测试数据", file_format="txt")
        resp = self.client.get(f"/api/datasets/resources/{r.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "路由测试数据")

    def test_upload_route_is_not_shadowed(self):
        # 上传是 multipart，这里只验证路由能被解析到（不是 405）
        resp = self.client.post("/api/datasets/resources/upload")
        self.assertNotEqual(resp.status_code, 405)


class RequiredFieldTest(TestCase):
    """空字符串必须被拦下：这是「新建了一个空名字的东西」的来源。"""

    def setUp(self):
        self.admin = User.objects.create_user(username="t_admin2", password="pw123456", role="admin")
        self.client.force_login(self.admin)

    def test_empty_names_rejected(self):
        cases = [
            ("/api/agents/", {"name": ""}),
            ("/api/datasets/categories", {"name": ""}),
            ("/api/knowledge/bases", {"name": ""}),
            ("/api/datasets/tags", {"name": ""}),
        ]
        for path, payload in cases:
            with self.subTest(path=path):
                resp = self.client.post(path, payload, content_type="application/json")
                self.assertEqual(resp.status_code, 422, f"{path} 应拒绝空 name")

    def test_whitespace_only_name_rejected(self):
        resp = self.client.post("/api/agents/", {"name": "   "}, content_type="application/json")
        self.assertEqual(resp.status_code, 422)

    def test_provider_requires_base_url(self):
        resp = self.client.post(
            "/api/configs/providers",
            {"name": "x", "code": "x1", "base_url": ""},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 422)


class RateLimitTest(TestCase):
    """聊天限流：超限要返回 429，且要在调用模型之前就拦住。"""

    def setUp(self):
        from apps.agents.models import Agent

        self.user = User.objects.create_user(username="t_rl", password="pw123456", role="student")
        self.client.force_login(self.user)
        self.agent = Agent.objects.create(name="限流测试智能体", code="rate-agent")

    def _seed_counter(self, n: int) -> None:
        """直接把本分钟的计数写成 n，省得为了触发限流真的去打模型接口。"""
        import time

        from django.core.cache import cache

        key = f"ratelimit:chat:{self.user.id}:{int(time.time() // 60)}"
        cache.set(key, n, timeout=70)

    def test_over_limit_returns_429_without_touching_model(self):
        from django.test import override_settings

        with override_settings(CHAT_RATE_LIMIT_PER_MINUTE=5):
            self._seed_counter(5)  # 本分钟已用满
            resp = self.client.post(
                f"/api/agents/{self.agent.id}/chat",
                {"question": "限流测试"},
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 429)
        self.assertIn("过于频繁", resp.json()["detail"])

    def test_helper_counts_per_minute(self):
        from django.test import override_settings
        from ninja.errors import HttpError

        from apps.common.api import check_rate_limit

        request = type("R", (), {"user": self.user})()

        class _Req:
            pass

        req = _Req()
        req.user = self.user
        with override_settings(CHAT_RATE_LIMIT_PER_MINUTE=2):
            check_rate_limit(req, "unit-test", 2)
            check_rate_limit(req, "unit-test", 2)
            with self.assertRaises(HttpError) as ctx:
                check_rate_limit(req, "unit-test", 2)
        self.assertEqual(ctx.exception.status_code, 429)

    def test_zero_limit_means_unlimited(self):
        from apps.common.api import check_rate_limit

        req = type("Req", (), {"user": self.user})()
        for _ in range(50):
            check_rate_limit(req, "unlimited-test", 0)  # 不抛异常即为通过


class AbuseGuardTest(TestCase):
    """对抗性检查守住的几条线：输入长度、批量条数、跨用户归属。"""

    def setUp(self):
        from apps.agents.models import Agent, Conversation

        self.admin = User.objects.create_user(username="t_abuse", password="pw123456", role="admin")
        self.other = User.objects.create_user(username="t_other", password="pw123456", role="student")
        self.agent = Agent.objects.create(name="越权测试智能体", code="abuse-agent")
        self.conv = Conversation.objects.create(agent=self.agent, user=self.other, title="别人的会话")
        self.msg = Message.objects.create(conversation=self.conv, role=Message.Role.ASSISTANT, content="别人的回答")
        self.client.force_login(self.admin)

    def test_question_length_capped(self):
        """超长问题必须在 schema 层被拒，不能原样送去调模型。"""
        resp = self.client.post(
            f"/api/agents/{self.agent.id}/chat",
            {"question": "啊" * 5000},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 422)

    def test_empty_question_rejected(self):
        resp = self.client.post(
            f"/api/agents/{self.agent.id}/chat", {"question": "   "}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 422)

    def test_batch_size_capped(self):
        from apps.datasets.api import MAX_BATCH_IDS

        too_many = list(range(1, MAX_BATCH_IDS + 2))
        for path, payload in [
            ("/api/datasets/resources/batch-parse", {"ids": too_many}),
            ("/api/datasets/resources/batch-tags", {"ids": too_many, "tags": ["x"]}),
            ("/api/datasets/resources/batch-move", {"ids": too_many, "category_id": 0}),
            ("/api/datasets/resources/batch-delete", {"ids": too_many}),
        ]:
            with self.subTest(path=path):
                resp = self.client.post(path, payload, content_type="application/json")
                self.assertEqual(resp.status_code, 400, f"{path} 应拒绝超量 ids")

    def test_batch_size_at_limit_passes(self):
        from apps.datasets.api import MAX_BATCH_IDS

        ids = list(range(1, MAX_BATCH_IDS + 1))
        resp = self.client.post(
            "/api/datasets/resources/batch-parse", {"ids": ids}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)

    def test_cannot_rate_someone_elses_message(self):
        """评价别人的回答要拒绝，否则满意度统计可被任何人篡改。"""
        resp = self.client.post(
            f"/api/agents/messages/{self.msg.id}/feedback",
            {"rating": "like"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_can_rate_own_message(self):
        from apps.agents.models import Conversation

        own = Conversation.objects.create(agent=self.agent, user=self.admin, title="自己的会话")
        mine = Message.objects.create(conversation=own, role=Message.Role.ASSISTANT, content="自己的回答")
        resp = self.client.post(
            f"/api/agents/messages/{mine.id}/feedback",
            {"rating": "like"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_batch_move_requires_explicit_clear(self):
        """目标分类留空不能静默清空分类：必须显式 clear=true。

        实测教训：带 category_id=0 的批量移动会把目标数据的分类全部清空，
        前端下拉框没选就点确认，等于一次静默的数据损坏。
        """
        r = DataResource.objects.create(name="有分类的数据", category=DataCategory.objects.create(name="临时分类"))
        resp = self.client.post(
            "/api/datasets/resources/batch-move",
            {"ids": [r.id], "category_id": 0},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        r.refresh_from_db()
        self.assertIsNotNone(r.category)  # 分类还在

        ok = self.client.post(
            "/api/datasets/resources/batch-move",
            {"ids": [r.id], "category_id": 0, "clear": True},
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200)
        r.refresh_from_db()
        self.assertIsNone(r.category)  # 显式确认后才真的移出

    def test_unauthenticated_gets_401(self):
        self.client.logout()
        for method, path in [
            ("get", "/api/datasets/resources"),
            ("post", "/api/datasets/resources/batch-delete"),
            ("get", "/api/agents/6/conversations"),
            ("delete", "/api/knowledge/chunks/1"),
        ]:
            with self.subTest(path=path):
                resp = getattr(self.client, method)(path, {}, content_type="application/json")
                self.assertEqual(resp.status_code, 401, f"{method} {path} 未登录应为 401")

    def test_like_wildcards_are_escaped(self):
        """搜索里的 % 与 _ 要当普通字符，否则一个 % 就能把全库拉出来。"""
        DataResource.objects.create(name="普通数据")
        for kw in ["%", "_"]:
            with self.subTest(kw=kw):
                resp = self.client.get("/api/datasets/resources", {"keyword": kw})
                self.assertEqual(resp.json()["total"], 0)


class EmbeddingDimGuardTest(TestCase):
    """向量模型维度与数据库列不一致时要在保存配置那一刻就报错。"""

    def setUp(self):
        from apps.configs.models import ModelProvider

        self.admin = User.objects.create_user(username="t_admin3", password="pw123456", role="admin")
        self.client.force_login(self.admin)
        self.provider = ModelProvider.objects.create(name="测试供应商", code="testprov", base_url="https://x.test/v1")

    def test_wrong_dimension_rejected(self):
        from django.conf import settings

        wrong = int(settings.EMBEDDING_DIM) + 1
        resp = self.client.post(
            "/api/configs/models",
            {"provider_id": self.provider.id, "name": "错维度向量", "model_id": "bad-embed",
             "kind": "embedding", "dimension": wrong},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("维度", resp.json()["detail"])

    def test_missing_dimension_rejected(self):
        resp = self.client.post(
            "/api/configs/models",
            {"provider_id": self.provider.id, "name": "缺维度向量", "model_id": "no-dim",
             "kind": "embedding"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


class PermissionBoundaryTest(TestCase):
    """学生账号碰管理接口要被拦住，读接口不受影响。"""

    def setUp(self):
        self.student = User.objects.create_user(username="t_stu", password="pw123456", role="student")
        self.client.force_login(self.student)
        self.resource = DataResource.objects.create(name="学生不该改的数据")

    def test_student_cannot_manage(self):
        cases = [
            ("post", "/api/datasets/resources/batch-parse", {"ids": [self.resource.id]}),
            ("post", "/api/datasets/resources/batch-move", {"ids": [self.resource.id], "category_id": 0}),
            ("delete", f"/api/datasets/resources/{self.resource.id}", None),
            ("patch", f"/api/datasets/resources/{self.resource.id}", {"name": "改名"}),
            ("delete", f"/api/knowledge/chunks/1", None),
        ]
        for method, path, payload in cases:
            with self.subTest(path=f"{method} {path}"):
                resp = getattr(self.client, method)(
                    path, payload or {}, content_type="application/json"
                )
                self.assertIn(resp.status_code, (401, 403), f"{method} {path} 应拒绝学生")

    def test_student_can_read(self):
        resp = self.client.get("/api/datasets/resources")
        self.assertEqual(resp.status_code, 200)


class SoftDeleteInvariantTest(TestCase):
    """删掉的数据不能还留在列表与统计里。"""

    def setUp(self):
        self.admin = User.objects.create_user(username="t_admin4", password="pw123456", role="admin")
        self.client.force_login(self.admin)

    def test_deleted_resource_disappears(self):
        r = DataResource.objects.create(name="待删数据")
        self.assertEqual(self.client.get("/api/datasets/stats").json()["total"], 1)

        resp = self.client.delete(f"/api/datasets/resources/{r.id}")
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(self.client.get("/api/datasets/stats").json()["total"], 0)
        listed = self.client.get("/api/datasets/resources").json()["items"]
        self.assertEqual([x["name"] for x in listed], [])

    def test_inactive_chunk_is_not_retrievable(self):
        """「是否有效」开关必须真的影响检索：关掉就该被检索层过滤掉。"""
        from rag.store import _base_queryset

        kb = KnowledgeBase.objects.create(name="测试库", code="testkb")
        doc = KnowledgeDoc.objects.create(knowledge_base=kb, data_resource=DataResource.objects.create(name="语料"))
        active = Chunk.objects.create(knowledge_doc=doc, content="有效切片", seq=1)
        inactive = Chunk.objects.create(knowledge_doc=doc, content="已下线切片", seq=2, is_active=False)

        ids = set(_base_queryset(None).values_list("id", flat=True))
        self.assertIn(active.id, ids)
        self.assertNotIn(inactive.id, ids)


class TaskPoolTest(TestCase):
    """后台任务的调度方式：不能一个任务起一个线程。"""

    def test_run_task_uses_bounded_pool(self):
        from apps.common import tasks

        done = []

        def job(x):
            done.append(x)

        mode = run_task(job, 1)
        self.assertEqual(mode, "pool")
        tasks._queue.join()  # 等任务跑完
        self.assertEqual(done, [1])
        # 工作线程数不超过配置上限
        self.assertLessEqual(len(tasks._workers), tasks._max_workers())


class AgentStatsTest(TestCase):
    """页头统计口径：软删除会话不计，提问只数用户消息。"""

    def setUp(self):
        self.user = User.objects.create_user(username="t_u", password="pw123456", role="student")
        self.client.force_login(self.user)
        self.agent = Agent.objects.create(name="统计测试智能体", code="stats-agent")
        from apps.agents.models import Conversation

        conv = Conversation.objects.create(agent=self.agent, user=self.user, title="会话一")
        Message.objects.create(conversation=conv, role=Message.Role.USER, content="问一")
        Message.objects.create(conversation=conv, role=Message.Role.ASSISTANT, content="答一")
        Message.objects.create(conversation=conv, role=Message.Role.USER, content="问二")

    def test_counts(self):
        data = self.client.get(f"/api/agents/{self.agent.id}").json()
        self.assertEqual(data["conversation_count"], 1)
        self.assertEqual(data["message_count"], 2)  # 只数用户消息

    def test_deleted_conversation_not_counted(self):
        from apps.agents.models import Conversation

        conv = Conversation.objects.filter(agent=self.agent).first()
        conv.is_deleted = True
        conv.save(update_fields=["is_deleted"])
        data = self.client.get(f"/api/agents/{self.agent.id}").json()
        self.assertEqual(data["conversation_count"], 0)
        self.assertEqual(data["message_count"], 0)


class CategoryTreeSerializationTest(TestCase):
    """分类树接口要能把两层结构正确串起来（value-key 相关的前端坑就靠这个守着）。"""

    def setUp(self):
        self.admin = User.objects.create_user(username="t_admin5", password="pw123456", role="admin")
        self.client.force_login(self.admin)

    def test_tree_nesting(self):
        parent = DataCategory.objects.create(name="一级")
        child = DataCategory.objects.create(name="二级", parent=parent)
        DataResource.objects.create(name="挂在子分类下", category=child)

        roots = self.client.get("/api/datasets/categories").json()
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0]["name"], "一级")
        self.assertEqual(roots[0]["children"][0]["name"], "二级")
        self.assertEqual(roots[0]["children"][0]["resource_count"], 1)
