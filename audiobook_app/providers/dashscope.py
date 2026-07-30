from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ..models import CharacterProfile, ScriptSegment
from ..voices import VoicePreset
from .base import TTSProvider


def dashscope_tts_is_configured() -> bool:
    return bool(
        os.getenv("DASHSCOPE_API_KEY")
        and (
            os.getenv("DASHSCOPE_TTS_ENDPOINT")
            or os.getenv("DASHSCOPE_WORKSPACE_ID")
        )
    )


class DashScopeTTSProvider(TTSProvider):
    """Alibaba Cloud Model Studio non-realtime TTS HTTP adapter."""

    name = "dashscope"

    def __init__(self) -> None:
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        workspace_id = os.getenv("DASHSCOPE_WORKSPACE_ID", "")
        default_endpoint = (
            f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com/"
            "api/v1/services/audio/tts/SpeechSynthesizer"
            if workspace_id
            else ""
        )
        self.endpoint = os.getenv("DASHSCOPE_TTS_ENDPOINT", default_endpoint)
        self.model = os.getenv("DASHSCOPE_TTS_MODEL", "cosyvoice-v3-flash")
        self.timeout = float(os.getenv("DASHSCOPE_TIMEOUT_SECONDS", "60"))
        if not self.api_key or not self.endpoint:
            raise RuntimeError(
                "请先配置 DASHSCOPE_API_KEY，以及 DASHSCOPE_WORKSPACE_ID "
                "或 DASHSCOPE_TTS_ENDPOINT"
            )

    def cache_identity(self) -> dict[str, object]:
        return {
            "provider": self.name,
            "version": 1,
            "model": self.model,
            "format": "wav",
            "sample_rate": 24000,
        }

    def synthesize(
        self,
        segment: ScriptSegment,
        character: CharacterProfile,
        voice: VoicePreset,
        output_path: Path,
    ) -> dict[str, object]:
        body = {
            "model": self.model,
            "input": {
                "text": segment.text,
                "voice": voice.provider_voice,
                "format": "wav",
                "sample_rate": 24000,
                "rate": round(voice.browser_rate, 2),
                "pitch": round(voice.browser_pitch, 2),
                "language_hints": ["zh"],
                "enable_aigc_tag": True,
            },
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            audio = payload["output"]["audio"]
            audio_url = str(audio["url"])
            parsed = urllib.parse.urlparse(audio_url)
            if parsed.scheme not in {"https", "http"}:
                raise RuntimeError("TTS 返回了不受支持的音频 URL")
            download_request = urllib.request.Request(
                audio_url, headers={"User-Agent": "MultiVoiceAudiobook/0.8"}
            )
            with urllib.request.urlopen(
                download_request, timeout=self.timeout
            ) as response:
                audio_bytes = response.read()
            if len(audio_bytes) < 44:
                raise RuntimeError("TTS 返回的 WAV 文件为空或损坏")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(audio_bytes)
            return {
                "provider": self.name,
                "model": self.model,
                "request_id": payload.get("request_id", ""),
                "characters": payload.get("usage", {}).get(
                    "characters", len(segment.text)
                ),
                "audio_id": audio.get("id", ""),
            }
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"百炼 TTS 请求失败（HTTP {exc.code}）。"
                "请检查地域、模型与音色是否匹配，并在供应商控制台查看请求详情。"
            ) from exc
        except (KeyError, json.JSONDecodeError, urllib.error.URLError) as exc:
            raise RuntimeError(f"百炼 TTS 返回异常：{type(exc).__name__}") from exc
