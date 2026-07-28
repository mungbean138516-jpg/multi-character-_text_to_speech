from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1

from .models import CharacterProfile


@dataclass(frozen=True)
class VoicePreset:
    id: str
    label: str
    provider_voice: str
    gender: str
    age_group: str
    description: str
    browser_pitch: float
    browser_rate: float
    tone_hz: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# All provider_voice values below belong to the same model:
# cosyvoice-v3-flash. This is important because Model Studio voice IDs are
# model-specific and cannot safely be mixed.
VOICE_CATALOG: tuple[VoicePreset, ...] = (
    VoicePreset(
        "narrator_f",
        "旁白 · 龙妙",
        "longmiao_v3",
        "female",
        "adult",
        "有节奏、适合长篇叙事",
        1.0,
        0.92,
        205,
    ),
    VoicePreset(
        "narrator_m",
        "旁白 · 龙三叔",
        "longsanshu_v3",
        "male",
        "adult",
        "沉稳、有质感",
        0.86,
        0.9,
        145,
    ),
    VoicePreset(
        "adult_f_soft",
        "成年女 · 龙婉君",
        "longwanjun_v3",
        "female",
        "adult",
        "细腻、轻柔",
        1.12,
        1.0,
        235,
    ),
    VoicePreset(
        "adult_f_warm",
        "成年女 · 龙媛",
        "longyuan_v3",
        "female",
        "adult",
        "温暖、治愈",
        1.06,
        0.94,
        220,
    ),
    VoicePreset(
        "adult_m_bright",
        "成年男 · 龙逸尘",
        "longyichen_v3",
        "male",
        "adult",
        "自由、明亮",
        0.92,
        1.02,
        165,
    ),
    VoicePreset(
        "adult_m_calm",
        "成年男 · 龙天",
        "longtian_v3",
        "male",
        "adult",
        "磁性、理性",
        0.82,
        0.94,
        130,
    ),
    VoicePreset(
        "teen_f",
        "少女 · 龙黛玉",
        "longdaiyu_v3",
        "female",
        "teen",
        "清丽、文气",
        1.22,
        1.04,
        265,
    ),
    VoicePreset(
        "child_f",
        "女孩 · 龙呼呼",
        "longhuhu_v3",
        "female",
        "child",
        "天真、活泼",
        1.42,
        1.1,
        325,
    ),
    VoicePreset(
        "child_m",
        "男孩 · 龙杰力豆",
        "longjielidou_v3",
        "male",
        "child",
        "阳光、调皮",
        1.3,
        1.08,
        285,
    ),
    VoicePreset(
        "elder_f",
        "老年女 · 龙老艺",
        "longlaoyi_v3",
        "female",
        "elder",
        "通透、沉静",
        0.88,
        0.82,
        180,
    ),
    VoicePreset(
        "elder_m",
        "老年男 · 龙老伯",
        "longlaobo_v3",
        "male",
        "elder",
        "沧桑、阅历感",
        0.72,
        0.8,
        110,
    ),
)

VOICE_BY_ID = {voice.id: voice for voice in VOICE_CATALOG}


def catalog_as_dicts() -> list[dict[str, object]]:
    return [voice.to_dict() for voice in VOICE_CATALOG]


def _rank_voice(character: CharacterProfile, voice: VoicePreset) -> int:
    score = 0
    if character.gender == voice.gender:
        score += 5
    elif character.gender in {"unknown", "neutral"}:
        score += 1
    if character.age_group == voice.age_group:
        score += 7
    elif character.age_group == "unknown" and voice.age_group == "adult":
        score += 2
    if character.name == "旁白" and voice.id.startswith("narrator"):
        score += 20
    elif character.name != "旁白" and voice.id.startswith("narrator"):
        score -= 4
    return score


def cast_characters(characters: list[CharacterProfile]) -> list[CharacterProfile]:
    used: set[str] = set()
    for character in characters:
        if character.voice_id in VOICE_BY_ID:
            used.add(character.voice_id)
            continue
        ranked = sorted(
            VOICE_CATALOG,
            key=lambda voice: (
                _rank_voice(character, voice),
                voice.id not in used,
                sha1(f"{character.name}:{voice.id}".encode()).hexdigest(),
            ),
            reverse=True,
        )
        chosen = ranked[0]
        character.voice_id = chosen.id
        used.add(chosen.id)
    return characters


def get_voice(voice_id: str) -> VoicePreset:
    try:
        return VOICE_BY_ID[voice_id]
    except KeyError as exc:
        raise ValueError(f"Unknown voice preset: {voice_id}") from exc

