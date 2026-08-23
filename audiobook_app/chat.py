from __future__ import annotations

import re
from dataclasses import dataclass

from .models import CharacterProfile


_PASSAGE_BREAK_RE = re.compile(r"\n\s*\n+")
_SENTENCE_RE = re.compile(r".+?(?:[。！？!?]+|$)", re.DOTALL)
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_CHAT_STOPWORDS = {
    "什么",
    "为什么",
    "怎么",
    "怎样",
    "可以",
    "觉得",
    "这个",
    "那个",
    "还是",
    "如果",
    "因为",
    "所以",
    "是否",
    "真的",
    "已经",
    "没有",
    "一个",
    "我们",
    "你们",
    "他们",
}


@dataclass(frozen=True)
class ChatContext:
    text: str
    source_characters: int
    selected_characters: int
    passage_count: int
    keyword_count: int
    truncated: bool

    def public_summary(self) -> dict[str, int | bool]:
        return {
            "source_characters": self.source_characters,
            "selected_characters": self.selected_characters,
            "passage_count": self.passage_count,
            "keyword_count": self.keyword_count,
            "truncated": self.truncated,
        }


def _chunk_long_passage(value: str, max_chunk_characters: int = 900) -> list[str]:
    value = re.sub(r"[ \t]+", " ", value).strip()
    if not value:
        return []
    if len(value) <= max_chunk_characters:
        return [value]
    sentences = [match.group(0).strip() for match in _SENTENCE_RE.finditer(value)]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if current and len(current) + len(sentence) + 1 > max_chunk_characters:
            chunks.append(current)
            current = ""
        if len(sentence) > max_chunk_characters:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(
                sentence[start : start + max_chunk_characters]
                for start in range(0, len(sentence), max_chunk_characters)
            )
        else:
            current = f"{current}\n{sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def _passages(source_text: str) -> list[str]:
    blocks = _PASSAGE_BREAK_RE.split(source_text.replace("\r\n", "\n").replace("\r", "\n"))
    passages: list[str] = []
    for block in blocks:
        passages.extend(_chunk_long_passage(block))
    return passages


def _message_keywords(user_message: str) -> list[str]:
    keywords: list[str] = []
    latin_words = [word.casefold() for word in _LATIN_WORD_RE.findall(user_message)]
    keywords.extend(word for word in latin_words if word not in _CHAT_STOPWORDS)

    cjk = "".join(_CJK_RE.findall(user_message))
    for width in (4, 3, 2):
        if len(cjk) < width:
            continue
        for start in range(0, len(cjk) - width + 1):
            token = cjk[start : start + width]
            if token not in _CHAT_STOPWORDS:
                keywords.append(token)
        if len(keywords) >= 24:
            break
    return list(dict.fromkeys(keywords))[:24]


def build_chat_context(
    source_text: str,
    character: CharacterProfile,
    user_message: str,
    *,
    max_characters: int = 12_000,
    max_passages: int = 18,
) -> ChatContext:
    """Select a small, source-grounded context instead of resending a whole book.

    The selector is deliberately local and deterministic. It prioritizes passages
    mentioning the selected character, aliases, evidence, and phrases from the
    current question, then includes neighboring passages for narrative context.
    """

    source_text = source_text.strip()
    max_characters = max(1_500, min(int(max_characters), 30_000))
    max_passages = max(3, min(int(max_passages), 30))
    passages = _passages(source_text)
    if not passages:
        return ChatContext("", len(source_text), 0, 0, 0, False)

    character_terms = list(
        dict.fromkeys(
            term.strip()
            for term in [character.name, *character.aliases[:8]]
            if term.strip() and term.strip() != "旁白"
        )
    )
    evidence_terms = [
        re.sub(r"\s+", "", item)[:20]
        for item in character.evidence[:4]
        if re.sub(r"\s+", "", item)
    ]
    message_terms = _message_keywords(user_message)

    scored: list[tuple[int, int]] = []
    for index, passage in enumerate(passages):
        folded = passage.casefold()
        score = sum(12 * folded.count(term.casefold()) for term in character_terms)
        score += sum(4 for term in evidence_terms if term and term in passage)
        score += sum(2 * folded.count(term.casefold()) for term in message_terms)
        if score and any(mark in passage for mark in ("“", "”", "\"", "「", "」")):
            score += 2
        if score:
            scored.append((score, index))

    anchors = [index for _score, index in sorted(scored, reverse=True)[:8]]
    if not anchors:
        anchors = [0]
    selected: set[int] = set()
    for index in anchors:
        for neighbor in (index - 1, index, index + 1):
            if 0 <= neighbor < len(passages):
                selected.add(neighbor)
            if len(selected) >= max_passages:
                break
        if len(selected) >= max_passages:
            break

    # A short opening excerpt helps answer broad questions such as identity or
    # setting when the exact wording does not occur near a character mention.
    if len(selected) < max_passages:
        selected.add(0)
    ordered = sorted(selected)[:max_passages]
    rendered: list[str] = []
    value_truncated = False
    for index in ordered:
        label = f"【原文片段 {index + 1}】\n"
        separator = "\n\n" if rendered else ""
        selected_characters = len(separator.join(rendered))
        available = max_characters - selected_characters - len(separator) - len(label)
        if available <= 0:
            break
        value = passages[index]
        if len(value) > available:
            value = value[: max(0, available - 1)].rstrip() + "…"
            value_truncated = True
        rendered.append(label + value)
        if len("\n\n".join(rendered)) >= max_characters:
            break

    text = "\n\n".join(rendered)
    return ChatContext(
        text=text,
        source_characters=len(source_text),
        selected_characters=len(text),
        passage_count=len(rendered),
        keyword_count=len(message_terms),
        truncated=(
            len(ordered) < len(passages)
            or len(rendered) < len(ordered)
            or value_truncated
        ),
    )
