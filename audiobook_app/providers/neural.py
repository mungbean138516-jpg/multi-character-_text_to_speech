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


NEURAL_VOICE_MAP_VERSION = 1

# The free Edge catalogue currently exposes fourteen Chinese neural voices.
# Auto-casting uses nine Mandarin / Taiwan Mandarin voices; Cantonese and
# regional-accent voices stay opt-in so ordinary novel characters do not
# unexpectedly change dialect. Keep the mapping explicit so a character's
# voice remains stable across chapters and app restarts.
NEURAL_VOICE_BY_PRESET: dict[str, str] = {
    "narrator_f": "zh-CN-XiaoxiaoNeural",
    "narrator_m": "zh-CN-YunyangNeural",
    "narrator_f_warm": "zh-TW-HsiaoChenNeural",
    "narrator_m_story": "zh-TW-YunJheNeural",
    "adult_f_soft": "zh-CN-XiaoyiNeural",
    "adult_f_warm": "zh-TW-HsiaoYuNeural",
    "adult_m_bright": "zh-CN-YunxiNeural",
    "adult_m_calm": "zh-CN-YunyangNeural",
    "adult_m_wise": "zh-CN-YunjianNeural",
    "adult_f_cheerful": "zh-CN-XiaoyiNeural",
    "adult_f_low": "zh-TW-HsiaoChenNeural",
    "adult_f_gentle": "zh-TW-HsiaoYuNeural",
    "adult_f_composed": "zh-CN-XiaoxiaoNeural",
    "young_m_crisp": "zh-CN-YunxiNeural",
    "young_f_sweet": "zh-CN-XiaoyiNeural",
    "young_m_clear": "zh-CN-YunxiaNeural",
    "adult_m_warm": "zh-TW-YunJheNeural",
    "adult_m_deadpan": "zh-CN-YunjianNeural",
    "adult_m_melancholy": "zh-TW-YunJheNeural",
    "teen_f": "zh-CN-XiaoyiNeural",
    "child_f": "zh-TW-HsiaoYuNeural",
    "child_m": "zh-CN-YunxiaNeural",
    "elder_f": "zh-TW-HsiaoChenNeural",
    "elder_m": "zh-TW-YunJheNeural",
}

_FALLBACK_BY_GENDER = {
    "female": "zh-CN-XiaoxiaoNeural",
    "male": "zh-CN-YunxiNeural",
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
    """Use small rate differences while leaving timbre to the neural voice."""

    percent = round((preset.browser_rate - 1.0) * 50)
    if preset.age_group == "child":
        percent = max(percent, 4)
    elif preset.age_group == "teen":
        percent = max(percent, 2)
    elif preset.age_group == "elder":
        percent = min(percent, -5)
    percent = max(-6, min(6, percent))
    return f"{percent:+d}%"


def neural_pitch(preset: VoicePreset) -> str:
    """Avoid the exaggerated pitch shifting that made old voices sound ghostly."""

    hertz = {
        "child": 2,
        "teen": 1,
        "elder": -2,
    }.get(preset.age_group, 0)
    return f"{hertz:+d}Hz"


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
