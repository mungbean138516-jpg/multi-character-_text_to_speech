from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import wave
from pathlib import Path
from uuid import uuid4

from .models import AnalysisResult, CharacterProfile, ScriptSegment
from .providers.base import TTSProvider
from .voices import VoicePreset, get_voice


def concatenate_wavs(
    input_paths: list[Path], output_path: Path, pause_ms: int = 220
) -> None:
    if not input_paths:
        raise ValueError("没有可合并的音频片段")
    params: tuple[int, int, int] | None = None
    chunks: list[bytes] = []
    for path in input_paths:
        with wave.open(str(path), "rb") as audio:
            current = (
                audio.getnchannels(),
                audio.getsampwidth(),
                audio.getframerate(),
            )
            if params is None:
                params = current
            elif current != params:
                raise ValueError(
                    f"WAV 参数不一致：{path.name} 为 {current}，预期 {params}"
                )
            chunks.append(audio.readframes(audio.getnframes()))
    assert params is not None
    channels, sample_width, sample_rate = params
    silence_frames = int(sample_rate * max(0, pause_ms) / 1000)
    silence = b"\x00" * silence_frames * channels * sample_width
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(sample_width)
        output.setframerate(sample_rate)
        for index, chunk in enumerate(chunks):
            if index:
                output.writeframes(silence)
            output.writeframes(chunk)


def mp3_is_available() -> bool:
    return shutil.which("ffmpeg") is not None


def encode_mp3(input_path: Path, output_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("当前服务器未安装 ffmpeg，暂不能输出 MP3")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(output_path),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )
    if process.returncode or not output_path.is_file() or output_path.stat().st_size == 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("MP3 转码失败，请检查服务器 ffmpeg 配置")


def _validate_wav(path: Path) -> tuple[int, int, int]:
    try:
        with wave.open(str(path), "rb") as audio:
            params = (
                audio.getnchannels(),
                audio.getsampwidth(),
                audio.getframerate(),
            )
            if audio.getnframes() <= 0:
                raise ValueError("音频片段没有采样帧")
    except (wave.Error, EOFError, FileNotFoundError) as exc:
        raise ValueError(f"无效的 WAV 音频：{path.name}") from exc
    return params


def _prepared_segments(
    analysis: AnalysisResult,
    *,
    max_characters: int,
    max_segments: int,
) -> list[tuple[ScriptSegment, CharacterProfile, VoicePreset]]:
    if not analysis.segments:
        raise ValueError("没有可生成的脚本片段")
    if len(analysis.segments) > max_segments:
        raise ValueError(f"单次最多生成 {max_segments} 个片段")
    total_characters = sum(len(segment.text) for segment in analysis.segments)
    if total_characters > max_characters:
        raise ValueError(f"单次最多生成 {max_characters} 个字符")

    characters = {character.id: character for character in analysis.characters}
    prepared: list[tuple[ScriptSegment, CharacterProfile, VoicePreset]] = []
    for segment in analysis.segments:
        if not segment.text:
            raise ValueError(f"{segment.id} 没有可生成的文本")
        character = characters.get(segment.speaker_id)
        if character is None:
            raise ValueError(f"{segment.id} 引用了不存在的角色")
        prepared.append((segment, character, get_voice(character.voice_id)))
    return prepared


def segment_cache_key(
    provider: TTSProvider,
    segment: ScriptSegment,
    voice: VoicePreset,
) -> str:
    value = {
        "schema": 1,
        "provider": provider.cache_identity(),
        "text": segment.text,
        "emotion": segment.emotion,
        "voice": {
            "id": voice.id,
            "provider_voice": voice.provider_voice,
            "pitch": voice.browser_pitch,
            "rate": voice.browser_rate,
        },
    }
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _cache_path(cache_root: Path, cache_key: str) -> Path:
    return cache_root / cache_key[:2] / f"{cache_key}.wav"


def _cache_is_valid(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        _validate_wav(path)
    except ValueError:
        return False
    return True


def _store_cache(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{uuid4().hex}.tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)


def build_render_plan(
    analysis: AnalysisResult,
    provider: TTSProvider,
    cache_root: Path | None,
    *,
    max_characters: int = 20_000,
    max_segments: int = 120,
    price_per_10k_cny: float | None = None,
) -> dict[str, object]:
    prepared = _prepared_segments(
        analysis,
        max_characters=max_characters,
        max_segments=max_segments,
    )
    cached_segments = 0
    estimated_billable_characters = 0
    for segment, _character, voice in prepared:
        cache_hit = False
        if cache_root is not None:
            key = segment_cache_key(provider, segment, voice)
            cache_hit = _cache_is_valid(_cache_path(cache_root, key))
        if cache_hit:
            cached_segments += 1
        else:
            estimated_billable_characters += len(segment.text)

    estimated_cost = None
    if price_per_10k_cny is not None:
        estimated_cost = round(
            estimated_billable_characters * price_per_10k_cny / 10_000,
            4,
        )
    return {
        "provider": provider.name,
        "segments": len(prepared),
        "billable_characters": sum(len(item[0].text) for item in prepared),
        "cached_segments": cached_segments,
        "estimated_requests": len(prepared) - cached_segments,
        "estimated_billable_characters": estimated_billable_characters,
        "price_per_10k_cny": price_per_10k_cny,
        "estimated_cost_cny": estimated_cost,
    }


def render_audiobook(
    analysis: AnalysisResult,
    provider: TTSProvider,
    output_root: Path,
    *,
    max_characters: int = 20_000,
    max_segments: int = 120,
    cache_root: Path | None = None,
    max_attempts: int = 2,
    output_format: str = "wav",
) -> dict[str, object]:
    if output_format not in {"wav", "mp3"}:
        raise ValueError("输出格式只支持 WAV 或 MP3")
    if output_format == "mp3" and not mp3_is_available():
        raise ValueError("当前服务器未安装 ffmpeg，暂不能输出 MP3")
    prepared = _prepared_segments(
        analysis,
        max_characters=max_characters,
        max_segments=max_segments,
    )
    total_characters = sum(len(segment.text) for segment in analysis.segments)
    max_attempts = max(1, min(int(max_attempts), 3))

    job_id = uuid4().hex[:12]
    job_dir = output_root / job_id
    segment_dir = job_dir / "segments"
    segment_dir.mkdir(parents=True, exist_ok=False)
    audio_paths: list[Path] = []
    manifest_segments: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    cache_hits = 0
    synthesized_segments = 0
    for index, (segment, character, voice) in enumerate(prepared, start=1):
        output_path = segment_dir / f"{index:03d}_{segment.id}.wav"
        cache_key = segment_cache_key(provider, segment, voice)
        cached_path = _cache_path(cache_root, cache_key) if cache_root else None
        metadata: dict[str, object]

        if cached_path is not None and _cache_is_valid(cached_path):
            shutil.copyfile(cached_path, output_path)
            metadata = {
                "provider": provider.name,
                "cache_hit": True,
                "cache_key": cache_key,
            }
            cache_hits += 1
        else:
            last_error = ""
            metadata = {}
            for attempt in range(1, max_attempts + 1):
                output_path.unlink(missing_ok=True)
                try:
                    metadata = dict(
                        provider.synthesize(
                            segment,
                            character,
                            voice,
                            output_path,
                        )
                    )
                    _validate_wav(output_path)
                    metadata.update(
                        {
                            "cache_hit": False,
                            "cache_key": cache_key,
                            "attempts": attempt,
                        }
                    )
                    synthesized_segments += 1
                    if cached_path is not None:
                        _store_cache(output_path, cached_path)
                    break
                except (RuntimeError, ValueError) as exc:
                    last_error = str(exc)[:240]
            else:
                output_path.unlink(missing_ok=True)
                failure = {
                    "segment_id": segment.id,
                    "index": index,
                    "message": last_error or "语音供应商未能生成该片段",
                }
                failures.append(failure)
                manifest_segments.append(
                    {
                        "status": "failed",
                        "segment": segment.to_dict(),
                        "character": character.to_dict(),
                        "voice": voice.to_dict(),
                        "error": failure,
                    }
                )
                continue

        audio_paths.append(output_path)
        manifest_segments.append(
            {
                "status": "completed",
                "segment": segment.to_dict(),
                "character": character.to_dict(),
                "voice": voice.to_dict(),
                "provider": metadata,
                "file": output_path.name,
            }
        )

    status = "partial" if failures else "completed"
    final_wav_path: Path | None = None
    final_audio_path: Path | None = None
    if not failures:
        final_wav_path = job_dir / "audiobook.wav"
        concatenate_wavs(audio_paths, final_wav_path)
        final_audio_path = final_wav_path
        if output_format == "mp3":
            final_audio_path = job_dir / "audiobook.mp3"
            encode_mp3(final_wav_path, final_audio_path)

    manifest = {
        "job_id": job_id,
        "status": status,
        "provider": provider.name,
        "requested_format": output_format,
        "total_characters": total_characters,
        "cache_hits": cache_hits,
        "synthesized_segments": synthesized_segments,
        "failed_segments": failures,
        "segments": manifest_segments,
        "audio_file": final_audio_path.name if final_audio_path else None,
        "wav_file": final_wav_path.name if final_wav_path else None,
    }
    (job_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "job_id": job_id,
        "status": status,
        "provider": provider.name,
        "format": output_format,
        "total_characters": total_characters,
        "segment_count": len(audio_paths),
        "cache_hits": cache_hits,
        "synthesized_segments": synthesized_segments,
        "failed_segments": failures,
        "retryable": bool(failures),
        "audio_url": (
            f"/outputs/{job_id}/{final_audio_path.name}"
            if final_audio_path
            else None
        ),
        "wav_url": (
            f"/outputs/{job_id}/{final_wav_path.name}"
            if final_wav_path
            else None
        ),
        "manifest_url": f"/outputs/{job_id}/manifest.json",
    }
