"""EPUB 解析器（ebooklib + BeautifulSoup）。

按 spine（阅读顺序）遍历章节，把 h1~h6 还原成标题层级。
《物联网概论》第 3 版用的是这个解析器。
"""
from .base import ParseError, ParseResult, join_heading, strip_junk_nodes

_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


def _iter_documents(book):
    """按 spine 顺序产出文档 item —— 保证正文顺序与阅读顺序一致。"""
    import ebooklib

    id_map = {item.get_id(): item for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)}
    for entry in book.spine:
        item_id = entry[0] if isinstance(entry, (tuple, list)) else entry
        item = id_map.get(item_id)
        if item is not None:
            yield item


def _make_soup(content, BeautifulSoup):
    """EPUB 内容多为 XHTML，优先用 XML 解析器，失败再退回 HTML 解析器。"""
    try:
        return BeautifulSoup(content, "lxml-xml")
    except Exception:
        return BeautifulSoup(content, "lxml")


def parse(path: str, fmt: str = "epub") -> ParseResult:
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ParseError("缺少 ebooklib / beautifulsoup4 依赖") from exc

    try:
        book = epub.read_epub(path, options={"ignore_ncx": True})
    except Exception as exc:
        raise ParseError(f"无法打开 EPUB：{exc}") from exc

    result = ParseResult(meta={"format": fmt})
    stack: list[str] = []
    doc_count = 0

    for item in _iter_documents(book):
        doc_count += 1
        try:
            soup = _make_soup(item.get_content(), BeautifulSoup)
        except Exception:
            continue
        # 电子书转换器会在段落里塞水印 / 压缩数据，先清掉再抽正文
        strip_junk_nodes(soup)

        for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th"]):
            text = node.get_text(" ", strip=True)
            if not text:
                continue

            level = _HEADING_TAGS.get(node.name, 0)
            if level:
                del stack[level - 1:]
                while len(stack) < level - 1:
                    stack.append("")
                stack.append(text)
                result.add(text, heading_path=join_heading(stack), level=level)
            else:
                result.add(text, heading_path=join_heading(stack))

    if not result.blocks:
        raise ParseError("EPUB 中没有解析出任何正文内容")

    result.meta["document_count"] = doc_count
    result.meta["heading_count"] = sum(1 for b in result.blocks if b.level)
    return result
