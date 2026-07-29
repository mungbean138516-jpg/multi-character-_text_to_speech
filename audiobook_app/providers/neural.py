from __future__ import annotations

import asyncio
import importlib.util
from importlib import metadata
from pathlib import Path
from typing import Callable
from uuid import uuid4

from ..models import CharacterProfile, ScriptSegment
from ..voices import VoicePreset
from .base import TTSProvider


NEURAL_VOICE_MAP_VERSION = 5

# The free experience intentionally uses five tested roles instead of exposing
# every available Edge voice. The narrator and adult roles keep their native
# timbre. Yunxi gives adult dialogue a younger, clearer delivery than the
# professional-announcer-oriented Yunyang. Yunxia already reads naturally as a
# boy. The free Edge catalogue has no equivalent standard-Mandarin girl voice,
# so the girl uses the livelier Xiaoyi base with a controlled child-specific
# lift. Elder presets deliberately fall back to a natural adult voice instead
# of simulating age through pitch shifting.
NEURAL_VOICE_BY_PRESET: dict[str, str] = {
    "narrator_f": "zh-CN-XiaoxiaoNeural",
    "adult_f_soft": "zh-CN-XiaoyiNeural",
    "adult_m_calm": "zh-CN-YunxiNeural",
    "child_f": "zh-CN-XiaoyiNeural",
    "child_m": "zh-CN-YunxiaNeural",
}

_FALLBACK_BY_GENDER = {
    "female": "zh-CN-XiaoyiNeural",
    "male": "zh-CN-YunyangNeural",
}

_RATE_BY_PRESET = {
    "narrator_f": "-2%",
    "adult_f_soft": "+0%",
    "adult_m_calm": "+2%",
    "child_f": "+6%",
    "child_m": "+4%",
}

_PITCH_BY_PRESET = {
    "child_f": "+8Hz",
    "child_m": "+2Hz",
}


def neural_voice_pack_is_available() -> bool:
    """Return whether both optional runtime packages are installed."""

    return (
        importlib.util.find_spec("edge_tts") is not None
        and importlib.util.find_spec("miniaudio") is not None
    )


def select_neural_voice(preset: VoicePreset) -> str:
    return NEURAL_VOICE_BY_PRESET.get(
        preset.id,
        _FALLBACK_BY_GENDER.get(
            preset.gender,
            "zh-CN-XiaoxiaoNeural",
        ),
    )


def neural_rate(preset: VoicePreset) -> str:
    """Keep Neural delivery close to each voice's native cadence."""

    curated = _RATE_BY_PRESET.get(preset.id)
    if curated is not None:
        return curated
    percent = round((preset.browser_rate - 1.0) * 25)
    percent = max(-3, min(3, percent))
    return f"{percent:+d}%"


def neural_pitch(preset: VoicePreset) -> str:
    """Keep adults native and use only a subtle lift for child presets."""

    return _PITCH_BY_PRESET.get(preset.id, "+0Hz")


def _package_version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "unknown"


def _save_edge_mp3(
    text: str,
    voice_name: str,
    rate: str,
    pitch: str,
    output_path: Path,
) -> None:
    import edge_tts

    async def generate() -> None:
        speech = edge_tts.Communicate(
            text,
            voice_name,
            rate=rate,
            pitch=pitch,
            connect_timeout=15,
            receive_timeout=90,
        )
        await speech.save(str(output_path))

    asyncio.run(generate())


def _decode_mp3_to_wav(source: Path, target: Path) -> None:
    import miniaudio

    sound = miniaudio.decode_file(
        str(source),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=24_000,
    )
    miniaudio.wav_write_file(str(target), sound)


class NeuralVoicePackProvider(TTSProvider):
    """Generate high-quality Mandarin speech through the free Edge service."""

    name = "neural"

    def __init__(
        self,
        *,
        save_mp3: Callable[[str, str, str, str, Path], None] | None = None,
        decode_mp3: Callable[[Path, Path], None] | None = None,
    ) -> None:
        if (
            (save_mp3 is None or decode_mp3 is None)
            and not neural_voice_pack_is_available()
        ):
            raise RuntimeError(
                "免费 Neural 声线包尚未安装；请运行 "
                "python3 -m pip install edge-tts miniaudio"
            )
        self._save_mp3 = save_mp3 or _save_edge_mp3
        self._decode_mp3 = decode_mp3 or _decode_mp3_to_wav

    def cache_identity(self) -> dict[str, object]:
        return {
            "provider": self.name,
            "version": 1,
            "engine": "edge-neural",
            "sample_rate": 24_000,
            "voice_map_version": NEURAL_VOICE_MAP_VERSION,
            "edge_tts_version": _package_version("edge-tts"),
            "miniaudio_version": _package_version("miniaudio"),
        }

    def synthesize(
        self,
        segment: ScriptSegment,
        character: CharacterProfile,
        voice: VoicePreset,
        output_path: Path,
    ) -> dict[str, object]:
        voice_name = select_neural_voice(voice)
        rate = neural_rate(voice)
        pitch = neural_pitch(voice)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        mp3_path = output_path.with_name(
            f".{output_path.stem}.{token}.edge.mp3"
        )
        output_path.unlink(missing_ok=True)
        try:
            self._save_mp3(
                segment.text,
                voice_name,
                rate,
                pitch,
                mp3_path,
            )
            if not mp3_path.is_file() or mp3_path.stat().st_size < 100:
                raise RuntimeError("免费 Neural 服务没有返回有效音频")
            self._decode_mp3(mp3_path, output_path)
            if not output_path.is_file() or output_path.stat().st_size <= 44:
                raise RuntimeError("Neural 音频转成 WAV 失败")
        except RuntimeError:
            output_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            raise RuntimeError(
                "免费 Neural 声线暂时不可用；请检查网络，或改用 Mac 本地声音"
            ) from exc
        finally:
            mp3_path.unlink(missing_ok=True)
        return {
            "provider": self.name,
            "engine": "edge-neural",
            "system_voice": voice_name,
            "character": character.name,
            "rate": rate,
            "pitch": pitch,
            "characters": len(segment.text),
            "note": "免 Key 在线 Neural 中文声线（实验）",
        }
