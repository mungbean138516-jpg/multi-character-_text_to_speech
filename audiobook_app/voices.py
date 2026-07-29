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
        "旁白 · 清晰女声",
        "longmiao_v3",
        "female",
        "adult",
        "自然清晰，适合长篇叙事",
        1.0,
        0.96,
        205,
    ),
    VoicePreset(
        "narrator_m",
        "旁白 · 龙三叔",
        "longsanshu_v3",
        "male",
        "adult",
        "沉稳、有质感",
        0.96,
        0.94,
        145,
    ),
    VoicePreset(
        "narrator_f_warm",
        "旁白 · 龙悦",
        "longyue_v3",
        "female",
        "adult",
        "温暖、磁性，适合有声书",
        1.01,
        0.95,
        198,
    ),
    VoicePreset(
        "narrator_m_story",
        "旁白 · 龙修",
        "longxiu_v3",
        "male",
        "adult",
        "博学、会讲故事",
        0.95,
        0.93,
        138,
    ),
    VoicePreset(
        "adult_f_soft",
        "成年女 · 温柔女声",
        "longwanjun_v3",
        "female",
        "adult",
        "细腻、自然、不夸张",
        1.04,
        0.98,
        235,
    ),
    VoicePreset(
        "adult_f_warm",
        "成年女 · 龙媛",
        "longyuan_v3",
        "female",
        "adult",
        "温暖、治愈",
        1.02,
        0.96,
        220,
    ),
    VoicePreset(
        "adult_m_bright",
        "成年男 · 龙逸尘",
        "longyichen_v3",
        "male",
        "adult",
        "自由、明亮",
        0.98,
        1.0,
        165,
    ),
    VoicePreset(
        "adult_m_calm",
        "成年男 · 沉稳男声",
        "longtian_v3",
        "male",
        "adult",
        "清晰、沉稳、适合对白",
        0.96,
        0.95,
        130,
    ),
    VoicePreset(
        "adult_m_wise",
        "青年男 · 龙楠",
        "longnan_v3",
        "male",
        "adult",
        "清醒、睿智",
        0.97,
        0.97,
        158,
    ),
    VoicePreset(
        "adult_f_cheerful",
        "成年女 · 龙安欢",
        "longanhuan_v3",
        "female",
        "adult",
        "开朗、有活力",
        1.05,
        1.02,
        242,
    ),
    VoicePreset(
        "adult_f_low",
        "成年女 · 龙应静",
        "longyingjing_v3",
        "female",
        "adult",
        "低调、冷静",
        0.99,
        0.95,
        195,
    ),
    VoicePreset(
        "adult_f_gentle",
        "成年女 · 龙应灵",
        "longyingling_v3",
        "female",
        "adult",
        "温柔、有共情力",
        1.03,
        0.97,
        216,
    ),
    VoicePreset(
        "adult_f_composed",
        "成年女 · 龙应桃",
        "longyingtao_v3",
        "female",
        "adult",
        "柔和、从容",
        1.01,
        0.96,
        208,
    ),
    VoicePreset(
        "young_m_crisp",
        "青年男 · 龙安朗",
        "longanlang_v3",
        "male",
        "adult",
        "清新、利落",
        1.0,
        1.02,
        178,
    ),
    VoicePreset(
        "young_f_sweet",
        "青年女 · 龙华",
        "longhua_v3",
        "female",
        "adult",
        "有活力、甜美",
        1.06,
        1.03,
        252,
    ),
    VoicePreset(
        "young_m_clear",
        "青年男 · 龙成",
        "longcheng_v3",
        "male",
        "adult",
        "年轻、清晰",
        1.0,
        1.01,
        172,
    ),
    VoicePreset(
        "adult_m_warm",
        "成年男 · 龙泽",
        "longze_v3",
        "male",
        "adult",
        "温暖、有朝气",
        0.98,
        0.98,
        153,
    ),
    VoicePreset(
        "adult_m_deadpan",
        "成年男 · 龙哲",
        "longzhe_v3",
        "male",
        "adult",
        "冷幽默、内心温暖",
        0.96,
        0.95,
        146,
    ),
    VoicePreset(
        "adult_m_melancholy",
        "成年男 · 龙浩",
        "longhao_v3",
        "male",
        "adult",
        "深情、略带忧郁",
        0.95,
        0.93,
        124,
    ),
    VoicePreset(
        "teen_f",
        "少女 · 龙黛玉",
        "longdaiyu_v3",
        "female",
        "teen",
        "清丽、文气",
        1.07,
        1.02,
        265,
    ),
    VoicePreset(
        "child_f",
        "小女孩 · 活泼女声",
        "longhuhu_v3",
        "female",
        "child",
        "天真、活泼、清亮",
        1.09,
        1.04,
        325,
    ),
    VoicePreset(
        "child_m",
        "小男孩 · 清亮男声",
        "longjielidou_v3",
        "male",
        "child",
        "年轻、清楚、不做夸张变调",
        1.06,
        1.03,
        285,
    ),
    VoicePreset(
        "elder_f",
        "老年女 · 龙老艺",
        "longlaoyi_v3",
        "female",
        "elder",
        "通透、沉静",
        0.97,
        0.9,
        180,
    ),
    VoicePreset(
        "elder_m",
        "老年男 · 龙老伯",
        "longlaobo_v3",
        "male",
        "elder",
        "沧桑、阅历感",
        0.94,
        0.88,
        110,
    ),
)

VOICE_BY_ID = {voice.id: voice for voice in VOICE_CATALOG}

# The free product intentionally keeps only five strong, distinct roles.
# Other catalogue entries remain available to paid providers such as
# CosyVoice, but are not auto-cast or selectable in the free UI.
FREE_VOICE_IDS = frozenset(
    {
        "narrator_f",
        "adult_f_soft",
        "adult_m_calm",
        "child_f",
        "child_m",
    }
)
FREE_VOICE_CATALOG = tuple(
    voice for voice in VOICE_CATALOG if voice.id in FREE_VOICE_IDS
)


def catalog_as_dicts() -> list[dict[str, object]]:
    catalog: list[dict[str, object]] = []
    for voice in VOICE_CATALOG:
        item = voice.to_dict()
        item["access"] = "free" if voice.id in FREE_VOICE_IDS else "premium"
        item["preview_provider"] = (
            "neural" if voice.id in FREE_VOICE_IDS else "dashscope"
        )
        catalog.append(item)
    return catalog


def _rank_voice(character: CharacterProfile, voice: VoicePreset) -> int:
    score = 0
    if character.gender == voice.gender:
        score += 5
    elif character.gender in {"unknown", "neutral"}:
        score += 1
    if character.age_group == voice.age_group:
        score += 7
    elif (
        character.age_group in {"teen", "elder"}
        and voice.age_group == "adult"
    ):
        # The free tier deliberately avoids fake teen/elder timbres made with
        # pitch shifting. A natural adult voice is the safer fallback.
        score += 4
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
        if character.voice_id in FREE_VOICE_IDS or (
            character.locked and character.voice_id in VOICE_BY_ID
        ):
            used.add(character.voice_id)
            continue
        # Unlocked projects created before 0.9 may still carry one of the
        # larger premium catalogue IDs. Move those automatic choices onto the
        # curated free pack, while preserving voices the user explicitly
        # locked.
        ranked = sorted(
            FREE_VOICE_CATALOG,
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
