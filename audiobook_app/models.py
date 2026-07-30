from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VALID_GENDERS = {"female", "male", "neutral", "unknown"}
VALID_AGE_GROUPS = {"child", "teen", "adult", "elder", "unknown"}
VALID_SEGMENT_KINDS = {"narration", "dialogue"}
VALID_LANGUAGES = {"auto", "zh", "en"}


@dataclass
class CharacterProfile:
    id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    gender: str = "unknown"
    age_group: str = "unknown"
    traits: list[str] = field(default_factory=list)
    voice_id: str = ""
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)
    locked: bool = False

    def __post_init__(self) -> None:
        if self.gender not in VALID_GENDERS:
            self.gender = "unknown"
        if self.age_group not in VALID_AGE_GROUPS:
            self.age_group = "unknown"
        self.aliases = list(
            dict.fromkeys(
                alias.strip()
                for alias in self.aliases
                if alias.strip() and alias.strip() != self.name
            )
        )
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.locked = bool(self.locked)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CharacterProfile":
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            aliases=[str(item) for item in value.get("aliases", [])],
            gender=str(value.get("gender", "unknown")),
            age_group=str(value.get("age_group", "unknown")),
            traits=[str(item) for item in value.get("traits", [])],
            voice_id=str(value.get("voice_id", "")),
            confidence=float(value.get("confidence", 0.5)),
            evidence=[str(item) for item in value.get("evidence", [])],
            locked=bool(value.get("locked", False)),
        )


@dataclass
class ScriptSegment:
    id: str
    kind: str
    text: str
    speaker_id: str
    emotion: str = "neutral"
    confidence: float = 0.5
    source_start: int = 0
    source_end: int = 0
    locked: bool = False
    language: str = "auto"

    def __post_init__(self) -> None:
        if self.kind not in VALID_SEGMENT_KINDS:
            raise ValueError(f"Unsupported segment kind: {self.kind}")
        self.text = self.text.strip()
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.locked = bool(self.locked)
        if self.language not in VALID_LANGUAGES:
            self.language = "auto"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScriptSegment":
        return cls(
            id=str(value["id"]),
            kind=str(value["kind"]),
            text=str(value["text"]),
            speaker_id=str(value["speaker_id"]),
            emotion=str(value.get("emotion", "neutral")),
            confidence=float(value.get("confidence", 0.5)),
            source_start=int(value.get("source_start", 0)),
            source_end=int(value.get("source_end", 0)),
            locked=bool(value.get("locked", False)),
            language=str(value.get("language", "auto")),
        )


@dataclass
class AnalysisResult:
    characters: list[CharacterProfile]
    segments: list[ScriptSegment]
    analyzer: str = "heuristic-v1"
    warnings: list[str] = field(default_factory=list)
    pronunciations: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.pronunciations) > 100:
            raise ValueError("发音词典最多保存 100 条")
        normalized: dict[str, str] = {}
        for source, reading in self.pronunciations.items():
            source_text = str(source).strip()
            reading_text = str(reading).strip()
            if not source_text or not reading_text or source_text == reading_text:
                continue
            if len(source_text) > 32:
                raise ValueError("发音词典的原词最多 32 个字符")
            if len(reading_text) > 64:
                raise ValueError("发音词典的朗读写法最多 64 个字符")
            normalized[source_text] = reading_text
        self.pronunciations = normalized

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": [character.to_dict() for character in self.characters],
            "segments": [segment.to_dict() for segment in self.segments],
            "analyzer": self.analyzer,
            "warnings": list(self.warnings),
            "pronunciations": dict(self.pronunciations),
            "summary": {
                "character_count": max(0, len(self.characters) - 1),
                "segment_count": len(self.segments),
                "dialogue_count": sum(
                    segment.kind == "dialogue" for segment in self.segments
                ),
                "characters_to_render": sum(
                    len(segment.text) for segment in self.segments
                ),
            },
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AnalysisResult":
        raw_pronunciations = value.get("pronunciations", {})
        if not isinstance(raw_pronunciations, dict):
            raw_pronunciations = {}
        return cls(
            characters=[
                CharacterProfile.from_dict(item)
                for item in value.get("characters", [])
            ],
            segments=[
                ScriptSegment.from_dict(item) for item in value.get("segments", [])
            ],
            analyzer=str(value.get("analyzer", "client-edited")),
            warnings=[str(item) for item in value.get("warnings", [])],
            pronunciations={
                str(source): str(reading)
                for source, reading in raw_pronunciations.items()
            },
        )
