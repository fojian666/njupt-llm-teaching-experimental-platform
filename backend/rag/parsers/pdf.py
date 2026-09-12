"""PDF 解析器（pypdf）。

只处理**带文字层**的 PDF。纯扫描件抽不出文字，会在 meta 里标记 needs_ocr，
并在正文给出提示 —— 教材《物联网工程导论》第 2 版就是这种情况，走 OCR 后再导入。
"""
from .base import ParseError, ParseResult, join_heading
from .plain import _classify

MIN_CHARS_PER_PAGE = 50  # 低于此值基本可判定为扫描件


def parse(path: str, fmt: str = "pdf") -> ParseResult:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ParseError("缺少 pypdf 依赖") from exc

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise ParseError("PDF 已加密，无法解析") from exc
        page_count = len(reader.pages)
        pages_text: list[tuple[int, str]] = []
        for idx, page in enumerate(reader.pages, start=1):
            try:
                pages_text.append((idx, page.extract_text() or ""))
            except Exception:
                pages_text.append((idx, ""))
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(f"无法打开 PDF：{exc}") from exc

    total_chars = sum(len(t.strip()) for _, t in pages_text)
    result = ParseResult(meta={"format": fmt, "page_count": page_count})

    if page_count and total_chars / page_count < MIN_CHARS_PER_PAGE:
        result.meta["needs_ocr"] = True
        result.meta["ocr_hint"] = (
            f"该 PDF 疑似扫描件（{page_count} 页仅抽出 {total_chars} 字），"
            "没有文字层，需先做 OCR 再导入。"
        )
        result.add(
            f"【系统提示】该 PDF 共 {page_count} 页，仅抽出 {total_chars} 个字符，"
            "判定为扫描件（无文字层）。请先使用 OCR 工具转换为文本后再导入。"
        )
        return result

    stack: list[str] = []
    for page_no, text in pages_text:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            level, title = _classify(line)
            if level:
                del stack[level - 1:]
                while len(stack) < level - 1:
                    stack.append("")
                stack.append(title)
                result.add(title, heading_path=join_heading(stack), level=level)
            else:
                result.add(line, heading_path=join_heading(stack))
        # 用分页标记辅助定位（切片时作为弱边界）
        result.meta.setdefault("page_chars", {})[page_no] = len(text.strip())

    result.meta["heading_count"] = sum(1 for b in result.blocks if b.level)
    return result
