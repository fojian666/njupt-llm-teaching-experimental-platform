"""纯文本 / Markdown 解析器。

OCR 产出的教材文本走这里 —— 关键是从行首编号里还原章节层级，
这样切片才能带上 "第1章 物联网概论 > 1.4 物联网体系结构" 这样的溯源路径。
"""
import re

from .base import ParseResult, join_heading

# Markdown 标题
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# "第1章 物联网概论" / "第三节 调研地区现状分析" / "第2章 RFID 与物联网应用"
# 章/节后首个有效字符必须是汉字或拉丁字母：
#   允许字母 —— 章名可能以缩写开头（RFID、5G 之类的 "RFID" 就在本书第 2 章）
#   排除数字 —— 挡住 OCR 页眉残留的 "第1章6  11" 这类噪声
_ZH_CHAPTER = re.compile(r"^第\s*[0-9一二三四五六七八九十百零]{1,4}\s*[章节][\s:：]*[A-Za-z\u4e00-\u9fff]")
# "1.4 物联网体系结构" / "1.4.1 基本概念"（必须带点，避免把 "1.为什么要…" 误判成标题）
_NUM_HEADING = re.compile(r"^(\d+(?:\.\d+){1,3})\s+\S")
# "一、" / "（一）" 这类中文序号
_ZH_NUM = re.compile(r"^[（(]?[一二三四五六七八九十]{1,3}[）)]?\s*[、.．]\s*\S")
# 目录条目：以 "/页码" 结尾，或用点线引导到页码
_TOC_ENTRY = re.compile(r"^.{2,90}?(?:[／/]\s*\d{1,4}|[.．·…]{3,}\s*\d{1,4})\s*$")
_TOC_TITLE = re.compile(r"^目\s*录$")

MAX_HEADING_LEN = 60

# 纯页码行，如 "25"、"＄ 25"、"· 12"
_PAGE_NOISE = re.compile(r"^[＄$·•\-\s]*\d{1,4}\s*$")

# 文档行数超过该值才启样板行过滤 —— 短文档本来就没有页眉页脚
BOILERPLATE_MIN_LINES = 400


# 归一化时抹掉的噪声字符（空白与标点）
_NOISE_CHARS = re.compile(r"[\s。．·•,，、．.＄$'\"“”‘’()（）\[\]【】\-—_/／:：;；!！?？]+")


def _norm_key(text: str) -> str:
    """把同一页眉的不同 OCR 变体归一到同一个键。

    页眉常被识别成 "第1章 。5" 与 "第1章。5" 两行，只差一个空格或标点，
    精确字符串匹配抓不到它们，归一化之后才能正确按频次过滤。
    """
    return _NOISE_CHARS.sub("", text)


def _strip_boilerplate(lines: list[str]) -> list[str]:
    """剔除 OCR 留下的页眉页脚。

    扫描件每页都会重复「第1章 / 页码 / 书名」这类行，它们会被标题识别规则误判成标题，
    污染章节路径。判据很直接：**短行 + 高频重复** —— 正文句子不可能在一本书里出现几十次。
    """
    from collections import Counter

    if len(lines) < BOILERPLATE_MIN_LINES:
        return lines

    counts: Counter[str] = Counter()
    for line in lines:
        stripped = line.strip()
        if 0 < len(stripped) <= 40:
            counts[_norm_key(stripped)] += 1

    threshold = max(12, int(len(lines) * 0.002))
    boilerplate = {key for key, n in counts.items() if n >= threshold and key}

    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _PAGE_NOISE.match(stripped) or _norm_key(stripped) in boilerplate:
            continue
        cleaned.append(line)
    return cleaned


def _is_toc_line(line: str) -> bool:
    """目录条目（"1.4 物联网体系结构/25"、"1.1 …… 1"）。

    这类行会被标题规则命中并打乱整棵标题栈 —— 按 "第1章/1 > 1.5 …/44 > 1.1.2 …/3"
    这种顺序污染后面所有正文的章节路径，必须提前剔掉。
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 100:
        return False
    return bool(_TOC_ENTRY.match(stripped) or _TOC_TITLE.match(stripped))


# OCR 产物里的分页标记，形如 "===== 第 12 页 ====="
_PAGE_MARK = re.compile(r"^=+\s*第\s*\d+\s*页\s*=+$")
# 句末标点 —— 目录条目不会有
_SENTENCE_TAIL = ("。", "！", "？", "；", "：", "，", ",", ".", ")", "）")
# 编号式标题开头
_NUMBERED_START = re.compile(r"^(?:\d+(?:\.\d+)*\s|第\s*[0-9]+\s*[章节]|[一二三四五六七八九十]{1,3}\s*[、.．])")


def _split_pages(lines: list[str]) -> list[list[str]] | None:
    """按分页标记切页。没有标记则返回 None（退化为整篇处理）。"""
    pages: list[list[str]] = []
    current: list[str] = []
    found = False
    for line in lines:
        if _PAGE_MARK.match(line.strip()):
            found = True
            pages.append(current)
            current = []
        else:
            current.append(line)
    pages.append(current)
    return pages if found else None


def _page_looks_like_toc(page: list[str]) -> bool:
    """整页判定目录。

    只认一条判据：**页码引用密度** —— 目录页大量出现 "1.4 物联网体系结构/25"、
    "物联网应用层/40" 这种 "标题 + 页码" 的行，正文页里这个比例几乎为零。

    故意不做"短行占比"这类统计兜底：正文页在 OCR 后同样会有大量短行（图注、编号条目），
    用它会把正常正文整页丢掉 —— 漏掉一页目录只是少个导航，丢掉一页正文是真丢知识。
    """
    texts = [l.strip() for l in page if l.strip()]
    if len(texts) < 8:
        return False

    refs = sum(1 for t in texts if len(t) <= 90 and _TOC_ENTRY.match(t))
    return refs >= 6 and refs / len(texts) >= 0.15


def _drop_toc_pages(lines: list[str]) -> tuple[list[str], int]:
    """丢掉落整页的目录 / 索引页，返回 (清洗后的行, 丢弃页数)。"""
    pages = _split_pages(lines)
    if pages is None:
        return lines, 0

    kept: list[str] = []
    dropped_pages = 0
    for page in pages:
        if _page_looks_like_toc(page):
            dropped_pages += 1
            continue
        kept.extend(page)
    return kept, dropped_pages


# 页眉里的裸章号："第1章"
_BARE_CHAPTER = re.compile(r"^第\s*([0-9]{1,2})\s*章\s*(.*)$")
# 一级章标题行（用于清洗与去重）
_CHAPTER_HEADING = re.compile(r"^第\s*([0-9]{1,2})\s*章\s*(.*)$")
# 汉字 —— 用来挡掉 OCR 页眉里的零碎符号与页码残渣
_CJK = re.compile(r"[\u4e00-\u9fff]")
# 行首噪声：OCR 常在章标题前粘上项目符号、页码碎片或装饰符号
# （"•第2章。RFID 与物联网应用"、"＄ 第3章 …"），剥掉后才是规整的标题
_LEAD_JUNK = re.compile(r"^[^\u4e00-\u9fffA-Za-z0-9]*")
# 章名首尾要剥掉的标点
_EDGE_PUNCT = " -—·.。．、,，:：;"

# 前后附页的标题。这些页不属于任何编号章节，必须让它们单独成节点，
# 否则正文会挂到上一章最后一个小节下面 —— 「参考文献」被标成「9.9.4 大型智能物流系统的设计方法」
# 就是这么来的，引用来源一旦这么写就完全不可信了。
_SPECIAL_TITLES = {
    "前言", "序言", "内容简介", "目录", "参考文献", "参考书目", "附录",
    "索引", "后记", "致谢", "结语", "推荐阅读", "教学建议", "习题答案",
    "选择题答案", "出版说明", "作者简介", "译者序", "编委会",
}
_SPECIAL_MAX_LEN = 8


def _special_heading(line: str) -> str:
    """识别前后附页标题（只认「整行就是这几个字」的情况）。

    判据是**全行只剩这几个汉字**，所以正文里出现「参考文献」四个字不会被误判 ——
    正文句子长得多，去除非汉字字符后长度必然超过限制。
    """
    key = re.sub(r"[^\u4e00-\u9fff]+", "", line)
    if 2 <= len(key) <= _SPECIAL_MAX_LEN and key in _SPECIAL_TITLES:
        return key
    return ""


def _clean_chapter_title(line: str) -> str:
    """洗净章标题 —— OCR 常把页眉页码粘在章名后面（"第9章 物联网应用277"），
    有时还会在章号前粘上项目符号或在章号后留下一个句号（"•第2章。RFID 与物联网应用"）。

    只处理章标题这一种行：正文里的数字不能被吞掉。
    """
    line = _LEAD_JUNK.sub("", line.strip())
    m = _CHAPTER_HEADING.match(line)
    if not m:
        return line
    rest = re.sub(r"[\s\d]{1,6}$", "", m.group(2)).strip(_EDGE_PUNCT)
    return f"第{m.group(1)}章 {rest}" if rest else f"第{m.group(1)}章"


def _scan_chapter_title(page_lines: list[str], start: int) -> str:
    """从页眉或章首页还原章节标题。

    OCR 把章标题搞成了好几种形态，都要认：
      "第1章。5" + "物联网概论"           —— 章号与页码糊在一起
      "第1章" + "G" + "15" + "物联网概论"  —— 中间夹着零碎符号与页码
      "•第2章。RFID 与物联网应用"          —— 章首页一整行，行首带项目符号
      "第1章 物联网概论"                   —— 干净的一行
    页眉行因为整章重复会被样板行过滤掉，于是 "第N章" 这个根节点就丢了。
    这里在每章首页补一行合成标题，让它重新成为一级标题。

    只看页面**最前面 3 行**：章号只可能出现在页眉或章首页的大标题位置，
    放开范围会把「教学建议」表格里的 "第6章" 单元格也当章名。
    """
    limit = min(start + 3, len(page_lines))
    for offset in range(start, limit):
        line = _LEAD_JUNK.sub("", page_lines[offset].strip())
        m = _BARE_CHAPTER.match(line)
        if not m:
            continue
        no = m.group(1)
        rest = re.sub(r"[\s\d]{1,6}$", "", m.group(2)).strip(_EDGE_PUNCT)
        # 章名与章号同行时直接可用；但要挡住 ".5" 这种页码残渣 —— 必须含 2 个以上汉字
        if len(_CJK.findall(rest)) >= 2:
            return f"第{no}章 {rest}"
        # 章名被 OCR 拆到了后面几行，逐行去找：跳过页码与零碎符号行
        for nxt in page_lines[offset + 1 : offset + 5]:
            candidate = nxt.strip()
            if not candidate or _PAGE_NOISE.match(candidate):
                continue
            if len(_CJK.findall(candidate)) < 2:
                continue
            if len(candidate) <= 40 and not candidate.endswith(_SENTENCE_TAIL):
                return f"第{no}章 {candidate}"
            break
        return ""
    return ""


def _chapter_canonical_map(pages: list[list[str]]) -> dict[str, str]:
    """先扫全篇，为每个章号选定唯一「规范章名」。

    同一章在不同页的页眉会被 OCR 认成不同变体（"物联网概论" / "粅联网概论"），
    直接按页插入会让同一章变成两个根节点。先按出现频次投票选一个标准写法，
    后面插入和去重都以它为准。
    """
    from collections import Counter

    votes: dict[str, Counter[str]] = {}
    first_idx: dict[tuple[str, str], int] = {}
    for idx, page in enumerate(pages):
        # 注意：_split_pages 已经把分页标记行剥掉了，页眉就在页首
        title = _scan_chapter_title(page, 0)
        if not title:
            continue
        m = _CHAPTER_HEADING.match(title)
        if not m:
            continue
        no = m.group(1)
        votes.setdefault(no, Counter())[title] += 1
        first_idx.setdefault((no, title), idx)

    canonical: dict[str, str] = {}
    for no, counter in votes.items():
        top = max(counter.values())
        cands = [t for t, n in counter.items() if n == top]
        # 频次打平时取最早出现的那个：章首页的页眉通常最清晰，
        # 越往后 OCR 越容易把形近字认错（"物联网概论" → "粅联网概论"）
        canonical[no] = min(cands, key=lambda t: first_idx[(no, t)])
    return canonical


def _is_variant_of(title: str, canonical: str) -> bool:
    """判断一行章标题是不是规范章名的 OCR 变体。

    用相似度而不是相等判断：形近字错认只差一两个字（"粅联网概论" vs "物联网概论"），
    而正文里的交叉引用（"第1章介绍了物联网的基本概念"）虽然也以章号开头，
    但长度和内容都差得远，不会被误杀。
    """
    from difflib import SequenceMatcher

    if not canonical:
        return False
    return SequenceMatcher(None, _norm_key(title), _norm_key(canonical)).ratio() >= 0.6


def _inject_chapter_headings(text: str) -> tuple[str, dict[str, str]]:
    """在每章首页插入一行合成章节标题，并返回章号 → 规范章名。

    返回 canonical 供 parse_text 做同名去重：只在首次出现处插一次标题，
    后续页的同章标题不再重复插入。
    """
    lines = text.splitlines()
    pages = _split_pages(lines) or []
    canonical = _chapter_canonical_map(pages)

    out: list[str] = []
    current = ""
    for idx, line in enumerate(lines):
        out.append(line)
        if not _PAGE_MARK.match(line.strip()):
            continue
        title = _scan_chapter_title(lines, idx + 1)
        if not title:
            continue
        cm = _CHAPTER_HEADING.match(title)
        if cm and cm.group(1) in canonical:
            title = canonical[cm.group(1)]
        if title != current:
            current = title
            out.append(title)
    return "\n".join(out), canonical


def _classify(line: str) -> tuple[int, str, tuple[int, ...] | None]:
    """判断一行是不是标题，返回 (层级, 标题文本, 编号键)；非标题返回 (0, "", None)。

    编号键是形如 (4,) / (4, 4) / (4, 4, 2) 的整数元组 —— 结构还原要靠它判断上下位，
    只按「层级深度」入栈会把 "4.4.2" 错挂到 "4.3" 底下（4.4.2 的父级是 4.4，不是 4.3）。
    """
    line = line.strip()
    if not line or len(line) > MAX_HEADING_LEN:
        return 0, "", None

    # 以句末标点结尾的一定是正文。挡住 "802.15.4 节点的发射功率只是Wi-Fi的1%。"
    # 这类以编号开头的句子被当成标题 —— 标题从来不会以句号收尾。
    if line.endswith(_SENTENCE_TAIL):
        return 0, "", None

    m = _MD_HEADING.match(line)
    if m:
        return len(m.group(1)), m.group(2).strip(), None

    # 前后附页（参考文献 / 推荐阅读 / 前言…）单独成一级节点，键为 None → 重置标题栈
    special = _special_heading(line)
    if special:
        return 1, special, None

    # 剥掉行首的项目符号/装饰符号后再判章标题：
    # 章首页常写成 "•第2章。RFID 与物联网应用"，不剥就会当成正文，白白丢掉一个根节点
    head = _LEAD_JUNK.sub("", line)
    if _ZH_CHAPTER.match(head):
        cm = _CHAPTER_HEADING.match(head)
        key = (int(cm.group(1)),) if cm else None
        return 1, _clean_chapter_title(head), key

    m = _NUM_HEADING.match(line)
    if m:
        # "1.4" -> 2 级，"1.4.1" -> 3 级
        parts = tuple(int(p) for p in m.group(1).split("."))
        return min(len(parts) + 1, 6), line, parts

    if _ZH_NUM.match(line):
        return 2, line, None

    return 0, "", None


def _stack_keep(stack: list[tuple], key: tuple[int, ...] | None, level: int) -> int:
    """新标题该挂在哪儿 —— 返回要保留的栈深度。

    有编号时按**前缀关系**判断：只保留编号是新编号严格前缀的那些节点。
    "4.3" 不是 "4.4.2" 的前缀，所以会被弹掉；"第4章"（键 (4,)）是前缀，得以保留。
    没有编号（中文序号、"一、"）时退化为按层级深度弹栈。

    两种特殊情况：
    - **无编号的祖先要保留**。附表页（教学建议）里列出了别的教材的章节目录，
      那些 "2.1 自动识别技术" 不能变成文档的根节点，得挂在「教学建议」下面。
      否则文档会凭空多出一堆假章节。
    - **章级标题一律另起根节点**。第 N 章 是文档的顶层结构，
      不管前面堆了什么（前言、目录、上一章的小节），都必须重置。
    """
    if key is None:
        return max(0, level - 1)
    if len(key) == 1:
        return 0

    keep = 0
    for i, (k, _title) in enumerate(stack):
        if k is None:
            keep = i + 1
            continue
        if len(k) < len(key) and key[: len(k)] == k:
            keep = i + 1
        else:
            break
    return keep


def parse(path: str, fmt: str = "txt") -> ParseResult:
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        raw = fh.read()
    return parse_text(raw, fmt)


def parse_text(raw: str, fmt: str = "txt") -> ParseResult:
    """从已得到的纯文本还原结构 —— 供 .doc / OCR 产物等复用。"""
    result = ParseResult(meta={"format": fmt})
    stack: list[tuple[tuple[int, ...] | None, str]] = []
    injected, canonical = _inject_chapter_headings(raw)
    raw_lines = injected.splitlines()
    lines = _strip_boilerplate(raw_lines)
    if len(lines) != len(raw_lines):
        result.meta["boilerplate_dropped"] = len(raw_lines) - len(lines)

    lines, toc_pages = _drop_toc_pages(lines)
    if toc_pages:
        result.meta["toc_pages_dropped"] = toc_pages

    def heading_path() -> str:
        return join_heading([t for _k, t in stack])

    toc_lines = 0
    dropped_variants = 0
    for line in lines:
        if _is_toc_line(line):
            toc_lines += 1
            continue
        level, title, key = _classify(line)
        if level == 1:
            if key:
                no = str(key[0])
                # 同一章只保留一个根节点：OCR 形近字变体（"粅联网概论"）直接丢弃，
                # 否则章节树里会冒出 "第1章 物联网概论" 和 "第1章 粅联网概论" 两个一级节点
                if no in canonical:
                    if _is_variant_of(title, canonical[no]):
                        title = canonical[no]
                    if title != canonical[no]:
                        dropped_variants += 1
                        continue
            # 页眉还原出的合成标题、正文里的原始章标题、以及整章重复的页眉
            # 会各命中一次，相邻同名的一级标题只保留第一个
            if stack and title == stack[0][1]:
                dropped_variants += 1
                continue
        if level:
            # 按编号前缀决定挂载位置：只保留编号是新编号严格前缀的祖先
            del stack[_stack_keep(stack, key, level):]
            stack.append((key, title))
            # 标题本身也作为块保留：既让「数据详情」预览有层级，
            # 也让切片首行带标题，检索时更容易命中
            result.add(title, heading_path=heading_path(), level=level)
            continue
        if not line.strip():
            continue
        result.add(line, heading_path=heading_path())

    # 极端情况：整篇没有识别出任何标题，至少保证正文被收进去
    if not result.blocks and raw.strip():
        result.add(raw.strip(), heading_path=heading_path())

    if toc_lines:
        result.meta["toc_lines_dropped"] = toc_lines
    if dropped_variants:
        result.meta["chapter_variants_dropped"] = dropped_variants
    result.meta["heading_count"] = sum(1 for b in result.blocks if b.level)
    return result
