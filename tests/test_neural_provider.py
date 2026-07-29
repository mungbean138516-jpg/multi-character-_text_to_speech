import tempfile
import unittest
import wave
from pathlib import Path

from audiobook_app.models import CharacterProfile, ScriptSegment
from audiobook_app.providers.neural import (
    NEURAL_VOICE_BY_PRESET,
    NeuralVoicePackProvider,
    neural_pitch,
    neural_rate,
    select_neural_voice,
)
from audiobook_app.voices import VOICE_BY_ID


class NeuralVoicePackProviderTests(unittest.TestCase):
    def test_auto_cast_uses_nine_non_dialect_neural_voices(self) -> None:
        voices = set(NEURAL_VOICE_BY_PRESET.values())

        self.assertEqual(len(voices), 9)
        self.assertFalse(
            any(
                marker in voice
                for voice in voices
                for marker in ("zh-HK", "liaoning", "shaanxi")
            )
        )

    def test_age_specific_voices_do_not_use_extreme_pitch(self) -> None:
        child = VOICE_BY_ID["child_m"]
        elder = VOICE_BY_ID["elder_m"]

        self.assertEqual(
            select_neural_voice(child),
            "zh-CN-YunxiaNeural",
        )
        self.assertEqual(
            select_neural_voice(elder),
            "zh-TW-YunJheNeural",
        )
        self.assertEqual(neural_pitch(child), "+2Hz")
        self.assertEqual(neural_pitch(elder), "-2Hz")
        self.assertEqual(neural_rate(child), "+4%")
        self.assertEqual(neural_rate(elder), "-6%")

    def test_female_first_demo_roles_use_natural_neural_voices(self) -> None:
        self.assertEqual(
            select_neural_voice(VOICE_BY_ID["narrator_f"]),
            "zh-CN-XiaoxiaoNeural",
        )
        self.assertEqual(
            select_neural_voice(VOICE_BY_ID["adult_f_soft"]),
            "zh-CN-XiaoyiNeural",
        )
        self.assertEqual(
            select_neural_voice(VOICE_BY_ID["child_f"]),
            "zh-TW-HsiaoYuNeural",
        )

    def test_provider_converts_downloaded_mp3_to_valid_wav(self) -> None:
        calls: list[tuple[str, str, str, str]] = []

        def save_mp3(
            text: str,
            voice_name: str,
            rate: str,
            pitch: str,
            output_path: Path,
        ) -> None:
            calls.append((text, voice_name, rate, pitch))
            output_path.write_bytes(b"ID3" + b"\x00" * 200)

        def decode_mp3(source: Path, target: Path) -> None:
            self.assertTrue(source.is_file())
            with wave.open(str(target), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(24_000)
                audio.writeframes(b"\x00\x00" * 240)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "segment.wav"
            provider = NeuralVoicePackProvider(
                save_mp3=save_mp3,
                decode_mp3=decode_mp3,
            )
            metadata = provider.synthesize(
                ScriptSegment(
                    id="s1",
                    kind="dialogue",
                    text="火车来啦！",
                    speaker_id="girl",
                ),
                CharacterProfile(
                    id="girl",
                    name="小女孩",
                    gender="female",
                    age_group="child",
                    voice_id="child_f",
                ),
                VOICE_BY_ID["child_f"],
                output,
            )

            with wave.open(str(output), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertEqual(audio.getframerate(), 24_000)
                self.assertGreater(audio.getnframes(), 0)
            self.assertEqual(
                calls,
                [
                    (
                        "火车来啦！",
                        "zh-TW-HsiaoYuNeural",
                        "+4%",
                        "+2Hz",
                    )
                ],
            )
            self.assertEqual(metadata["provider"], "neural")
            self.assertEqual(metadata["character"], "小女孩")
            self.assertFalse(list(Path(directory).glob("*.edge.mp3")))


if __name__ == "__main__":
    unittest.main()
