from __future__ import annotations

import io
import re
import zipfile
from hashlib import sha1
from pathlib import Path
from xml.etree import ElementTree

from .books import BookChapter, BookProject


_CHAPTER_RE = re.compile(
    r"(?m)^(?P<title>\s*(?:第[一二三四五六七八九十百千万零〇两\d]+[章节卷回部篇]|"
    r"chapter\s+\d+)[^\n]{0,60})\s*$",
    re.IGNORECASE,
)


def _split_chapters(text: str, source_name: str, source_type: str) -> BookProject:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("文档中没有可读取的正文")
    matches = list(_CHAPTER_RE.finditer(text))
    parts: list[tuple[str, str]] = []
    if matches:
        preface = text[: matches[0].start()].strip()
        if preface:
            parts.append(("序章", preface))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[match.end() : end].strip()
            if body:
                parts.append((match.group("title").strip(), body))
    if not parts:
        parts = [(Path(source_name).stem or "正文", text)]
    chapters = [
        BookChapter(
            id=f"chapter_{index + 1}_{sha1(title.encode('utf-8')).hexdigest()[:8]}",
            title=title,
            text=body,
            source_path=source_name,
        )
        for index, (title, body) in enumerate(parts)
    ]
    return BookProject(
        title=Path(source_name).stem or "未命名书籍",
        chapters=chapters,
        source_name=source_name,
        source_type=source_type,
    )


def parse_docx(data: bytes, source_name: str) -> BookProject:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 10_000_000:
                raise ValueError("DOCX 正文过大")
            xml = archive.read(info)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("无法读取 DOCX；文件可能已损坏或不是 Word DOCX 文档") from exc
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("DOCX 正文包含不安全的 XML 声明")
    root = ElementTree.fromstring(xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        value = "".join(
            node.text or "" for node in paragraph.iter(f"{namespace}t")
        ).strip()
        if value:
            paragraphs.append(value)
    return _split_chapters("\n".join(paragraphs), source_name, "docx")


def parse_pdf(data: bytes, source_name: str) -> BookProject:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ValueError(
            "PDF 导入需要可选组件 pypdf；请运行 pip install pypdf 后重试"
        ) from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as exc:
        raise ValueError("无法读取 PDF；加密、扫描图片或损坏的 PDF 暂不支持") from exc
    text = "\n\n".join(page for page in pages if page)
    if not text:
        raise ValueError("PDF 没有可提取文字；扫描版 PDF 请先进行 OCR")
    return _split_chapters(text, source_name, "pdf")


def parse_document(data: bytes, source_name: str) -> BookProject:
    lower = source_name.casefold()
    if lower.endswith(".docx"):
        return parse_docx(data, source_name)
    if lower.endswith(".pdf"):
        return parse_pdf(data, source_name)
    raise ValueError("请选择 .pdf 或 .docx 文档")
