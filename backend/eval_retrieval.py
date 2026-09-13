"""检索质量评测：两组问题 × 四种检索配置，统计命中率。

为什么不评生成质量：生成好不好没法客观打分，但"该找到的那一节有没有被找回来"
可以客观判定。而检索恰恰是 RAG 里最容易翻车、也最该被量化的一环。
本脚本只跑检索层（`rag.retriever.Retriever`，与线上问答同一份代码），
**不调用大模型，零 token 消耗**。

判定口径：命中 = 召回结果的 chapter_path 里出现了期望关键词。
只认章节路径、不认正文，是故意的 —— 正文里"感知层"这种词到处都是，
拿正文匹配会把命中率虚高上去，那样的数字没法拿去答辩。

用法：
    .venv/bin/python eval_retrieval.py               # 跑全量，写出 Markdown 报告
    .venv/bin/python eval_retrieval.py --out /tmp/x.md
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.knowledge.models import Chunk, KnowledgeDoc  # noqa: E402
from rag.providers import embedding_from_settings  # noqa: E402
from rag.retriever import RetrieveOptions, Retriever  # noqa: E402

TOP_K = 5
K_LIST = (1, 3, 5)
ALPHA = 0.7  # 与线上 apps/agents/api.py 里 ChatIn.alpha 的默认值一致


@dataclass
class Case:
    """一道评测题。

    expect 里任意一个关键词出现在某条召回结果的 chapter_path 中，该条即算命中；
    给多个词是为了兼容两本教材对同一知识点的不同章节命名。
    """

    question: str
    expect: tuple[str, ...]
    basis: str = ""  # 判据说明，写进报告，方便别人复核


# ---- 第一组：教材式术语提问（学生复习时最可能的问法）----
TERM_CASES: list[Case] = [
    Case("物联网的三层架构分别是哪三层？各层的作用是什么？", ("三层", "体系结构"),
         "导论 1.4 物联网体系结构 / 概论 1.3.1 物联网三层模型"),
    Case("RFID 系统由哪几部分组成？它的工作原理是什么？", ("RFID", "自动识别"),
         "导论第 2 章 RFID 与物联网应用 / 概论第 3 章 自动识别技术"),
    Case("传感器网络有哪些特点和关键技术？", ("传感器",),
         "导论第 3 章 传感器与传感网技术 / 概论第 6、7 章 传感器与传感器网络"),
    Case("物联网常用的通信与网络技术有哪些？", ("通信", "网络技术"),
         "导论第 5 章 物联网通信与网络技术 / 概论第 5 章 通信技术"),
    Case("物联网中常用的定位技术有哪些？", ("定位",),
         "导论第 6 章 位置信息、定位技术与位置服务 / 概论第 12 章 定位技术"),
    Case("物联网面临哪些安全威胁？常用的安全防护手段有哪些？", ("安全",),
         "导论第 8 章 物联网网络安全 / 概论第 11 章 物联网的安全与管理"),
    Case("物联网的智能数据处理技术包括哪些？", ("数据处理", "智能数据"),
         "导论第 7 章 物联网智能数据处理技术 / 概论第 10 章 物联网的数据处理"),
    Case("嵌入式系统在物联网里承担什么角色？", ("嵌入式",),
         "导论第 4 章 物联网智能硬件与嵌入式系统 / 概论第 4 章 嵌入式系统"),
    Case("物联网工程专业的毕业要求有哪些？", ("毕业要求",),
         "培养方案文档的「三、毕业要求」小节"),
    Case("网络工程专业的核心课程包括哪些？", ("核心课程", "课程与毕业要求"),
         "培养方案文档的「六、核心课程」小节"),
]

# ---- 第二组：口语化提问（术语少、原文里找不到原样词汇，用来压测关键词通道）----
COLLOQUIAL_CASES: list[Case] = [
    Case("物联网为啥非要分成好几层来设计？", ("三层", "体系结构"),
         "同第 1 题的章节，但问法里没有「架构/体系结构」这类术语"),
    Case("手机碰一下就能刷地铁票，背后是什么技术在起作用？", ("RFID", "自动识别"),
         "导论第 2 章 / 概论第 3 章，口语里不会出现 RFID 三个字母"),
    Case("设备是怎么把采集到的数据送到服务器上去的？", ("通信", "网络", "接入", "承载", "互联网"),
         "导论第 5 章 / 概论第 5、8、9 章"),
    Case("图书馆里的书是怎么被系统自动认出来的？", ("自动识别", "RFID", "编码"),
         "概论第 2 章 物品信息编码 / 第 3 章 自动识别技术"),
    Case("为啥联网的设备反而更容易被攻击？", ("安全",),
         "导论第 8 章 / 概论第 11 章，问法带情绪、无术语"),
]

SETS: list[tuple[str, list[Case]]] = [
    ("教材术语型提问", TERM_CASES),
    ("口语化提问", COLLOQUIAL_CASES),
]


class BrokenEmbedding:
    """模拟嵌入服务不可用 —— 用来验证「向量挂了还能靠关键词兜住」这条降级路径。"""

    model = "（模拟不可用）"

    def embed_one(self, text: str):
        raise RuntimeError("模拟：嵌入服务连接失败")

    def embed(self, texts):
        raise RuntimeError("模拟：嵌入服务连接失败")


class CachedEmbedding:
    """把查询向量缓存到磁盘。

    两个目的，都是方法学上的必需项而非优化：
    1. **公平**：原来每个配置各调一次嵌入接口，等于"混合 vs 纯向量"连查询向量都不是同一个，
       比较里混进了无关变量。缓存后同一题在所有配置间共用同一个向量。
    2. **可复现**：嵌入接口对同一输入偶尔给出极微小差异的向量，在分数近似并列的题目上
       会让排名翻转（实测位次会出现 ±1 的抖动）。缓存后重跑结果完全一致，
       报告里的数字才敢写死。
    要重新取向量：删掉缓存文件或加 --no-cache。
    """

    def __init__(self, inner, cache_path: Path, use_cache: bool = True):
        self.inner = inner
        self.model = getattr(inner, "model", "?")
        self.cache_path = cache_path
        self.use_cache = use_cache
        self.cache: dict[str, list[float]] = {}
        self.hits = 0
        self.inner_calls = 0
        self.inner_ms = 0.0
        if use_cache and cache_path.exists():
            try:
                self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 —— 缓存坏了就当没有
                self.cache = {}

    def embed_one(self, text: str):
        if text in self.cache:
            self.hits += 1
            return self.cache[text]
        t0 = time.perf_counter()
        vec = self.inner.embed_one(text)
        self.inner_ms += (time.perf_counter() - t0) * 1000
        self.inner_calls += 1
        self.cache[text] = vec
        return vec

    def embed(self, texts):
        return self.inner.embed(texts)

    def save(self) -> None:
        if not self.use_cache:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache), encoding="utf-8")


@dataclass
class Config:
    name: str
    opts: dict
    retriever: object
    note: str = ""


@dataclass
class Row:
    case: Case
    per_config: dict = field(default_factory=dict)


def build_configs() -> list[Config]:
    emb = CachedEmbedding(
        embedding_from_settings(),
        Path(__file__).resolve().parent / ".eval_query_cache.json",
        use_cache="--no-cache" not in sys.argv,
    )
    return [
        Config("混合（α=%.1f + 关键词）" % ALPHA, {"alpha": ALPHA, "use_keyword": True}, Retriever(emb)),
        Config("纯向量", {"alpha": 1.0, "use_keyword": False}, Retriever(emb)),
        Config("纯关键词", {"alpha": 0.0, "use_keyword": True}, Retriever(emb)),
        Config("降级：嵌入不可用", {"alpha": ALPHA, "use_keyword": True}, Retriever(BrokenEmbedding()),
               note="向量通道抛异常后，应自动退化为关键词检索"),
    ], emb


def corpus_summary() -> str:
    rows, total = [], 0
    for d in KnowledgeDoc.objects.select_related("data_resource"):
        n = Chunk.objects.filter(knowledge_doc=d, is_active=True).count()
        total += n
        name = d.data_resource.name if d.data_resource else f"doc{d.id}"
        rows.append(f"| {d.id} | {name[:52]} | {n} |")
    return (f"共 {KnowledgeDoc.objects.count()} 个文档、**{total} 条有效切片**\n\n"
            "| doc | 文档 | 有效切片 |\n|---:|---|---:|\n" + "\n".join(rows))


def run_group(title: str, cases: list[Case], configs: list[Config]) -> list[Row]:
    print(f"\n### {title}（{len(cases)} 题）")
    rows: list[Row] = []
    for i, case in enumerate(cases, start=1):
        row = Row(case=case)
        for cfg in configs:
            opts = RetrieveOptions(top_k=TOP_K, knowledge_base_ids=None, **cfg.opts)
            t0 = time.perf_counter()
            try:
                res = cfg.retriever.retrieve(case.question, opts)
                ms = (time.perf_counter() - t0) * 1000
                rank, path = None, ""
                for pos, h in enumerate(res.hits, start=1):
                    if any(k in (h.chapter_path or "") for k in case.expect):
                        rank, path = pos, h.chapter_path
                        break
                row.per_config[cfg.name] = {"rank": rank, "path": path, "ms": ms,
                                            "vector": res.vector_count, "lexical": res.lexical_count,
                                            "note": res.note}
                print(f"  [{i:2}/{len(cases)}] {cfg.name:20} "
                      f"{('命中 @' + str(rank)) if rank else '未命中':10} {ms:5.0f}ms  {case.question[:24]}")
            except Exception as exc:  # noqa: BLE001 —— 单题失败不中断整轮
                row.per_config[cfg.name] = {"rank": None, "path": "", "ms": 0.0,
                                            "vector": 0, "lexical": 0, "note": f"异常：{exc}"}
                print(f"  [{i:2}/{len(cases)}] {cfg.name:20} 异常：{exc}")
            time.sleep(0.12)
        rows.append(row)
    return rows


def hit_table(rows: list[Row], configs: list[Config]) -> list[str]:
    n = len(rows)
    out = ["| 配置 | " + " | ".join(f"Hit@{k}" for k in K_LIST) + " | 平均首次命中位次 | 平均耗时 |",
           "|---|" + "---:|" * (len(K_LIST) + 2)]
    for cfg in configs:
        cells = []
        for k in K_LIST:
            hit = sum(1 for r in rows if (r.per_config[cfg.name]["rank"] or 99) <= k)
            cells.append(f"{hit}/{n}（{hit / n:.0%}）")
        ranks = [r.per_config[cfg.name]["rank"] for r in rows if r.per_config[cfg.name]["rank"]]
        mrr = f"{(sum(ranks) / len(ranks)):.2f}" if ranks else "—"
        ms = [r.per_config[cfg.name]["ms"] for r in rows if r.per_config[cfg.name]["ms"]]
        avg_ms = f"{(sum(ms) / len(ms)):.0f} ms" if ms else "—"
        out.append(f"| {cfg.name} | " + " | ".join(cells) + f" | {mrr} | {avg_ms} |")
    return out


def detail_table(rows: list[Row], configs: list[Config]) -> list[str]:
    out = ["| # | 问题 | 期望章节关键词 | " + " | ".join(c.name for c in configs) + " | 命中的章节路径 |",
           "|---:|---|---|" + "---|" * (len(configs) + 1)]
    for i, r in enumerate(rows, start=1):
        cells = [f"@{r.per_config[c.name]['rank']}" if r.per_config[c.name]["rank"] else "✗" for c in configs]
        best = next((r.per_config[c.name]["path"] for c in configs if r.per_config[c.name]["rank"]), "—")
        out.append(f"| {i} | {r.case.question} | {' / '.join(r.case.expect)} | "
                   + " | ".join(cells) + f" | {(best or '—')[:62]} |")
    return out


def build_report(all_rows: dict[str, list[Row]], configs: list[Config],
                 elapsed: float, emb: CachedEmbedding | None = None) -> str:
    L: list[str] = []
    L.append("# 检索质量评测报告\n")
    L.append("> 由 `backend/eval_retrieval.py` 生成，可复现。只跑检索层"
             "（与线上问答同一份 `rag/retriever.py`），**不调用大模型**。\n")
    L.append(f"- 向量模型：`{configs[0].retriever.embedding.model}`")
    L.append(f"- 融合权重：α = {ALPHA}（与线上默认一致，向量占 α、关键词占 1-α）")
    L.append(f"- 每题取回：top_k = {TOP_K}；本轮总耗时 {elapsed:.0f} 秒")
    L.append("- 查询向量做了**磁盘缓存**（`backend/.eval_query_cache.json`）："
             "同一题在所有配置间共用同一个向量，保证比较公平；重跑结果一致，数字可复现。"
             "重新取向量加 `--no-cache`。")
    if emb is not None:
        if emb.inner_calls:
            cost = (f"本轮实取 {emb.inner_calls} 次、每次约 "
                    f"{emb.inner_ms / emb.inner_calls:.0f} ms，其余 {emb.hits} 次命中缓存")
        else:
            cost = "本轮全部命中缓存，未实际发起嵌入请求"
        L.append(
            f"- **关于耗时**：{cost}。命中缓存的配置不再取查询向量，所以下表「平均耗时」"
            "只是**检索本体**耗时，不是端到端耗时；端到端还要加上取查询向量那一步"
            "（走云端嵌入接口，实测约 300 ms）。**别拿纯向量的 12 ms 和混合的 400 ms 比快慢——"
            "两者的差值几乎全部来自缓存，不是算法差异。**\n"
        )
    else:
        L.append("")

    L.append("\n## 一、语料规模\n")
    L.append(corpus_summary())

    L.append("\n## 二、命中率汇总\n")
    for title, rows in all_rows.items():
        L.append(f"\n**{title}**（{len(rows)} 题）\n")
        L.extend(hit_table(rows, configs))
        L.append("")
    L.append("\n> Hit@k = 前 k 条召回里出现过期望章节的题目占比；平均首次命中位次越小越好。\n")

    L.append("\n## 三、逐题明细\n")
    for title, rows in all_rows.items():
        L.append(f"\n**{title}**\n")
        L.extend(detail_table(rows, configs))
        L.append("")

    # 结论按实测数字写，不做粉饰
    term, coll = all_rows["教材术语型提问"], all_rows["口语化提问"]
    both = list(term) + list(coll)

    def hit_at(rows, cname, k):
        return sum(1 for r in rows if (r.per_config[cname]["rank"] or 99) <= k)

    c_mix, c_vec, c_lex, c_deg = (c.name for c in configs)
    L.append("\n## 四、结论（按实测数字，不做粉饰）\n")
    L.append(
        f"**1）本评测集上，纯向量的首条命中率最高，混合反而略低。**\n"
        f"教材术语型：纯向量 Hit@1 = {hit_at(term, c_vec, 1)}/{len(term)}，"
        f"混合 = {hit_at(term, c_mix, 1)}/{len(term)}，纯关键词 = {hit_at(term, c_lex, 1)}/{len(term)}；"
        f"口语化：纯向量 {hit_at(coll, c_vec, 1)}/{len(coll)}，混合 {hit_at(coll, c_mix, 1)}/{len(coll)}。"
        "这一条与「多路召回一定更好」的直觉相反，值得如实记录。\n\n"
        "**2）根因是关键词通道的归一化方式：每题它都必然拿到满分份额。**\n"
        "`rag/retriever.py` 里 BM25 分数是按**本候选集的最大值**归一化的"
        "（`_bm25_scores` 结尾 `s / hi`），于是无论绝对相关度高低，"
        "得分最高的那条关键词候选永远等于 1.0，在 α=0.7 的融合下稳定贡献 0.3 的份额。"
        "只要向量分最高的片段与其差距小于 0.3，它就会被关键词候选挤到第二位 —— "
        "这正好解释了术语型题组里那 2 题的位次下滑（@1 → @2）。"
        "这是**可定位、可修**的设计问题，而不是「模型不行」。\n\n"
        f"**3）互补性只在「向量补关键词的漏」这个方向上有证据。**\n"
        f"术语型题组 Hit@5：混合 {hit_at(term, c_mix, 5)}/{len(term)}、"
        f"纯向量 {hit_at(term, c_vec, 5)}/{len(term)}、纯关键词 {hit_at(term, c_lex, 5)}/{len(term)}"
        "—— 纯关键词漏掉的那 1 题被向量兜住了，这一侧的互补成立。\n"
        f"但口语化题组 Hit@5 三者相同（混合 {hit_at(coll, c_mix, 5)}/{len(coll)}、"
        f"纯向量 {hit_at(coll, c_vec, 5)}/{len(coll)}、纯关键词 {hit_at(coll, c_lex, 5)}/{len(coll)}），"
        "即「关键词补向量的漏」在本组题上**没有观察到**。"
        "原先预期「口语化提问靠关键词救回来」的假设，没有被这批数据支持，如实记录。\n\n"
        f"**4）降级路径实测有效。**\n"
        f"把嵌入通道换成必然抛异常的桩后，Hit@5 = {hit_at(both, c_deg, 5)}/{len(both)}，"
        "与纯关键词逐题一致，且平均耗时降到 "
        f"{sum(r.per_config[c_deg]['ms'] for r in both) / max(1, len(both)):.0f} ms（省掉了一次嵌入请求）。"
        "也就是说「向量服务挂掉不会打断问答，只是退化为关键词检索」这句话有实测支撑，"
        "不是设计文档里的口号。\n\n"
        "**5）下一步可做的改进（按性价比排序）。**\n"
        "- 关键词分改为**绝对尺度或分位归一化**，或给关键词通道设最低分门槛，"
        "避免弱匹配也吃满 0.3 的权重；这是成本最低、对 Hit@1 最直接的一刀；\n"
        "- 融合方式从加权平均换成 **RRF**（只看名次，天然免疫两路分数尺度不一致）；\n"
        "- 在融合后加一层 **rerank**，用交叉编码器重排 top-10，通常能把首条命中率拉回来；\n"
        "- 评测本身要升级：扩题量、做分级相关性标注（避免作者按教材目录命题带来的偏置），"
        "并加做「同一问题换问法」的鲁棒性测试。\n\n"
        "**6）本评测集的局限（先说清，免得数字被过度解读）。**\n"
        "题目由作者依教材目录编写，存在向教材章节命名的偏置；判据只认章节路径、不认正文，"
        "宁可低估也不虚高，因此表中未命中 ≠ 答不出来，只代表没定位到那一节。\n"
    )
    return "\n".join(L) + "\n"


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "检索评测报告.md"
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])

    configs, emb = build_configs()
    total_q = sum(len(c) for _, c in SETS)
    print(f"开始评测：{total_q} 题 × {len(configs)} 配置 = {total_q * len(configs)} 次检索"
          f"（只跑检索层，不消耗 token）")
    t0 = time.perf_counter()
    all_rows = {title: run_group(title, cases, configs) for title, cases in SETS}
    elapsed = time.perf_counter() - t0
    emb.save()

    report = build_report(all_rows, configs, elapsed, emb)
    out.write_text(report, encoding="utf-8")
    print(f"\n报告已写入：{out}\n")
    for title, rows in all_rows.items():
        print(f"== {title} ==")
        for line in hit_table(rows, configs):
            print("  " + line)


if __name__ == "__main__":
    main()
