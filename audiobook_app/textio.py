from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DecodedText:
    text: str
    encoding: str


def _looks_like_text(value: str) -> bool:
    if not value:
        return True
    control_characters = sum(
        ord(character) < 32 and character not in "\n\r\t"
        for character in value
    )
    return control_characters / len(value) < 0.01


def decode_text_bytes(data: bytes) -> DecodedText:
    """Decode common Chinese TXT encodings without third-party packages."""

    if not data:
        return DecodedText("", "utf-8")

    bom_candidates = (
        (b"\xef\xbb\xbf", "utf-8-sig", "UTF-8 BOM"),
        (b"\xff\xfe", "utf-16-le", "UTF-16 LE"),
        (b"\xfe\xff", "utf-16-be", "UTF-16 BE"),
    )
    for bom, codec, label in bom_candidates:
        if data.startswith(bom):
            value = data[len(bom) :].decode(codec)
            if not _looks_like_text(value):
                raise ValueError("文件包含过多控制字符，可能不是小说文本")
            return DecodedText(value, label)

    for codec, label in (("utf-8", "UTF-8"), ("gb18030", "GB18030")):
        try:
            value = data.decode(codec)
        except UnicodeDecodeError:
            continue
        if _looks_like_text(value):
            return DecodedText(value, label)

    raise ValueError("无法识别 TXT 编码；请转换为 UTF-8、UTF-16 或 GB18030")


def read_text_file(path: Path) -> DecodedText:
    return decode_text_bytes(path.read_bytes())
