"""解析器注册表 —— 对外只暴露 `parse_file()`。

新增一种格式只需：写一个 `parse(path, fmt) -> ParseResult` 的模块，然后在
`_EXT_TO_FMT` 里登记扩展名、在 `parse_file()` 里接一行分支即可，
下游的切片 / 向量化 / 检索都不用改。
"""
from pathlib import Path

from .base import Block, ParseError, ParseResult, join_heading, strip_junk_nodes

_EXT_TO_FMT = {
    ".txt": "txt",
    ".text": "txt",
    ".md": "md",
    ".markdown": "md",
    ".docx": "docx",
    ".doc": "doc",
    ".wps": "doc",
    ".pdf": "pdf",
    ".epub": "epub",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".csv": "csv",
    ".html": "html",
    ".htm": "html",
}

__all__ = ["Block", "ParseError", "ParseResult", "join_heading",
           "supported_formats", "detect_format", "parse_file"]


def supported_formats() -> list[str]:
    return sorted({fmt for fmt in _EXT_TO_FMT.values()})


def detect_format(path: str) -> str:
    return _EXT_TO_FMT.get(Path(path).suffix.lower(), "")


def _parse_html(path: str, fmt: str) -> ParseResult:
    from bs4 import BeautifulSoup

    from .plain import parse_text

    raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    strip_junk_nodes(soup)
    for node in soup.find_all(["br", "p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"]):
        node.insert_after("\n")
    return parse_text(soup.get_text("\n", strip=True), fmt)


def parse_file(path: str, fmt: str | None = None) -> ParseResult:
    """解析一个文件，返回结构化结果。失败抛 ParseError（消息直接给前端看）。"""
    path = str(path)
    fmt = (fmt or detect_format(path)).lower()
    if not fmt:
        raise ParseError(f"不支持的文件类型：{Path(path).suffix}")

    if fmt in ("txt", "md"):
        from .plain import parse as _p
    elif fmt == "docx":
        from .word import parse as _p
    elif fmt == "doc":
        from .doc import parse as _p
    elif fmt == "pdf":
        from .pdf import parse as _p
    elif fmt == "epub":
        from .epub import parse as _p
    elif fmt in ("xlsx", "xls", "csv"):
        from .sheet import parse as _p
    elif fmt == "html":
        _p = _parse_html
    else:
        raise ParseError(f"暂不支持的格式：{fmt}")

    result = _p(path, fmt)
    result.meta.setdefault("format", fmt)
    result.meta["block_count"] = len(result.blocks)
    result.meta["char_count"] = result.char_count
    return result
