from __future__ import annotations

import io
import posixpath
import re
import zipfile
from hashlib import sha1
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from .books import BookChapter, BookProject


MAX_EPUB_ENTRIES = 2_000
MAX_EPUB_UNCOMPRESSED_BYTES = 50_000_000
MAX_EPUB_MEMBER_BYTES = 5_000_000
MAX_CHAPTER_CHARACTERS = 45_000
MAX_COMPRESSION_RATIO = 150
EPUB_DOCUMENT_MEDIA_TYPES = {
    "application/xhtml+xml",
    "text/html",
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_archive_path(value: str) -> str:
    if not value or "\x00" in value or "\\" in value:
        raise ValueError("EPUB 包含非法文件路径")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("EPUB 包含越界文件路径")
    normalized = posixpath.normpath(value)
    if normalized in {"", "."} or normalized.startswith("../"):
        raise ValueError("EPUB 包含非法文件路径")
    return normalized


def _read_member(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    name: str,
    *,
    max_bytes: int = MAX_EPUB_MEMBER_BYTES,
) -> bytes:
    safe_name = _safe_archive_path(name)
    info = members.get(safe_name)
    if info is None or info.is_dir():
        raise ValueError(f"EPUB 缺少必要文件：{safe_name}")
    if info.file_size > max_bytes:
        raise ValueError(f"EPUB 内文件过大：{safe_name}")
    data = archive.read(info)
    if len(data) != info.file_size:
        raise ValueError(f"EPUB 内文件读取不完整：{safe_name}")
    return data


def _xml_root(data: bytes, label: str) -> ElementTree.Element:
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError(f"{label} 包含不支持的 XML 声明")
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError(f"{label} 格式损坏") from exc


def _decode_document(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    header = data[:1_024].decode("ascii", errors="ignore")
    declared = re.search(
        r"(?:encoding|charset)\s*=\s*[\"']?\s*([A-Za-z0-9._-]+)",
        header,
        flags=re.IGNORECASE,
    )
    encodings = ["utf-8-sig", "gb18030"]
    if declared:
        normalized = declared.group(1).casefold().replace("_", "-")
        if normalized in {"utf-8", "utf8"}:
            encodings.insert(0, "utf-8-sig")
        elif normalized in {"gb18030", "gbk", "gb2312"}:
            encodings.insert(0, "gb18030")
    for encoding in dict.fromkeys(encodings):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


class _ReadableHTMLParser(HTMLParser):
    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "p",
        "pre",
        "section",
        "td",
        "th",
        "tr",
    }
    SKIP_TAGS = {"script", "style", "svg", "math", "nav", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.heading_depth = 0
        self.title_depth = 0
        self.heading_parts: list[str] = []
        self.title_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.casefold()
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        if tag in {"h1", "h2"} and not self.heading_parts:
            self.heading_depth += 1
        if tag == "title":
            self.title_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self.SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        if tag in {"h1", "h2"} and self.heading_depth:
            self.heading_depth -= 1
        if tag == "title" and self.title_depth:
            self.title_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.title_depth:
            self.title_parts.append(data)
            return
        self.parts.append(data)
        if self.heading_depth:
            self.heading_parts.append(data)

    def readable_text(self) -> str:
        raw = "".join(self.parts).replace("\xa0", " ")
        raw = re.sub(r"[ \t\f\v]+", " ", raw)
        lines = [line.strip() for line in raw.splitlines()]
        compact: list[str] = []
        for line in lines:
            if line:
                compact.append(line)
            elif compact and compact[-1] != "":
                compact.append("")
        return "\n\n".join(line for line in compact if line).strip()

    def chapter_title(self) -> str:
        heading = re.sub(r"\s+", " ", "".join(self.heading_parts)).strip()
        document_title = re.sub(r"\s+", " ", "".join(self.title_parts)).strip()
        return heading or document_title


def _extract_document(data: bytes) -> tuple[str, str]:
    parser = _ReadableHTMLParser()
    try:
        parser.feed(_decode_document(data))
        parser.close()
    except Exception as exc:
        raise ValueError("EPUB 章节内容无法解析") from exc
    return parser.chapter_title(), parser.readable_text()


def _split_long_text(text: str, max_characters: int) -> list[str]:
    if len(text) <= max_characters:
        return [text]
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", text)]
    units: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        if len(paragraph) <= max_characters:
            units.append(paragraph)
            continue
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？!?；;])", paragraph)
            if sentence.strip()
        ]
        for sentence in sentences or [paragraph]:
            while len(sentence) > max_characters:
                units.append(sentence[:max_characters])
                sentence = sentence[max_characters:]
            if sentence:
                units.append(sentence)

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for unit in units:
        separator = 2 if current else 0
        if current and current_length + separator + len(unit) > max_characters:
            chunks.append("\n\n".join(current))
            current = []
            current_length = 0
            separator = 0
        current.append(unit)
        current_length += separator + len(unit)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _resolved_href(opf_path: str, href: str) -> str:
    decoded_path = unquote(urlsplit(href).path)
    if not decoded_path:
        raise ValueError("EPUB 书脊引用了空文件")
    resolved = posixpath.normpath(
        posixpath.join(posixpath.dirname(opf_path), decoded_path)
    )
    return _safe_archive_path(resolved)


def parse_epub(data: bytes, source_name: str = "book.epub") -> BookProject:
    if not data:
        raise ValueError("EPUB 文件为空")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("这不是有效的 EPUB 文件") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_EPUB_ENTRIES:
            raise ValueError("EPUB 内文件数量过多")
        total_uncompressed = 0
        members: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            safe_name = _safe_archive_path(info.filename)
            if safe_name in members:
                raise ValueError("EPUB 包含重复文件路径")
            members[safe_name] = info
            total_uncompressed += info.file_size
            if info.flag_bits & 0x1:
                raise ValueError("暂不支持加密或带 DRM 的 EPUB")
            if (
                info.file_size > 1_000_000
                and info.compress_size > 0
                and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise ValueError("EPUB 压缩比例异常，已停止导入")
        if total_uncompressed > MAX_EPUB_UNCOMPRESSED_BYTES:
            raise ValueError("EPUB 解压后的内容过大")
        if "META-INF/encryption.xml" in members:
            encryption = _read_member(
                archive,
                members,
                "META-INF/encryption.xml",
                max_bytes=500_000,
            )
            if b"EncryptedData" in encryption:
                raise ValueError("暂不支持加密或带 DRM 的 EPUB")

        container_root = _xml_root(
            _read_member(
                archive,
                members,
                "META-INF/container.xml",
                max_bytes=500_000,
            ),
            "EPUB 目录",
        )
        rootfile = next(
            (
                element
                for element in container_root.iter()
                if _local_name(element.tag) == "rootfile"
                and element.get("full-path")
            ),
            None,
        )
        if rootfile is None:
            raise ValueError("EPUB 找不到书籍目录")
        opf_path = _safe_archive_path(str(rootfile.get("full-path")))
        opf_root = _xml_root(
            _read_member(
                archive,
                members,
                opf_path,
                max_bytes=2_000_000,
            ),
            "EPUB 书籍目录",
        )

        title = ""
        creators: list[str] = []
        manifest: dict[str, tuple[str, str, str]] = {}
        spine_ids: list[str] = []
        for element in opf_root.iter():
            name = _local_name(element.tag)
            text = (element.text or "").strip()
            if name == "title" and text and not title:
                title = text
            elif name == "creator" and text:
                creators.append(text)
            elif name == "item":
                item_id = (element.get("id") or "").strip()
                href = (element.get("href") or "").strip()
                media_type = (element.get("media-type") or "").strip().casefold()
                properties = (element.get("properties") or "").strip().casefold()
                if item_id and href:
                    manifest[item_id] = (href, media_type, properties)
            elif name == "itemref":
                item_id = (element.get("idref") or "").strip()
                linear = (element.get("linear") or "yes").strip().casefold()
                if item_id and linear != "no":
                    spine_ids.append(item_id)

        if not spine_ids:
            spine_ids = list(manifest)

        chapters: list[BookChapter] = []
        skipped = 0
        for item_id in spine_ids:
            item = manifest.get(item_id)
            if item is None:
                skipped += 1
                continue
            href, media_type, properties = item
            extension = posixpath.splitext(urlsplit(href).path)[1].casefold()
            if (
                "nav" in properties.split()
                or (
                    media_type not in EPUB_DOCUMENT_MEDIA_TYPES
                    and extension not in {".html", ".htm", ".xhtml"}
                )
            ):
                continue
            chapter_path = _resolved_href(opf_path, href)
            try:
                chapter_title, text = _extract_document(
                    _read_member(archive, members, chapter_path)
                )
            except ValueError:
                skipped += 1
                continue
            if not text:
                skipped += 1
                continue
            fallback_title = posixpath.splitext(posixpath.basename(chapter_path))[0]
            chapter_title = chapter_title or fallback_title or "未命名章节"
            parts = _split_long_text(text, MAX_CHAPTER_CHARACTERS)
            for part_index, part in enumerate(parts, start=1):
                display_title = (
                    chapter_title
                    if len(parts) == 1
                    else f"{chapter_title}（{part_index}/{len(parts)}）"
                )
                stable_id = sha1(
                    f"{chapter_path}:{part_index}:{display_title}".encode("utf-8")
                ).hexdigest()[:12]
                chapters.append(
                    BookChapter(
                        id=f"chapter_{stable_id}",
                        title=display_title,
                        text=part,
                        source_path=chapter_path,
                    )
                )

        if not chapters:
            raise ValueError("EPUB 中没有找到可朗读章节")
        warnings: list[str] = []
        if skipped:
            warnings.append(f"有 {skipped} 个无正文或损坏的书籍页面已跳过。")
        source_stem = posixpath.splitext(posixpath.basename(source_name))[0]
        return BookProject(
            title=title or source_stem or "未命名书籍",
            author="、".join(dict.fromkeys(creators)),
            chapters=chapters,
            source_name=posixpath.basename(source_name),
            source_type="epub",
            warnings=warnings,
        )
