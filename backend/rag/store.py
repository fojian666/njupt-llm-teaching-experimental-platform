"""切片存储：pgvector 向量召回 + 关键词召回。

放在 rag/ 下的原因：检索的「怎么取」属于 RAG 逻辑，而「从哪儿取」通过传进来的
knowledge_base_ids 决定，不写死业务规则。ORM 在方法内部延迟导入，
这个包因此可以脱离 Django 单独跑（例如离线做召回评测）。
"""
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .tokenizer import tokenize

# 关键词召回一次最多带多少个 bigram 去查 —— 太多会让 SQL 变成几百个 OR
MAX_QUERY_TERMS = 16


@dataclass
class ChunkHit:
    """一条召回结果。分数都在 0~1，方便前端展示与阈值过滤。"""

    chunk_id: int
    doc_id: int
    content: str
    chapter_path: str = ""
    source_name: str = ""
    vector_score: float = 0.0
    lexical_score: float = 0.0
    score: float = 0.0

    def to_dict(self, index: int | None = None) -> dict:
        data = {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "source_name": self.source_name,
            "chapter_path": self.chapter_path,
            "content": self.content,
            "snippet": self.content[:160],
            "score": round(self.score, 4),
            "vector_score": round(self.vector_score, 4),
            "lexical_score": round(self.lexical_score, 4),
        }
        if index is not None:
            data["index"] = index
        return data


@dataclass
class SearchResult:
    hits: list[ChunkHit] = field(default_factory=list)
    vector_count: int = 0
    lexical_count: int = 0
    note: str = ""


def _base_queryset(knowledge_base_ids: Sequence[int] | None):
    """把「有效」的定义收在一处：切片有效 + 条目有效 + 知识库启用。"""
    from apps.knowledge.models import Chunk

    qs = Chunk.objects.filter(
        is_active=True,
        knowledge_doc__is_active=True,
        knowledge_doc__knowledge_base__is_active=True,
    )
    if knowledge_base_ids:
        qs = qs.filter(knowledge_doc__knowledge_base_id__in=list(knowledge_base_ids))
    return qs


def vector_search(
    query_vector: Sequence[float],
    limit: int,
    knowledge_base_ids: Sequence[int] | None = None,
) -> list[tuple[int, float]]:
    """向量召回，返回 [(chunk_id, 余弦相似度)]。

    相似度 = 1 - 余弦距离，越大越像。HNSW 索引走 `vector_cosine_ops`，
    所以这里必须用 `CosineDistance`，用成 L2 就走不上索引了。
    """
    from pgvector.django import CosineDistance

    rows = (
        _base_queryset(knowledge_base_ids)
        .filter(embedding__isnull=False)
        .annotate(distance=CosineDistance("embedding", list(query_vector)))
        .order_by("distance")
        .values_list("id", "distance")[:limit]
    )
    return [(cid, max(0.0, min(1.0, 1.0 - float(dist or 0.0)))) for cid, dist in rows]


def _select_query_terms(query: str) -> list[str]:
    """挑出用于 SQL 关键词召回的词。

    没有 IDF 可用，就按「信息量」的朴素代理排序：**越长越好**。
    中文 bigram 里 2 字几乎都比单字有信息量，英文整词（zigbee、epcis）更长也更值钱。
    """
    terms = [t for t in dict.fromkeys(tokenize(query)) if len(t) >= 2 or t.isascii()]
    terms.sort(key=len, reverse=True)
    return terms[:MAX_QUERY_TERMS]


def lexical_candidates(
    query: str,
    limit: int,
    knowledge_base_ids: Sequence[int] | None = None,
) -> list[int]:
    """关键词召回：把含查询词的切片捞出来，返回 id 列表。

    两段式：先用 OR-of-LIKE 粗筛（能走上索引，很快），再按**命中的查询词个数**
    排序取前 N。千万别按 id 排 —— id 是插入顺序，与相关度毫无关系，
    按 id 取只会把文档末尾的参考文献、封底书目顶上来。

    真排序交给后面的 BM25，这里只负责把「有戏的候选」挑出来。
    """
    from django.db.models import Case, IntegerField, Q, Value, When

    terms = _select_query_terms(query)
    if not terms:
        return []

    cond = Q()
    for t in terms:
        cond |= Q(content__icontains=t)

    # 命中词数：每多命中一个 bigram 加一分
    score = Value(0, output_field=IntegerField())
    for t in terms:
        score = score + Case(
            When(content__icontains=t, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )

    rows = (
        _base_queryset(knowledge_base_ids)
        .filter(cond)
        .annotate(term_hits=score)
        .order_by("-term_hits", "id")
        .values_list("id", flat=True)[: limit * 4]
    )
    return list(rows)


def fetch_chunks(chunk_ids: Iterable[int]) -> dict[int, dict]:
    """按 id 取回切片详情，附带来源文件名 —— 引用面板要展示这些。"""
    from apps.knowledge.models import Chunk

    ids = list(chunk_ids)
    if not ids:
        return {}
    rows = (
        Chunk.objects.filter(id__in=ids)
        .values(
            "id",
            "content",
            "chapter_path",
            "knowledge_doc_id",
            "knowledge_doc__data_resource__name",
        )
    )
    return {
        r["id"]: {
            "chunk_id": r["id"],
            "doc_id": r["knowledge_doc_id"],
            "content": r["content"] or "",
            "chapter_path": r["chapter_path"] or "",
            "source_name": r["knowledge_doc__data_resource__name"] or "",
        }
        for r in rows
    }


def save_embeddings(
    pairs: Sequence[tuple[int, Sequence[float]]],
    batch_size: int = 64,
) -> int:
    """批量写入向量。切片是一次性生成的，所以这里不用逐条 save。"""
    from apps.knowledge.models import Chunk

    if not pairs:
        return 0

    by_id = {pk: vec for pk, vec in pairs}
    objs = list(Chunk.objects.filter(id__in=list(by_id)))
    for obj in objs:
        obj.embedding = list(by_id[obj.id])

    written = 0
    for start in range(0, len(objs), batch_size):
        batch = objs[start : start + batch_size]
        Chunk.objects.bulk_update(batch, ["embedding"], batch_size=batch_size)
        written += len(batch)
    return written


def missing_embedding_ids(knowledge_doc_id: int) -> list[int]:
    """找出还没算向量的切片 —— 断点续跑时只补这些，不必整篇重来。"""
    from apps.knowledge.models import Chunk

    return list(
        Chunk.objects.filter(knowledge_doc_id=knowledge_doc_id, embedding__isnull=True)
        .order_by("seq")
        .values_list("id", flat=True)
    )
