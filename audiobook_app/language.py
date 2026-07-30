from __future__ import annotations

import re


_LATIN_RE = re.compile(r"[A-Za-z]")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def detect_text_language(text: str) -> str:
    """Classify only clearly monolingual English; otherwise keep Chinese mode.

    Punctuation, numbers, whitespace, curly quotes, and common Latin-script
    names do not affect the decision. A single CJK character intentionally
    prevents English auto-routing so mixed books keep their existing voice
    behaviour.
    """

    latin_count = len(_LATIN_RE.findall(text))
    cjk_count = len(_CJK_RE.findall(text))
    if latin_count >= 20 and cjk_count == 0:
        return "en"
    return "zh"
