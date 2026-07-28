from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import CharacterProfile, ScriptSegment
from ..voices import VoicePreset


class TTSProvider(ABC):
    name = "base"

    def cache_identity(self) -> dict[str, object]:
        """Return non-secret settings that change the synthesized waveform."""

        return {"provider": self.name, "version": 1}

    @abstractmethod
    def synthesize(
        self,
        segment: ScriptSegment,
        character: CharacterProfile,
        voice: VoicePreset,
        output_path: Path,
    ) -> dict[str, object]:
        """Write one WAV file and return provider metadata."""
