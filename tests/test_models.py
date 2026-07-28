import unittest

from audiobook_app.models import AnalysisResult, CharacterProfile, ScriptSegment
from audiobook_app.qwen import QwenNovelAnalyzer


class ModelContractTests(unittest.TestCase):
    def test_aliases_and_locks_round_trip(self) -> None:
        analysis = AnalysisResult(
            characters=[
                CharacterProfile(
                    id="narrator",
                    name="旁白",
                    voice_id="narrator_f",
                ),
                CharacterProfile(
                    id="character",
                    name="陈伯",
                    aliases=["老陈", "陈伯", "老陈"],
                    voice_id="elder_m",
                    locked=True,
                ),
            ],
            segments=[
                ScriptSegment(
                    id="seg_001",
                    kind="dialogue",
                    text="出发吧。",
                    speaker_id="character",
                    locked=True,
                )
            ],
        )
        restored = AnalysisResult.from_dict(analysis.to_dict())
        self.assertEqual(restored.characters[1].aliases, ["老陈"])
        self.assertTrue(restored.characters[1].locked)
        self.assertTrue(restored.segments[0].locked)

    def test_qwen_alias_merges_into_existing_character(self) -> None:
        baseline = AnalysisResult(
            characters=[
                CharacterProfile(
                    id="narrator",
                    name="旁白",
                    voice_id="narrator_f",
                ),
                CharacterProfile(
                    id="character",
                    name="小陈",
                    voice_id="adult_m_bright",
                ),
            ],
            segments=[
                ScriptSegment(
                    id="seg_001",
                    kind="dialogue",
                    text="我来处理。",
                    speaker_id="character",
                )
            ],
        )
        merged = QwenNovelAnalyzer._merge(
            baseline,
            {
                "characters": [
                    {
                        "name": "陈默",
                        "aliases": ["小陈"],
                        "gender": "male",
                        "age_group": "adult",
                        "traits": ["沉稳"],
                        "confidence": 0.9,
                    }
                ],
                "speaker_assignments": {"seg_001": "陈默"},
            },
        )
        self.assertEqual(len(merged.characters), 2)
        self.assertIn("陈默", merged.characters[1].aliases)
        self.assertEqual(merged.segments[0].speaker_id, merged.characters[1].id)


if __name__ == "__main__":
    unittest.main()
