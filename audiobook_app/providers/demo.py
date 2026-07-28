from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from ..models import CharacterProfile, ScriptSegment
from ..voices import VoicePreset
from .base import TTSProvider


class DemoToneProvider(TTSProvider):
    """Offline pipeline checker.

    It deliberately produces tones, not fake speech. The web client supplies a
    browser speech preview, while this provider proves that the server-side
    segment-to-audio-to-stitching path works without spending API credits.
    """

    name = "demo"
    sample_rate = 24_000

    def synthesize(
        self,
        segment: ScriptSegment,
        character: CharacterProfile,
        voice: VoicePreset,
        output_path: Path,
    ) -> dict[str, object]:
        duration = max(0.45, min(2.4, 0.18 + len(segment.text) * 0.055))
        frame_count = int(self.sample_rate * duration)
        amplitude = 8_000
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(self.sample_rate)
            frames = bytearray()
            for index in range(frame_count):
                envelope = min(1.0, index / 500, (frame_count - index) / 500)
                carrier = math.sin(
                    2 * math.pi * voice.tone_hz * index / self.sample_rate
                )
                pulse = 0.25 * math.sin(
                    2 * math.pi * (voice.tone_hz * 1.5) * index / self.sample_rate
                )
                value = int(amplitude * max(0.0, envelope) * (carrier + pulse))
                frames.extend(struct.pack("<h", max(-32768, min(32767, value))))
            audio.writeframes(bytes(frames))
        return {
            "provider": self.name,
            "characters": len(segment.text),
            "note": "离线诊断音，不是真实 TTS",
        }

