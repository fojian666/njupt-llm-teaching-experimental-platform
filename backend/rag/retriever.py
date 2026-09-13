"""混合检索器：向量召回 + 关键词召回，融合后给出最终排序。

为什么不只用向量：
- 纯向量对**专有名词**很弱 —— "ZigBee"、"EPCIS"、"6LoWPAN" 这类词在嵌入空间里挤成一团，
  而学生问的偏偏就是这些词；
- 纯关键词对**口语化提问**很弱 —— "物联网为啥要分层" 这种问法里没有一个词能在原文里原样出现。
两者互补，融合后才既扛得住术语又扛得住白话。

为什么融合用加权而不是 RRF：两路分数都归一化到了 0~1，加权可解释、好调；
RRF 只看名次，丢掉了「有多像」这个信息，阈值过滤就无从下手了。
"""
from dataclasses import dataclass, field
from typing import Sequence

from .store import ChunkHit, SearchResult, fetch_chunks, lexical_candidates, vector_search
from .tokenizer import tokenize

DEFAULT_ALPHA = 0.7  # 向量分权重；剩下的给关键词
RECALL_MULTIPLIER = 4  # 召回阶段多取一些，融合后再截断到 top_k


@dataclass
class RetrieveOptions:
    top_k: int = 5
    score_threshold: float = 0.0
    knowledge_base_ids: Sequence[int] | None = None
    alpha: float = DEFAULT_ALPHA
    use_keyword: bool = True

    def normalized(self) -> "RetrieveOptions":
        top_k = max(1, min(int(self.top_k or 5), 50))
        alpha = min(1.0, max(0.0, float(self.alpha)))
        return RetrieveOptions(
            top_k=top_k,
            score_threshold=max(0.0, float(self.score_threshold or 0.0)),
            knowledge_base_ids=list(self.knowledge_base_ids or []) or None,
            alpha=alpha,
            use_keyword=bool(self.use_keyword),
        )


def _bm25_scores(query: str, docs: list[str]) -> list[float]:
    """对候选集算 BM25 分数并归一化到 0~1。

    候选集只有几十条，构索引的开销可以忽略。rank-bm25 万一不可用就退化成
    词项重合度 —— 效果差一些，但不会因为一个依赖缺失就把整条问答链路打断。
    """
    q_tokens = tokenize(query)
    if not q_tokens or not docs:
        return [0.0] * len(docs)

    try:
        from rank_bm25 import BM25Okapi

        corpus = [tokenize(d) or [""] for d in docs]
        raw = list(BM25Okapi(corpus).get_scores(q_tokens))
    except Exception:  # noqa: BLE001 —— 兜底路径，任何异常都不该让检索挂掉
        q_set = set(q_tokens)
        raw = [
            len(q_set & set(tokenize(d))) / max(1, len(q_set))
            for d in docs
        ]

    hi = max(raw) if raw else 0.0
    if hi <= 0:
        return [0.0] * len(raw)
    return [max(0.0, s) / hi for s in raw]


class Retriever:
    """检索器。embedding 只用来把问题转成向量，检索本身全在 SQL 里。"""

    def __init__(self, embedding_provider):
        self.embedding = embedding_provider

    def retrieve(self, query: str, options: RetrieveOptions | None = None) -> SearchResult:
        opts = (options or RetrieveOptions()).normalized()
        query = (query or "").strip()
        if not query:
            return SearchResult(note="问题为空")

        recall = opts.top_k * RECALL_MULTIPLIER
        result = SearchResult()

        # ---- 第一路：向量召回 ----
        vector_rank: dict[int, float] = {}
        try:
            query_vector = self.embedding.embed_one(query)
            for cid, score in vector_search(query_vector, recall, opts.knowledge_base_ids):
                vector_rank[cid] = score
        except Exception as exc:  # noqa: BLE001 —— 向量挂了还能靠关键词兜住
            result.note = f"向量召回不可用（{exc}），已退化为关键词检索。"

        # ---- 第二路：关键词召回 ----
        # 粗筛规模维持原样（top_k × 4）；精排统一放在融合前对所有候选做，
        # 而不是只给关键词通道自己召回的候选算分。
        lexical_ids: list[int] = []
        if opts.use_keyword:
            try:
                lexical_ids = lexical_candidates(query, opts.top_k, opts.knowledge_base_ids)
            except Exception as exc:  # noqa: BLE001
                result.note = (result.note + f" 关键词召回不可用（{exc}）。").strip()

        result.vector_count = len(vector_rank)
        result.lexical_count = len(lexical_ids)

        # ---- 融合 ----
        all_ids = list(dict.fromkeys([*vector_rank, *lexical_ids]))
        if not all_ids:
            return result

        details = fetch_chunks(all_ids)

        # 关键词分数对全部候选统一计算。此前只给关键词通道自己召回的候选打分，
        # 其余候选按 0 分参与融合——向量分再高的片段也会被硬扣 (1-α) 份额，
        # 综合分因此失真（实测：向量分全场最高的片段综合分垫底）。
        lexical_rank: dict[int, float] = {}
        if lexical_ids:
            scored_ids = [cid for cid in all_ids if cid in details]
            scores = _bm25_scores(query, [details[cid]["content"] for cid in scored_ids])
            lexical_rank = dict(zip(scored_ids, scores))

        w_vector = opts.alpha if vector_rank else 0.0
        w_lexical = (1.0 - opts.alpha) if lexical_rank else 0.0
        if w_vector + w_lexical == 0:
            w_vector = 1.0

        hits: list[ChunkHit] = []
        for cid in all_ids:
            info = details.get(cid)
            if not info:
                continue
            v = vector_rank.get(cid, 0.0)
            l = lexical_rank.get(cid, 0.0)
            hits.append(
                ChunkHit(
                    chunk_id=cid,
                    doc_id=info["doc_id"],
                    content=info["content"],
                    chapter_path=info["chapter_path"],
                    source_name=info["source_name"],
                    vector_score=v,
                    lexical_score=l,
                    score=(w_vector * v + w_lexical * l) / (w_vector + w_lexical),
                )
            )

        hits.sort(key=lambda h: (-h.score, h.chunk_id))
        if opts.score_threshold > 0:
            hits = [h for h in hits if h.score >= opts.score_threshold]
        result.hits = hits[: opts.top_k]
        return result


def citations_from_hits(hits: Sequence[ChunkHit]) -> list[dict]:
    """把召回结果转成「引用来源」的结构，编号从 1 开始与提示词里的 [1][2] 对齐。"""
    return [h.to_dict(index=i) for i, h in enumerate(hits, start=1)]
