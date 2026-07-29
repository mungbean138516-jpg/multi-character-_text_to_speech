from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Callable
from uuid import uuid4

from ..models import CharacterProfile, ScriptSegment
from ..voices import VoicePreset
from .base import TTSProvider


@dataclass(frozen=True)
class MacOSVoice:
    name: str
    locale: str


_FEMALE_VOICE_HINTS = {
    "huihui",
    "meijia",
    "sinji",
    "tingting",
    "xiaohan",
    "xiaomeng",
    "xiaomo",
    "xiaorui",
    "xiaoshuang",
    "xiaoxiao",
    "xiaoyi",
    "xiaoyan",
    "yaoyao",
}
_MALE_VOICE_HINTS = {
    "kangkang",
    "limu",
    "yunjian",
    "yunjie",
    "yunfeng",
    "yunhao",
    "yunxi",
    "yunyang",
    "yunye",
    "yushu",
}
_NOVELTY_VOICE_HINTS = {
    "badnews",
    "bahh",
    "bells",
    "boing",
    "bubbles",
    "cellos",
    "eddy",
    "flo",
    "goodnews",
    "grandma",
    "grandpa",
    "organ",
    "rocko",
    "sandy",
    "shelley",
    "trinoids",
    "whisper",
    "wobble",
    "zarvox",
}


def _compact_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _name_group(name: str) -> str:
    compact = _compact_name(name)
    if any(hint in compact for hint in _NOVELTY_VOICE_HINTS):
        return "novelty"
    if any(hint in compact for hint in _FEMALE_VOICE_HINTS):
        return "female"
    if any(hint in compact for hint in _MALE_VOICE_HINTS):
        return "male"
    return "unknown"


def list_macos_chinese_voices(
    say_path: str | None = None,
) -> tuple[MacOSVoice, ...]:
    """Return installed Mandarin/Cantonese system voices without downloading any."""

    if sys.platform != "darwin" and say_path is None:
        return ()
    executable = say_path or shutil.which("say")
    if not executable:
        return ()
    try:
        process = subprocess.run(
            [executable, "-v", "?"],
            capture_output=True,
            check=False,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if process.returncode:
        return ()

    voices: list[MacOSVoice] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in process.stdout.splitlines():
        match = re.search(r"\s+(zh_(?:CN|TW|HK))\s+", raw_line)
        if match is None:
            continue
        item = (raw_line[: match.start()].strip(), match.group(1))
        if not item[0] or item in seen:
            continue
        seen.add(item)
        voices.append(MacOSVoice(*item))
    return tuple(voices)


def macos_local_tts_is_available() -> bool:
    if sys.platform != "darwin":
        return False
    return bool(
        shutil.which("say")
        and shutil.which("afconvert")
        and list_macos_chinese_voices()
    )


def _voice_score(system_voice: MacOSVoice, preset: VoicePreset) -> int:
    score = {"zh_CN": 60, "zh_TW": 35, "zh_HK": 25}.get(
        system_voice.locale,
        0,
    )
    group = _name_group(system_voice.name)
    if group == "novelty":
        score -= 120
    elif group == preset.gender:
        score += 45
    elif group in {"female", "male"}:
        score -= 35
    else:
        score += 5
    return score


def select_macos_voice(
    voices: tuple[MacOSVoice, ...],
    preset: VoicePreset,
) -> MacOSVoice:
    if not voices:
        raise RuntimeError("Mac 尚未安装可用的中文系统声音")
    ranked = sorted(
        voices,
        key=lambda item: (
            _voice_score(item, preset),
            sha1(f"{preset.id}:{item.name}".encode()).hexdigest(),
        ),
        reverse=True,
    )
    return ranked[0]


def macos_speech_rate(preset: VoicePreset) -> int:
    """Keep age differences audible without the distorted slow/fast extremes."""

    return max(165, min(205, round(190 * preset.browser_rate)))


class MacOSLocalTTSProvider(TTSProvider):
    """Generate real Chinese speech with the voices already installed on a Mac."""

    name = "local"

    def __init__(
        self,
        *,
        voices: tuple[MacOSVoice, ...] | None = None,
        say_path: str | None = None,
        afconvert_path: str | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.say_path = say_path or shutil.which("say") or ""
        self.afconvert_path = afconvert_path or shutil.which("afconvert") or ""
        self.voices = (
            voices
            if voices is not None
            else list_macos_chinese_voices(self.say_path or None)
        )
        self._runner = runner
        if not self.say_path or not self.afconvert_path:
            raise RuntimeError("Mac 本地朗读组件不可用")
        if not self.voices:
            raise RuntimeError(
                "Mac 尚未安装中文系统声音；请在“系统设置 → 辅助功能 → "
                "朗读内容”中下载一个中文声音"
            )

    def cache_identity(self) -> dict[str, object]:
        return {
            "provider": self.name,
            "version": 1,
            "engine": "macos-say",
            "sample_rate": 24_000,
            "voice_map_version": 1,
            "installed_voices": [
                {"name": item.name, "locale": item.locale}
                for item in self.voices
            ],
        }

    def synthesize(
        self,
        segment: ScriptSegment,
        character: CharacterProfile,
        voice: VoicePreset,
        output_path: Path,
    ) -> dict[str, object]:
        del character
        system_voice = select_macos_voice(self.voices, voice)
        rate = macos_speech_rate(voice)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        text_path = output_path.with_name(f".{output_path.stem}.{token}.txt")
        aiff_path = output_path.with_name(f".{output_path.stem}.{token}.aiff")
        text_path.write_text(segment.text, encoding="utf-8")
        output_path.unlink(missing_ok=True)
        try:
            spoken = self._runner(
                [
                    self.say_path,
                    "-v",
                    system_voice.name,
                    "-r",
                    str(rate),
                    "-o",
                    str(aiff_path),
                    "-f",
                    str(text_path),
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=90,
            )
            if spoken.returncode or not aiff_path.is_file():
                raise RuntimeError(
                    "Mac 本地语音生成失败；请确认所选中文系统声音已经下载完成"
                )
            converted = self._runner(
                [
                    self.afconvert_path,
                    "-f",
                    "WAVE",
                    "-d",
                    "LEI16@24000",
                    "-c",
                    "1",
                    str(aiff_path),
                    str(output_path),
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=90,
            )
            if (
                converted.returncode
                or not output_path.is_file()
                or output_path.stat().st_size <= 44
            ):
                output_path.unlink(missing_ok=True)
                raise RuntimeError("Mac 本地语音转成 WAV 失败")
        except (OSError, subprocess.TimeoutExpired) as exc:
            output_path.unlink(missing_ok=True)
            raise RuntimeError("Mac 本地语音组件暂时无法完成这一句") from exc
        finally:
            text_path.unlink(missing_ok=True)
            aiff_path.unlink(missing_ok=True)
        return {
            "provider": self.name,
            "engine": "macos-say",
            "system_voice": system_voice.name,
            "locale": system_voice.locale,
            "rate": rate,
            "characters": len(segment.text),
            "note": "Mac 本机真实中文语音",
        }
