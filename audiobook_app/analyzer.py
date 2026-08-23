from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from hashlib import sha1

from .models import AnalysisResult, CharacterProfile, ScriptSegment
from .voices import cast_characters


NARRATOR_ID = "narrator"
OPEN_TO_CLOSE = {"“": "”", "「": "」", "『": "』"}
CLOSE_TO_OPEN = {value: key for key, value in OPEN_TO_CLOSE.items()}
SPEECH_VERBS = (
    "说道",
    "问道",
    "答道",
    "喊道",
    "叫道",
    "笑道",
    "哭道",
    "嚷道",
    "低声说",
    "轻声说",
    "大声说",
    "沉声说",
    "说",
    "问",
    "答",
    "喊",
    "叫",
    "道",
)
SPEECH_VERB_RE = "|".join(sorted(map(re.escape, SPEECH_VERBS), key=len, reverse=True))
NAME_TOKEN_RE = r"[\u3400-\u9fff]{1,5}?"
SPEAKER_MODIFIER_RE = (
    r"(?:(?:轻轻地|低声地|大声地|缓慢地|忽然|终于|冷冷地|笑着|哭着|"
    r"轻声|低声|大声|沉声|冷冷|笑了笑|叹了口气|抬起头|回过头|"
    r"点了点头|摇了摇头)[，,\s]*)*"
)
BEFORE_SPEAKER_RE = re.compile(
    rf"(?P<name>{NAME_TOKEN_RE}){SPEAKER_MODIFIER_RE}"
    rf"(?:(?:{SPEECH_VERB_RE}))?[：:，,\s]*$"
)
AFTER_SPEAKER_RE = re.compile(
    rf"^[，,\s]*(?P<name>{NAME_TOKEN_RE}){SPEAKER_MODIFIER_RE}"
    rf"(?:{SPEECH_VERB_RE})"
)

PRONOUNS = {"他", "她", "它", "他们", "她们"}
ROLE_ALIASES = {
    "老人",
    "老者",
    "老头",
    "老太太",
    "老爷爷",
    "老奶奶",
    "男孩",
    "女孩",
    "小男孩",
    "小女孩",
    "少年",
    "少女",
    "男人",
    "女人",
    "男子",
    "女子",
    "母亲",
    "父亲",
    "妈妈",
    "爸爸",
    "奶奶",
    "爷爷",
}
NAME_STOPWORDS = {
    "这时",
    "此时",
    "然后",
    "接着",
    "于是",
    "可是",
    "但是",
    "突然",
    "忽然",
    "轻声",
    "低声",
    "大声",
    "冷冷",
    "笑着",
    "哭着",
    "回头",
    "抬头",
    "点头",
    "摇头",
    "门外",
    "身后",
    "面前",
}

FEMALE_MARKERS = {
    "她",
    "女孩",
    "小女孩",
    "少女",
    "姑娘",
    "女人",
    "女子",
    "女士",
    "母亲",
    "妈妈",
    "奶奶",
    "祖母",
    "妻子",
    "姐姐",
    "妹妹",
    "女儿",
    "老太太",
    "老奶奶",
}
MALE_MARKERS = {
    "他",
    "男孩",
    "小男孩",
    "少年",
    "男人",
    "男子",
    "先生",
    "父亲",
    "爸爸",
    "爷爷",
    "祖父",
    "丈夫",
    "哥哥",
    "弟弟",
    "儿子",
    "老头",
    "老爷爷",
}
CHILD_MARKERS = {"孩子", "儿童", "男孩", "女孩", "小男孩", "小女孩", "童声", "稚嫩"}
TEEN_MARKERS = {"少年", "少女", "中学生", "高中生", "十几岁"}
ELDER_MARKERS = {
    "老人",
    "老者",
    "老头",
    "老太太",
    "老爷爷",
    "老奶奶",
    "爷爷",
    "奶奶",
    "祖父",
    "祖母",
    "白发",
    "年迈",
}
TRAIT_MARKERS = {
    "温柔": "温柔",
    "轻声": "轻柔",
    "低声": "沉静",
    "冷冷": "冷静",
    "冷静": "冷静",
    "威严": "威严",
    "严厉": "严肃",
    "活泼": "活泼",
    "兴奋": "活泼",
    "天真": "天真",
    "稚嫩": "稚嫩",
    "沙哑": "沙哑",
    "苍老": "沧桑",
    "爽朗": "爽朗",
    "沉稳": "沉稳",
    "胆怯": "胆怯",
    "急促": "急切",
}


@dataclass(frozen=True)
class DialogueSpan:
    full_start: int
    content_start: int
    content_end: int
    full_end: int


def find_dialogue_spans(text: str) -> tuple[list[DialogueSpan], list[str]]:
    """Return top-level, correctly paired quote spans.

    Nested Chinese quote pairs remain inside their outer dialogue instead of
    being split into unrelated fragments. ASCII double quotes are treated as a
    toggle because the opening and closing glyph are identical.
    """

    spans: list[DialogueSpan] = []
    stack: list[tuple[str, int]] = []
    root_start = -1
    unmatched_closers = 0

    for index, character in enumerate(text):
        if character == '"':
            if stack and stack[-1][0] == '"':
                stack.pop()
                if not stack:
                    spans.append(
                        DialogueSpan(root_start, root_start + 1, index, index + 1)
                    )
                    root_start = -1
            else:
                if not stack:
                    root_start = index
                stack.append((character, index))
            continue

        if character in OPEN_TO_CLOSE:
            if not stack:
                root_start = index
            stack.append((character, index))
            continue

        opening = CLOSE_TO_OPEN.get(character)
        if opening is None:
            continue
        if stack and stack[-1][0] == opening:
            stack.pop()
            if not stack:
                spans.append(
                    DialogueSpan(root_start, root_start + 1, index, index + 1)
                )
                root_start = -1
        else:
            unmatched_closers += 1

    warnings: list[str] = []
    if stack:
        warnings.append("检测到未闭合引号；未闭合部分暂按旁白保留，请检查原文")
    if unmatched_closers:
        warnings.append("检测到无法配对的右引号；请检查原文引号格式")
    return spans, warnings


def _character_id(name: str) -> str:
    return "char_" + sha1(name.encode("utf-8")).hexdigest()[:10]


def _compact_evidence(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ，。！？；：\n")[:80]


def _clean_candidate(raw: str) -> str | None:
    candidate = raw.strip(" ，。！？；：\n")
    candidate = re.sub(r"^(?:那|这|只见|身后的|门口的|面前的)", "", candidate)
    candidate = re.sub(r"^(他|她|它)(?:又|也|还|再)$", r"\1", candidate)
    if not candidate or candidate in NAME_STOPWORDS:
        return None
    if candidate.endswith("地"):
        return None
    for prefix in sorted(NAME_STOPWORDS, key=len, reverse=True):
        if candidate.startswith(prefix) and len(candidate) > len(prefix):
            candidate = candidate[len(prefix) :]
    if candidate in PRONOUNS or candidate in ROLE_ALIASES:
        return candidate
    if not 2 <= len(candidate) <= 4:
        return None
    if any(candidate.endswith(word) for word in NAME_STOPWORDS):
        return None
    return candidate


def _infer_speaker(
    text: str,
    quote_start: int,
    quote_end: int,
    recent_speakers: deque[str],
    profiles_by_name: dict[str, CharacterProfile],
) -> tuple[str | None, float, str]:
    before = text[max(0, quote_start - 70) : quote_start]
    after = text[quote_end : quote_end + 45]
    before_matches = list(BEFORE_SPEAKER_RE.finditer(before))
    raw_name = before_matches[-1].group("name") if before_matches else None
    evidence = before_matches[-1].group(0) if before_matches else ""
    if raw_name is None:
        after_match = AFTER_SPEAKER_RE.search(after)
        if after_match:
            raw_name = after_match.group("name")
            evidence = after_match.group(0)

    candidate = _clean_candidate(raw_name or "")
    alias_hits = [
        (before.rfind(alias) + len(alias), len(alias), alias)
        for alias in ROLE_ALIASES
        if before.rfind(alias) >= 0
    ]
    if (candidate is None or candidate.endswith("地")) and alias_hits:
        _, _, alias = max(alias_hits)
        return alias, 0.86, before[before.rfind(alias) :]
    if candidate in PRONOUNS:
        target_gender = "female" if candidate.startswith("她") else "male"
        for recent_name in reversed(recent_speakers):
            profile = profiles_by_name.get(recent_name)
            if profile and profile.gender in {target_gender, "unknown"}:
                return recent_name, 0.68, evidence
        return candidate, 0.45, evidence
    if candidate:
        return candidate, 0.92, evidence

    unique_recent = list(dict.fromkeys(reversed(recent_speakers)))
    if len(unique_recent) >= 2:
        return unique_recent[1], 0.42, "按最近对话轮次推断"
    if unique_recent:
        return unique_recent[0], 0.35, "沿用最近说话人"
    return None, 0.2, "未找到明确说话人"


def _infer_profile(name: str, text: str, evidence: str) -> CharacterProfile:
    sentence_contexts = [
        sentence.strip()
        for sentence in re.split(r"[。！？!?\n]+", text)
        if name in sentence
    ]
    contexts = sentence_contexts[:8]
    if evidence:
        contexts.append(evidence)
    context = " ".join(contexts) or name

    female_score = sum(marker in name for marker in FEMALE_MARKERS)
    male_score = sum(marker in name for marker in MALE_MARKERS)
    structural_female = "|".join(
        map(re.escape, sorted(FEMALE_MARKERS - {"她"}, key=len, reverse=True))
    )
    structural_male = "|".join(
        map(re.escape, sorted(MALE_MARKERS - {"他"}, key=len, reverse=True))
    )
    if re.search(
        rf"(?:{structural_female}).{{0,4}}{re.escape(name)}|"
        rf"{re.escape(name)}.{{0,6}}(?:是|作为|这个|那个)?(?:{structural_female})",
        context,
    ):
        female_score += 2
    if re.search(
        rf"(?:{structural_male}).{{0,4}}{re.escape(name)}|"
        rf"{re.escape(name)}.{{0,6}}(?:是|作为|这个|那个)?(?:{structural_male})",
        context,
    ):
        male_score += 2
    if female_score > male_score:
        gender = "female"
    elif male_score > female_score:
        gender = "male"
    else:
        gender = "unknown"

    if any(marker in name for marker in ELDER_MARKERS):
        age_group = "elder"
    elif any(marker in name for marker in CHILD_MARKERS):
        age_group = "child"
    elif any(marker in name for marker in TEEN_MARKERS):
        age_group = "teen"
    else:
        age_group = "unknown"

    traits = []
    for marker, trait in TRAIT_MARKERS.items():
        if marker in context and trait not in traits:
            traits.append(trait)
    if not traits:
        traits = ["待确认"]

    explicit_role = name in ROLE_ALIASES
    confidence = 0.84 if explicit_role else 0.62
    if name in PRONOUNS:
        confidence = 0.35
    compact = [_compact_evidence(item) for item in contexts[:3] if _compact_evidence(item)]
    return CharacterProfile(
        id=_character_id(name),
        name=name,
        gender=gender,
        age_group=age_group,
        traits=traits[:4],
        confidence=confidence,
        evidence=compact,
    )


def infer_emotion(text: str) -> str:
    if any(marker in text for marker in ("愤怒", "怒", "吼", "混蛋", "住口")):
        return "angry"
    if any(marker in text for marker in ("哭", "泪", "难过", "悲伤", "哽咽")):
        return "sad"
    if any(marker in text for marker in ("笑", "开心", "太好了", "哈哈")):
        return "happy"
    if "！" in text or "!" in text:
        return "excited"
    if "？" in text or "?" in text:
        return "questioning"
    return "neutral"


class HeuristicNovelAnalyzer:
    """Deterministic baseline that works without a model or an API key."""

    def analyze(self, text: str) -> AnalysisResult:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise ValueError("文本不能为空")

        narrator = CharacterProfile(
            id=NARRATOR_ID,
            name="旁白",
            gender="female",
            age_group="adult",
            traits=["沉稳", "叙事"],
            confidence=1.0,
            evidence=["系统角色"],
        )
        characters: list[CharacterProfile] = [narrator]
        profiles_by_name: dict[str, CharacterProfile] = {}
        recent_speakers: deque[str] = deque(maxlen=6)
        segments: list[ScriptSegment] = []
        warnings: list[str] = []
        cursor = 0

        def append_narration(start: int, end: int) -> None:
            value = normalized[start:end].strip()
            if value:
                segments.append(
                    ScriptSegment(
                        id=f"seg_{len(segments) + 1:03d}",
                        kind="narration",
                        text=value,
                        speaker_id=NARRATOR_ID,
                        confidence=1.0,
                        source_start=start,
                        source_end=end,
                    )
                )

        quote_spans, quote_warnings = find_dialogue_spans(normalized)
        warnings.extend(quote_warnings)
        for span in quote_spans:
            append_narration(cursor, span.full_start)
            dialogue = normalized[span.content_start : span.content_end].strip()
            speaker_name, confidence, evidence = _infer_speaker(
                normalized,
                span.full_start,
                span.full_end,
                recent_speakers,
                profiles_by_name,
            )
            if speaker_name is None:
                speaker_name = f"待确认角色{1 + sum(p.name.startswith('待确认角色') for p in characters)}"
                warnings.append(f"{speaker_name} 的身份需要人工确认")

            if speaker_name not in profiles_by_name:
                profile = _infer_profile(speaker_name, normalized, evidence)
                profiles_by_name[speaker_name] = profile
                characters.append(profile)
            profile = profiles_by_name[speaker_name]
            if evidence:
                compact = _compact_evidence(evidence)
                if compact and compact not in profile.evidence:
                    profile.evidence.append(compact)
            recent_speakers.append(speaker_name)
            segments.append(
                ScriptSegment(
                    id=f"seg_{len(segments) + 1:03d}",
                    kind="dialogue",
                    text=dialogue,
                    speaker_id=profile.id,
                    emotion=infer_emotion(dialogue),
                    confidence=confidence,
                    source_start=span.content_start,
                    source_end=span.content_end,
                )
            )
            cursor = span.full_end

        append_narration(cursor, len(normalized))
        if not segments:
            append_narration(0, len(normalized))
        if not any(segment.kind == "dialogue" for segment in segments):
            warnings.append("没有检测到带引号的对话，当前文本将全部由旁白朗读")

        cast_characters(characters)
        return AnalysisResult(
            characters=characters,
            segments=segments,
            analyzer="heuristic-v1",
            warnings=list(dict.fromkeys(warnings)),
        )
