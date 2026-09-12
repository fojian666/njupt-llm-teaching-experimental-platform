"""DOCX 解析器（python-docx）。

按文档原始顺序遍历段落与表格，从段落样式中还原标题层级，
使切片能带上 "二、培养目标 > （1）具有社会主义核心价值观…" 这样的路径。
"""
import re

from .base import ParseError, ParseResult, join_heading

_HEADING_STYLE = re.compile(r"^(?:Heading|heading|标题)\s*(\d)", re.IGNORECASE)
_PLAIN_NUM_TITLE = re.compile(r"^([一二三四五六七八九十]+|\d+(?:\.\d+){0,3})\s*[、.．]?\s*\S")


def _heading_level(paragraph) -> int:
    """从段落样式名推断标题级别；取不到返回 0。"""
    style_name = ""
    try:
        style_name = paragraph.style.name or ""
    except Exception:
        return 0

    m = _HEADING_STYLE.match(style_name.strip())
    if m:
        return min(int(m.group(1)), 6)

    # 中文版 Word 的样式名，如 "标题 1"
    m = re.search(r"标题\s*(\d)", style_name)
    if m:
        return min(int(m.group(1)), 6)

    # 有些模板把大纲级别写在 pPr/outlineLvl 上
    try:
        ppr = paragraph._p.pPr
        if ppr is not None and ppr.outlineLvl is not None:
            lvl = ppr.outlineLvl.val
            if lvl is not None and 0 <= lvl <= 5:
                return int(lvl) + 1
    except Exception:
        pass
    return 0


def _iter_body(parent):
    """按 body 中的真实顺序产出 Paragraph / Table。"""
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in parent.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def _table_lines(table) -> list[str]:
    lines: list[str] = []
    for row in table.rows:
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        # 去掉整行为空的表格行
        if any(cells):
            lines.append(" | ".join(cells))
    return lines


def parse(path: str, fmt: str = "docx") -> ParseResult:
    try:
        from docx import Document
    except ImportError as exc:
        raise ParseError("缺少 python-docx 依赖") from exc

    try:
        document = Document(path)
    except Exception as exc:  # 加密、损坏、旧格式
        raise ParseError(f"无法打开 DOCX：{exc}") from exc

    result = ParseResult(meta={"format": fmt})
    stack: list[str] = []
    table_count = 0

    for item in _iter_body(document):
        if item.__class__.__name__ == "Table":
            table_count += 1
            for line in _table_lines(item):
                result.add(line, heading_path=join_heading(stack))
            continue

        text = (item.text or "").strip()
        if not text:
            continue

        level = _heading_level(item)
        if not level:
            # 样式没标层级时，用文本形态兜底（"二、培养目标"、"五、核心课程"）
            stripped = text
            m = re.match(r"^([一二三四五六七八九十]{1,3})\s*[、.．]\s*(\S.*)$", stripped)
            if m and len(stripped) <= 60:
                level = 1
            else:
                m2 = re.match(r"^(\d+(?:\.\d+){1,3})\s+(\S.*)$", stripped)
                if m2 and len(stripped) <= 60:
                    level = min(m2.group(1).count(".") + 1, 6)

        if level:
            del stack[level - 1:]
            while len(stack) < level - 1:
                stack.append("")
            stack.append(text)
            result.add(text, heading_path=join_heading(stack), level=level)
        else:
            result.add(text, heading_path=join_heading(stack))

    result.meta["table_count"] = table_count
    result.meta["heading_count"] = sum(1 for b in result.blocks if b.level)
    return result
