from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import CharacterProfile, ScriptSegment
from ..voices import VoicePreset


class TTSProvider(ABC):
    name = "base"

    @abstractmethod
    def synthesize(
        self,
        segment: ScriptSegment,
        character: CharacterProfile,
        voice: VoicePreset,
        output_path: Path,
    ) -> dict[str, object]:
        """Write one WAV file and return provider metadata."""

