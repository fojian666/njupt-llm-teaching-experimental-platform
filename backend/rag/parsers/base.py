"""解析结果的统一结构。

所有解析器都产出 `ParseResult`，下游的切片器只认这个结构，
因此新增一种文档格式只需要写一个 parser，不用动切片和检索。
"""
from dataclasses import dataclass, field
import re


@dataclass
class Block:
    """解析出的一个结构块 —— 一个段落、一个标题、一行表格。"""

    text: str
    heading_path: str = ""
    level: int = 0  # 0 = 正文；1..9 = 标题层级

    def __post_init__(self):
        self.text = (self.text or "").strip()


@dataclass
class ParseResult:
    blocks: list[Block] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        """拼平后的全文，用于落库与预览。"""
        return "\n".join(b.text for b in self.blocks if b.text)

    @property
    def char_count(self) -> int:
        return sum(len(b.text) for b in self.blocks)

    def add(self, text: str, heading_path: str = "", level: int = 0) -> None:
        text = (text or "").strip()
        if text:
            self.blocks.append(Block(text=text, heading_path=heading_path, level=level))


class ParseError(Exception):
    """解析失败，会把 message 原样展示到前端的「解析信息」列。"""


# 一整段没有空格、还带 +/= 的长串 —— 电子书转换器塞进段落里的水印或压缩数据，
# 不是人话，留在切片里只会污染检索结果
_JUNK_TEXT = re.compile(r"^[A-Za-z0-9+/=]{40,}$")


def strip_junk_nodes(soup) -> None:
    """把「看起来不是正文」的元素从解析树里删掉。

    判据故意收得很紧：必须整段都是 40 字符以上的 base64 字符集且无空格。
    正常的中英文段落不可能同时满足这两条，所以不会误伤；
    而《物联网概论》EPUB 里那些 88 字符的水印串正好全中。
    """
    for node in list(soup.find_all(True)):
        if node.name in ("script", "style"):
            continue
        own = "".join(node.find_all(string=True, recursive=False)).strip()
        if own and len(own) >= 40 and _JUNK_TEXT.match(own):
            node.decompose()


def join_heading(stack: list[str]) -> str:
    """把标题栈拼成 "第1章 物联网概论 > 1.4 物联网体系结构" 形式的章节路径。"""
    return " > ".join(s for s in stack if s)
