import tempfile
import unittest
import wave
from pathlib import Path

from audiobook_app.audio import (
    build_render_plan,
    concatenate_wavs,
    mp3_is_available,
    render_audiobook,
)
from audiobook_app.models import AnalysisResult, CharacterProfile, ScriptSegment
from audiobook_app.providers.demo import DemoToneProvider


def make_silent_wav(path: Path, duration_seconds: float, sample_rate: int = 24000):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * int(duration_seconds * sample_rate))


class AudioPipelineTests(unittest.TestCase):
    def test_concatenate_wavs_inserts_pause(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.wav"
            second = root / "second.wav"
            output = root / "output.wav"
            make_silent_wav(first, 0.5)
            make_silent_wav(second, 0.5)
            concatenate_wavs([first, second], output, pause_ms=300)
            with wave.open(str(output), "rb") as audio:
                duration = audio.getnframes() / audio.getframerate()
            self.assertAlmostEqual(duration, 1.3, places=2)

    def test_demo_provider_renders_complete_job(self) -> None:
        analysis = AnalysisResult(
            characters=[
                CharacterProfile(
                    id="narrator",
                    name="旁白",
                    gender="female",
                    age_group="adult",
                    voice_id="narrator_f",
                ),
                CharacterProfile(
                    id="character",
                    name="角色",
                    voice_id="adult_m_bright",
                ),
            ],
            segments=[
                ScriptSegment(
                    id="seg_001",
                    kind="narration",
                    text="夜色落下。",
                    speaker_id="narrator",
                ),
                ScriptSegment(
                    id="seg_002",
                    kind="dialogue",
                    text="我们走吧。",
                    speaker_id="character",
                ),
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = render_audiobook(
                analysis, DemoToneProvider(), Path(tmp), max_characters=100
            )
            audio_path = (
                Path(tmp) / str(result["job_id"]) / "audiobook.wav"
            )
            manifest_path = (
                Path(tmp) / str(result["job_id"]) / "manifest.json"
            )
            self.assertTrue(audio_path.is_file())
            self.assertTrue(manifest_path.is_file())
            self.assertEqual(result["segment_count"], 2)

    def test_render_limit_is_enforced_before_provider_calls(self) -> None:
        analysis = AnalysisResult(
            characters=[
                CharacterProfile(
                    id="narrator", name="旁白", voice_id="narrator_f"
                )
            ],
            segments=[
                ScriptSegment(
                    id="seg_001",
                    kind="narration",
                    text="字" * 20,
                    speaker_id="narrator",
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "最多生成"):
                render_audiobook(
                    analysis,
                    DemoToneProvider(),
                    Path(tmp),
                    max_characters=10,
                )

    def test_segment_cache_avoids_duplicate_provider_calls(self) -> None:
        class CountingProvider(DemoToneProvider):
            def __init__(self):
                self.calls = 0

            def synthesize(self, *args, **kwargs):
                self.calls += 1
                return super().synthesize(*args, **kwargs)

        analysis = self._two_segment_analysis()
        provider = CountingProvider()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            first = render_audiobook(
                analysis, provider, root / "jobs", cache_root=cache
            )
            second = render_audiobook(
                analysis, provider, root / "jobs", cache_root=cache
            )
            plan = build_render_plan(analysis, provider, cache)
        self.assertEqual(first["cache_hits"], 0)
        self.assertEqual(second["cache_hits"], 2)
        self.assertEqual(provider.calls, 2)
        self.assertEqual(plan["estimated_requests"], 0)

    def test_failed_segment_can_retry_without_regenerating_successes(self) -> None:
        class FailOnceProvider(DemoToneProvider):
            def __init__(self):
                self.calls = 0
                self.failed = False

            def synthesize(self, segment, *args, **kwargs):
                self.calls += 1
                if segment.id == "seg_002" and not self.failed:
                    self.failed = True
                    raise RuntimeError("temporary provider failure")
                return super().synthesize(segment, *args, **kwargs)

        analysis = self._two_segment_analysis()
        provider = FailOnceProvider()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            first = render_audiobook(
                analysis,
                provider,
                root / "jobs",
                cache_root=cache,
                max_attempts=1,
            )
            second = render_audiobook(
                analysis,
                provider,
                root / "jobs",
                cache_root=cache,
                max_attempts=1,
            )
        self.assertEqual(first["status"], "partial")
        self.assertEqual(first["failed_segments"][0]["segment_id"], "seg_002")
        self.assertEqual(second["status"], "completed")
        self.assertEqual(second["cache_hits"], 1)
        self.assertEqual(provider.calls, 3)

    @unittest.skipUnless(mp3_is_available(), "ffmpeg is not installed")
    def test_mp3_output_is_created_when_ffmpeg_is_available(self) -> None:
        analysis = self._two_segment_analysis()
        with tempfile.TemporaryDirectory() as tmp:
            result = render_audiobook(
                analysis,
                DemoToneProvider(),
                Path(tmp),
                output_format="mp3",
            )
            output = Path(tmp) / str(result["job_id"]) / "audiobook.mp3"
            output_exists = output.is_file() and output.stat().st_size > 0
        self.assertEqual(result["format"], "mp3")
        self.assertTrue(output_exists)

    @staticmethod
    def _two_segment_analysis() -> AnalysisResult:
        return AnalysisResult(
            characters=[
                CharacterProfile(
                    id="narrator",
                    name="旁白",
                    gender="female",
                    age_group="adult",
                    voice_id="narrator_f",
                ),
                CharacterProfile(
                    id="character",
                    name="角色",
                    voice_id="adult_m_bright",
                ),
            ],
            segments=[
                ScriptSegment(
                    id="seg_001",
                    kind="narration",
                    text="夜色落下。",
                    speaker_id="narrator",
                ),
                ScriptSegment(
                    id="seg_002",
                    kind="dialogue",
                    text="我们走吧。",
                    speaker_id="character",
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
