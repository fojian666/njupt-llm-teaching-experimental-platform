"""检索层的回归测试。

守两件历史上真出过问题的事：
1. **打分覆盖** —— 关键词分必须对所有候选计算，不能只算关键词通道自己召回的候选。
   早期实现里其余候选按 0 分参与融合，向量分最高的片段会被硬扣 (1-α) 份额而垫底；
2. **无信号通道退出融合** —— 问题用词与语料毫无字面重合时，关键词通道不参与加权，
   否则综合分被统一压到 α 倍，看上去像坏了。

向量用桩 provider 提供（所有片段向量相同），这样排序完全由关键词通道与融合逻辑决定，
测试不依赖任何外部接口。
"""
from django.conf import settings
from django.test import TestCase

from apps.datasets.models import DataResource
from apps.knowledge.models import Chunk, KnowledgeBase, KnowledgeDoc
from rag.retriever import Retriever, RetrieveOptions, _bm25_scores


class _StubEmbedding:
    """所有文本返回同一个向量：向量分全部打平，排序只看融合与关键词逻辑。"""

    name = "stub"
    model = "stub"
    dimension = settings.EMBEDDING_DIM

    def embed_one(self, text: str) -> list[float]:
        return [0.01] * settings.EMBEDDING_DIM


class Bm25NormalizationTest(TestCase):
    """BM25 归一化的边界行为。

    注意 `rank_bm25` 的 IDF 在语料很小时会变成负数（词出现在超过半数文档里时），
    全部原始分为负就落到 `hi <= 0` 的兜底分支，返回全 0。真实候选集是几十条，
    这里用 5 篇文档构造出正的 IDF。
    """

    def _corpus(self):
        return [
            "物联网的三层架构包括感知层网络层与应用层",
            "自动识别技术涵盖条码与射频识别",
            "传感器负责把物理量转换成电信号",
            "嵌入式系统在物联网终端里很常见",
            "数据库索引与查询优化的一般方法",
        ]

    def test_scores_normalized_to_one(self):
        scores = _bm25_scores("物联网三层架构", self._corpus())
        self.assertEqual(len(scores), 5)
        self.assertEqual(max(scores), 1.0)
        self.assertGreaterEqual(min(scores), 0.0)
        self.assertEqual(scores[0], max(scores))
        self.assertEqual(scores[-1], 0.0)

    def test_no_term_overlap_returns_zeros(self):
        scores = _bm25_scores("zzzqqqxxx", self._corpus())
        self.assertEqual(scores, [0.0] * 5)

    def test_empty_query_returns_zeros(self):
        self.assertEqual(_bm25_scores("", ["物联网三层架构"]), [0.0])

    def test_tiny_corpus_degenerates_to_zeros(self):
        """两篇文档时 IDF 为负，走兜底分支返回全 0 —— 记录这个已知行为，
        提醒不要用小候选集去解读关键词分。"""
        scores = _bm25_scores("物联网三层架构", ["物联网三层架构介绍", "完全无关的句子"])
        self.assertEqual(scores, [0.0, 0.0])


class FusionTest(TestCase):
    """融合打分的覆盖与权重行为。"""

    def setUp(self):
        kb = KnowledgeBase.objects.create(name="检索测试库", code="rag-test-kb")
        doc = KnowledgeDoc.objects.create(
            knowledge_base=kb, data_resource=DataResource.objects.create(name="检索测试语料")
        )
        vec = [0.01] * settings.EMBEDDING_DIM
        self.hit = Chunk.objects.create(
            knowledge_doc=doc, seq=1, embedding=vec,
            content="物联网的三层架构包括感知层、网络层与应用层", chapter_path="第一章",
        )
        self.partial = Chunk.objects.create(
            knowledge_doc=doc, seq=2, embedding=vec,
            content="物联网体系结构可以分成三层来理解", chapter_path="第一章",
        )
        self.miss = Chunk.objects.create(
            knowledge_doc=doc, seq=3, embedding=vec,
            content="本章讨论苹果与香蕉的种植技术", chapter_path="第二章",
        )
        self.kb_id = kb.id

    def _retrieve(self, query, **kw):
        opts = RetrieveOptions(knowledge_base_ids=[self.kb_id], top_k=3, **kw)
        return Retriever(_StubEmbedding()).retrieve(query, opts)

    def test_keyword_scores_cover_all_candidates(self):
        """有字面重合的候选都要拿到真实关键词分，不能因为召回路径不同被判 0。"""
        res = self._retrieve("物联网的三层架构")
        by_id = {h.chunk_id: h for h in res.hits}
        self.assertGreater(by_id[self.hit.id].lexical_score, 0)
        self.assertGreater(by_id[self.partial.id].lexical_score, 0)
        self.assertEqual(by_id[self.miss.id].lexical_score, 0)  # 真·零重合

    def test_matching_chunks_rank_above_unrelated(self):
        res = self._retrieve("物联网的三层架构")
        self.assertNotEqual(res.hits[-1].chunk_id, self.hit.id)
        self.assertGreater(res.hits[0].score, 0.5)

    def test_zero_signal_does_not_shrink_score(self):
        """全语料都没有字面重合时，综合分不应被无信号的关键词权重压低。

        两种情形都算无信号：粗筛没找到候选（lexical_ids 为空），
        或候选存在但 BM25 全 0。两种情况下排序都退化为纯向量。
        """
        res = self._retrieve("zzzqqqxxx")
        self.assertTrue(res.hits)
        for h in res.hits:
            self.assertEqual(h.lexical_score, 0.0)
            # 权重归零后综合分应等于向量分，而不是被打七折
            self.assertAlmostEqual(h.score, h.vector_score, places=6)

    def test_partial_signal_keeps_fusion(self):
        """只要有一个片段有字面重合，融合照常生效。"""
        res = self._retrieve("物联网的三层架构")
        self.assertEqual(res.note, "")

    def test_pure_vector_mode(self):
        res = self._retrieve("物联网的三层架构", alpha=1.0, use_keyword=False)
        for h in res.hits:
            self.assertEqual(h.lexical_score, 0.0)
            self.assertAlmostEqual(h.score, h.vector_score, places=6)

    def test_inactive_chunk_filtered(self):
        self.miss.is_active = False
        self.miss.save(update_fields=["is_active"])
        res = self._retrieve("苹果与香蕉")
        self.assertNotIn(self.miss.id, [h.chunk_id for h in res.hits])

    def test_deleted_doc_filtered(self):
        doc = self.hit.knowledge_doc
        doc.is_active = False
        doc.save(update_fields=["is_active"])
        res = self._retrieve("物联网的三层架构")
        self.assertNotIn(self.hit.id, [h.chunk_id for h in res.hits])
