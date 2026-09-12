"""切片器：把解析出的结构块切成可检索的 chunk。

切片的三个原则：
1. **不跨章节** —— 章节换了就断，避免一个切片里混两个主题；
2. **优先整块保留** —— 段落是语义完整单位，尽量不切碎；
3. **带重叠** —— 相邻切片留一段重叠，避免答案正好落在切口上。
"""
import re
from dataclasses import dataclass

from .parsers.base import Block

# 中文句读，用于超长段的硬切分
_SENTENCE_END = re.compile(r"(?<=[。！？；])|(?<=[!?;])\s+")

MIN_CHUNK_CHARS = 40  # 比这还短的切片直接并入上一块，避免产生无意义碎片


@dataclass
class ChunkData:
    seq: int
    content: str
    chapter_path: str
    char_count: int

    @property
    def token_estimate(self) -> int:
        """粗略 token 估算：中文约 1 字 1 token，英文约 4 字符 1 token。"""
        ascii_chars = sum(1 for c in self.content if ord(c) < 128)
        return int((self.char_count - ascii_chars) + ascii_chars / 4)


def _hard_split(text: str, size: int) -> list[str]:
    """把超长文本按句子边界切成不超过 size 的片段；无句读时退化为定长切。"""
    pieces: list[str] = []
    cur = ""
    for seg in _SENTENCE_END.split(text):
        if not seg:
            continue
        if cur and len(cur) + len(seg) > size:
            pieces.append(cur)
            cur = seg
        else:
            cur += seg
    if cur:
        pieces.append(cur)

    out: list[str] = []
    for piece in pieces:
        if len(piece) <= size:
            out.append(piece)
        else:
            out.extend(piece[i : i + size] for i in range(0, len(piece), size))
    return [p for p in out if p.strip()]


def split(
    blocks: list[Block],
    chunk_size: int = 500,
    overlap: int = 80,
    strategy: str = "heading",
) -> list[ChunkData]:
    """把结构块切成切片序列。

    strategy:
      - "heading"：按标题层级分组后按长度切（默认，推荐）
      - "length"：纯按长度切，忽略标题边界
    """
    if chunk_size < MIN_CHUNK_CHARS * 2:
        chunk_size = MIN_CHUNK_CHARS * 2
    overlap = max(0, min(overlap, chunk_size // 2))

    # 超长块先打散，保证后面不会出现「一块顶一个切片」
    expanded: list[Block] = []
    for b in blocks:
        if not b.text:
            continue
        if len(b.text) > chunk_size:
            for piece in _hard_split(b.text, chunk_size):
                expanded.append(Block(text=piece, heading_path=b.heading_path, level=b.level))
        else:
            expanded.append(b)

    respect_heading = strategy == "heading"
    chunks: list[ChunkData] = []
    buf: list[str] = []
    buf_len = 0
    path = ""
    tail = ""

    def emit() -> None:
        nonlocal buf, buf_len, tail
        text = "\n".join(buf).strip()
        if not text:
            buf, buf_len, tail = [], 0, ""
            return
        # 太短的切片并入上一块，不为几个字单开一条记录
        if chunks and len(text) < MIN_CHUNK_CHARS:
            prev = chunks[-1]
            prev.content = f"{prev.content}\n{text}"
            prev.char_count = len(prev.content)
        else:
            chunks.append(ChunkData(seq=len(chunks) + 1, content=text,
                                    chapter_path=path, char_count=len(text)))
        tail = text[-overlap:] if overlap else ""
        buf, buf_len = [], 0

    for b in expanded:
        # 章节边界：先结算当前缓冲，且不跨章节做重叠
        if respect_heading and b.heading_path != path:
            if buf:
                emit()
                tail = ""
            path = b.heading_path
        elif not buf:
            path = b.heading_path

        if not buf and tail:
            buf.append(tail)
            buf_len = len(tail)

        buf.append(b.text)
        buf_len += len(b.text) + 1

        if buf_len >= chunk_size:
            emit()

    if buf:
        emit()

    # 重新编号，保证连续
    for i, c in enumerate(chunks, start=1):
        c.seq = i
    return chunks
