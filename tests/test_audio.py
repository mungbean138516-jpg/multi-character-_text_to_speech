import tempfile
import unittest
import wave
from pathlib import Path

from audiobook_app.audio import concatenate_wavs, render_audiobook
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


if __name__ == "__main__":
    unittest.main()

