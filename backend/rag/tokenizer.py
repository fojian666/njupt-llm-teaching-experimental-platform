"""零依赖中文分词器。

BM25 需要 token 序列，而中文没有词边界。常用的 jieba 依赖 19MB sdist 且在本机
pip 解包阶段失败，因此这里改用**字符 bigram**：

    "物联网体系结构" -> ["物联", "联网", "网体", "体系", "系结", "结构"]

对检索召回而言这已经足够，而且对未登录词（"ZigBee"、"EPCIS" 这类专业术语）
比词典分词更稳 —— 不需要词表就知道怎么切。
ASCII 串（英文单词、型号、数字）整体保留，不切。
"""
import re

_ASCII_RUN = re.compile(r"[A-Za-z0-9_]+")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_TOKEN_SCAN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")

# 高频但无检索价值的词，避免污染 BM25 权重
STOPWORDS = {
    "的", "了", "和", "是", "在", "有", "与", "及", "或", "对", "为", "以", "被",
    "这", "那", "其", "之", "也", "就", "都", "而", "并", "等", "中", "上", "下",
    "the", "a", "an", "of", "to", "in", "is", "are", "and", "or", "for", "on",
    "with", "as", "by", "at", "be", "it", "that", "this", "from",
}


def tokenize(text: str) -> list[str]:
    """把文本切成检索用的 token 序列。"""
    if not text:
        return []
    tokens: list[str] = []
    for m in _TOKEN_SCAN.finditer(text):
        piece = m.group(0)
        if _ASCII_RUN.fullmatch(piece):
            low = piece.lower()
            if low not in STOPWORDS:
                tokens.append(low)
            continue
        # 中文片段
        if len(piece) == 1:
            if piece not in STOPWORDS:
                tokens.append(piece)
            continue
        for i in range(len(piece) - 1):
            bg = piece[i : i + 2]
            if bg not in STOPWORDS:
                tokens.append(bg)
    return tokens


def bigrams(text: str) -> set[str]:
    """切片去重用的 token 集合，用于估算切片相似度。"""
    return set(tokenize(text))
