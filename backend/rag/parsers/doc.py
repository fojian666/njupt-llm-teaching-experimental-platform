"""旧版 .doc / .wps 解析器。

这类二进制格式 Python 没有纯 Python 的可靠解析器，统一走系统转换工具：
macOS 用自带的 `textutil`，Linux 用 `antiword` / `libreoffice`。
转换后交给纯文本解析器还原标题层级。
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import ParseError, ParseResult
from .plain import parse_text


def _convert_with_textutil(path: str) -> str | None:
    if shutil.which("textutil") is None:
        return None
    try:
        proc = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", path],
            capture_output=True, timeout=180,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="ignore")


def _convert_with_antiword(path: str) -> str | None:
    if shutil.which("antiword") is None:
        return None
    try:
        proc = subprocess.run(["antiword", path], capture_output=True, timeout=180)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="ignore")


def _convert_with_libreoffice(path: str) -> str | None:
    binary = shutil.which("soffice") or shutil.which("libreoffice")
    if not binary:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run(
                [binary, "--headless", "--convert-to", "txt:Text (encoded):UTF8",
                 "--outdir", tmp, path],
                capture_output=True, timeout=300,
            )
        except Exception:
            return None
        if proc.returncode != 0:
            return None
        produced = list(Path(tmp).glob("*.txt"))
        if not produced:
            return None
        return produced[0].read_text(encoding="utf-8", errors="ignore")


def parse(path: str, fmt: str = "doc") -> ParseResult:
    for converter in (_convert_with_textutil, _convert_with_antiword, _convert_with_libreoffice):
        raw = converter(path)
        if raw is not None:
            result = parse_text(raw, fmt)
            result.meta["converted_by"] = converter.__name__.removeprefix("_convert_with_")
            return result

    raise ParseError(
        "无法转换 .doc 文件：本机未找到可用的转换工具。"
        "macOS 需要 textutil（系统自带），Linux 可安装 antiword 或 libreoffice。"
        "也可以先在 Word/WPS 里另存为 .docx 再上传。"
    )
