from __future__ import annotations

import json
import wave
from pathlib import Path
from uuid import uuid4

from .models import AnalysisResult
from .providers.base import TTSProvider
from .voices import get_voice


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


def render_audiobook(
    analysis: AnalysisResult,
    provider: TTSProvider,
    output_root: Path,
    *,
    max_characters: int = 20_000,
    max_segments: int = 120,
) -> dict[str, object]:
    characters = {character.id: character for character in analysis.characters}
    if len(analysis.segments) > max_segments:
        raise ValueError(f"单次最多生成 {max_segments} 个片段")
    total_characters = sum(len(segment.text) for segment in analysis.segments)
    if total_characters > max_characters:
        raise ValueError(f"单次最多生成 {max_characters} 个字符")

    job_id = uuid4().hex[:12]
    job_dir = output_root / job_id
    segment_dir = job_dir / "segments"
    segment_dir.mkdir(parents=True, exist_ok=False)
    audio_paths: list[Path] = []
    manifest_segments = []
    for index, segment in enumerate(analysis.segments, start=1):
        character = characters.get(segment.speaker_id)
        if character is None:
            raise ValueError(f"{segment.id} 引用了不存在的角色")
        voice = get_voice(character.voice_id)
        output_path = segment_dir / f"{index:03d}_{segment.id}.wav"
        metadata = provider.synthesize(segment, character, voice, output_path)
        audio_paths.append(output_path)
        manifest_segments.append(
            {
                "segment": segment.to_dict(),
                "character": character.to_dict(),
                "voice": voice.to_dict(),
                "provider": metadata,
                "file": output_path.name,
            }
        )

    final_path = job_dir / "audiobook.wav"
    concatenate_wavs(audio_paths, final_path)
    manifest = {
        "job_id": job_id,
        "provider": provider.name,
        "total_characters": total_characters,
        "segments": manifest_segments,
        "audio_file": final_path.name,
    }
    (job_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "job_id": job_id,
        "provider": provider.name,
        "total_characters": total_characters,
        "segment_count": len(audio_paths),
        "audio_url": f"/outputs/{job_id}/audiobook.wav",
        "manifest_url": f"/outputs/{job_id}/manifest.json",
    }

