from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .models import AnalysisResult, CharacterProfile
from .voices import cast_characters


NARRATOR_ID = "narrator"
MINOR_CHARACTERS_ID = "minor_characters"
DEFAULT_PRIMARY_LIMIT = 10


def _unique(values: list[str], *, limit: int | None = None) -> list[str]:
    normalized = list(
        dict.fromkeys(
            str(value).strip()
            for value in values
            if str(value).strip()
        )
    )
    return normalized if limit is None else normalized[:limit]


def _identity_terms(character: CharacterProfile) -> set[str]:
    return {
        term.replace(" ", "").casefold()
        for term in [character.name, *character.aliases]
        if term.strip()
    }


def _copy_character(character: CharacterProfile) -> CharacterProfile:
    return CharacterProfile.from_dict(character.to_dict())


@dataclass
class CharacterRegistry:
    """Book-level character memory shared by all chapter analyses."""

    characters: list[CharacterProfile] = field(default_factory=list)
    dialogue_counts: dict[str, int] = field(default_factory=dict)
    minor_character_names: list[str] = field(default_factory=list)
    primary_limit: int = DEFAULT_PRIMARY_LIMIT

    def __post_init__(self) -> None:
        self.primary_limit = max(1, min(DEFAULT_PRIMARY_LIMIT, int(self.primary_limit)))
        unique_characters: list[CharacterProfile] = []
        seen_ids: set[str] = set()
        primary_count = 0
        overflow_profiles: list[CharacterProfile] = []
        for character in self.characters:
            if character.id in seen_ids:
                continue
            if character.id not in {NARRATOR_ID, MINOR_CHARACTERS_ID}:
                if primary_count >= self.primary_limit:
                    overflow_profiles.append(character)
                    continue
                primary_count += 1
            seen_ids.add(character.id)
            unique_characters.append(character)
        self.characters = unique_characters
        if overflow_profiles:
            minor = next(
                (
                    character
                    for character in self.characters
                    if character.id == MINOR_CHARACTERS_ID
                ),
                None,
            )
            if minor is None:
                minor = CharacterProfile(
                    id=MINOR_CHARACTERS_ID,
                    name="其他角色",
                    gender="neutral",
                    age_group="adult",
                    traits=["次要人物合用"],
                    voice_id="adult_m_calm",
                    confidence=0.5,
                    locked=True,
                )
                self.characters.append(minor)
            minor.aliases = _unique(
                [
                    *minor.aliases,
                    *[
                        name
                        for character in overflow_profiles
                        for name in [character.name, *character.aliases]
                    ],
                ],
                limit=200,
            )
            self.minor_character_names = _unique(
                [
                    *self.minor_character_names,
                    *[character.name for character in overflow_profiles],
                ],
                limit=200,
            )
        valid_ids = {character.id for character in self.characters}
        self.dialogue_counts = {
            str(character_id): max(0, int(count))
            for character_id, count in self.dialogue_counts.items()
            if str(character_id) in valid_ids
        }
        self.minor_character_names = _unique(self.minor_character_names, limit=200)

    @property
    def primary_count(self) -> int:
        return sum(
            character.id not in {NARRATOR_ID, MINOR_CHARACTERS_ID}
            for character in self.characters
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": [character.to_dict() for character in self.characters],
            "dialogue_counts": dict(self.dialogue_counts),
            "minor_character_names": list(self.minor_character_names),
            "primary_limit": self.primary_limit,
            "primary_count": self.primary_count,
        }

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any] | None,
        *,
        default_limit: int = DEFAULT_PRIMARY_LIMIT,
    ) -> "CharacterRegistry":
        if not isinstance(value, dict):
            return cls(primary_limit=default_limit)
        raw_characters = value.get("characters", [])
        raw_counts = value.get("dialogue_counts", {})
        if not isinstance(raw_characters, list):
            raw_characters = []
        if not isinstance(raw_counts, dict):
            raw_counts = {}
        characters: list[CharacterProfile] = []
        for item in raw_characters:
            if not isinstance(item, dict):
                continue
            try:
                characters.append(CharacterProfile.from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
        # Migrate pre-0.9 automatic premium assignments when an old project is
        # reopened. cast_characters preserves any voice the user locked.
        cast_characters(characters)
        return cls(
            characters=characters,
            dialogue_counts={
                str(character_id): int(count)
                for character_id, count in raw_counts.items()
                if isinstance(count, (int, float))
            },
            minor_character_names=[
                str(name)
                for name in value.get("minor_character_names", [])
                if str(name).strip()
            ],
            primary_limit=min(
                default_limit,
                int(value.get("primary_limit", default_limit)),
            ),
        )

    def reconcile(self, analysis: AnalysisResult) -> AnalysisResult:
        """Merge one chapter into the registry and rewrite its speaker IDs."""

        incoming_by_id = {character.id: character for character in analysis.characters}
        chapter_dialogue_counts = Counter(
            segment.speaker_id
            for segment in analysis.segments
            if segment.kind == "dialogue"
        )
        id_map: dict[str, str] = {}
        chapter_characters: dict[str, CharacterProfile] = {}
        overflow_names: list[str] = []

        incoming_narrator = incoming_by_id.get(NARRATOR_ID) or CharacterProfile(
            id=NARRATOR_ID,
            name="旁白",
            gender="neutral",
            age_group="adult",
            voice_id="narrator_f",
            confidence=1,
        )
        narrator = self._find_by_id(NARRATOR_ID)
        if narrator is None:
            narrator = _copy_character(incoming_narrator)
            narrator.id = NARRATOR_ID
            narrator.name = "旁白"
            self.characters.insert(0, narrator)
        else:
            self._merge_character(narrator, incoming_narrator)
        id_map[incoming_narrator.id] = narrator.id
        chapter_characters[narrator.id] = _copy_character(narrator)

        for incoming in analysis.characters:
            if incoming.id == NARRATOR_ID:
                continue
            existing = self._match(incoming)
            if existing is None:
                if self.primary_count < self.primary_limit:
                    existing = _copy_character(incoming)
                    existing.id = self._available_id(existing.id)
                    self.characters.append(existing)
                else:
                    existing = self._minor_character()
                    overflow_names.append(incoming.name)
                    existing.aliases = _unique(
                        [*existing.aliases, incoming.name, *incoming.aliases],
                        limit=200,
                    )
                    self.minor_character_names = _unique(
                        [*self.minor_character_names, incoming.name],
                        limit=200,
                    )
            else:
                self._merge_character(existing, incoming)

            id_map[incoming.id] = existing.id
            chapter_characters[existing.id] = _copy_character(existing)
            count = chapter_dialogue_counts.get(incoming.id, 0)
            self.dialogue_counts[existing.id] = (
                self.dialogue_counts.get(existing.id, 0) + count
            )

        for segment in analysis.segments:
            segment.speaker_id = id_map.get(segment.speaker_id, NARRATOR_ID)

        ordered = [chapter_characters[NARRATOR_ID]]
        ordered.extend(
            chapter_characters[character.id]
            for character in self.characters
            if character.id != NARRATOR_ID and character.id in chapter_characters
        )
        analysis.characters = ordered
        if overflow_names:
            names = "、".join(_unique(overflow_names, limit=5))
            suffix = "等" if len(_unique(overflow_names)) > 5 else ""
            analysis.warnings.append(
                f"本书主要角色已达到 {self.primary_limit} 位；"
                f"{names}{suffix} 暂归入“其他角色”，之后仍可手动调整。"
            )
        return analysis

    def _find_by_id(self, character_id: str) -> CharacterProfile | None:
        return next(
            (
                character
                for character in self.characters
                if character.id == character_id
            ),
            None,
        )

    def _match(self, incoming: CharacterProfile) -> CharacterProfile | None:
        same_id = self._find_by_id(incoming.id)
        if same_id is not None and same_id.id not in {
            NARRATOR_ID,
            MINOR_CHARACTERS_ID,
        }:
            return same_id
        incoming_terms = _identity_terms(incoming)
        if not incoming_terms:
            return None
        candidates = [
            character
            for character in self.characters
            if character.id not in {NARRATOR_ID, MINOR_CHARACTERS_ID}
            and incoming_terms.intersection(_identity_terms(character))
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda character: self.dialogue_counts.get(character.id, 0),
        )

    def _merge_character(
        self,
        existing: CharacterProfile,
        incoming: CharacterProfile,
    ) -> None:
        aliases = [*existing.aliases, *incoming.aliases]
        if incoming.name != existing.name:
            aliases.append(incoming.name)
        existing.aliases = _unique(
            [alias for alias in aliases if alias != existing.name],
            limit=100,
        )
        existing.evidence = _unique(
            [*existing.evidence, *incoming.evidence],
            limit=12,
        )
        existing.confidence = max(existing.confidence, incoming.confidence)
        if existing.locked:
            return
        existing.traits = _unique(
            [*existing.traits, *incoming.traits],
            limit=8,
        )
        if existing.gender == "unknown" and incoming.gender != "unknown":
            existing.gender = incoming.gender
        if existing.age_group == "unknown" and incoming.age_group != "unknown":
            existing.age_group = incoming.age_group
        if not existing.voice_id:
            existing.voice_id = incoming.voice_id
        existing.locked = existing.locked or incoming.locked

    def _available_id(self, requested: str) -> str:
        base = requested.strip() or "character"
        used = {character.id for character in self.characters}
        if base not in used:
            return base
        suffix = 2
        while f"{base}_{suffix}" in used:
            suffix += 1
        return f"{base}_{suffix}"

    def _minor_character(self) -> CharacterProfile:
        existing = self._find_by_id(MINOR_CHARACTERS_ID)
        if existing is not None:
            return existing
        minor = CharacterProfile(
            id=MINOR_CHARACTERS_ID,
            name="其他角色",
            gender="neutral",
            age_group="adult",
            traits=["次要人物合用"],
            voice_id="adult_m_calm",
            confidence=0.5,
            evidence=["超过本书主要角色上限后自动归类"],
            locked=True,
        )
        self.characters.append(minor)
        return minor
