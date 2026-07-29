import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from audiobook_app.models import CharacterProfile, ScriptSegment
from audiobook_app.providers.macos import (
    MacOSLocalTTSProvider,
    MacOSVoice,
    list_macos_chinese_voices,
    select_macos_voice,
)
from audiobook_app.voices import VOICE_BY_ID


class MacOSLocalProviderTests(unittest.TestCase):
    def test_installed_chinese_voice_list_is_parsed(self) -> None:
        listing = "\n".join(
            [
                "Ting-Ting            zh_CN    # 你好！",
                "Li-mu                zh_CN    # 你好！",
                "Samantha             en_US    # Hello!",
            ]
        )
        completed = subprocess.CompletedProcess(
            ["/usr/bin/say", "-v", "?"],
            0,
            stdout=listing,
            stderr="",
        )
        with patch(
            "audiobook_app.providers.macos.subprocess.run",
            return_value=completed,
        ):
            voices = list_macos_chinese_voices("/usr/bin/say")

        self.assertEqual(
            voices,
            (
                MacOSVoice("Ting-Ting", "zh_CN"),
                MacOSVoice("Li-mu", "zh_CN"),
            ),
        )

    def test_natural_voice_is_preferred_over_novelty_voice(self) -> None:
        voices = (
            MacOSVoice("Eddy (中文（中国大陆）)", "zh_CN"),
            MacOSVoice("Ting-Ting", "zh_CN"),
            MacOSVoice("Li-mu", "zh_CN"),
        )

        child = select_macos_voice(voices, VOICE_BY_ID["child_m"])
        elder = select_macos_voice(voices, VOICE_BY_ID["elder_f"])

        self.assertEqual(child.name, "Li-mu")
        self.assertEqual(elder.name, "Ting-Ting")

    def test_provider_writes_real_wav_pipeline_output(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(command, **kwargs):
            del kwargs
            calls.append(command)
            if command[0] == "/usr/bin/say":
                target = Path(command[command.index("-o") + 1])
                target.write_bytes(b"FORM" + b"\x00" * 64)
            else:
                target = Path(command[-1])
                with wave.open(str(target), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(24_000)
                    audio.writeframes(b"\x00\x00" * 2_400)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        provider = MacOSLocalTTSProvider(
            voices=(MacOSVoice("Ting-Ting", "zh_CN"),),
            say_path="/usr/bin/say",
            afconvert_path="/usr/bin/afconvert",
            runner=fake_runner,
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "line.wav"
            metadata = provider.synthesize(
                ScriptSegment(
                    id="seg_001",
                    kind="dialogue",
                    text="我们出发吧。",
                    speaker_id="heroine",
                ),
                CharacterProfile(id="heroine", name="林夏"),
                VOICE_BY_ID["adult_f_warm"],
                output,
            )
            with wave.open(str(output), "rb") as audio:
                params = (
                    audio.getnchannels(),
                    audio.getsampwidth(),
                    audio.getframerate(),
                )

        self.assertEqual(params, (1, 2, 24_000))
        self.assertEqual(metadata["system_voice"], "Ting-Ting")
        self.assertEqual(len(calls), 2)
        self.assertIn("-f", calls[0])
        self.assertIn("LEI16@24000", calls[1])


if __name__ == "__main__":
    unittest.main()
