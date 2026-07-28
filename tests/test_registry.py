import unittest

from audiobook_app.models import AnalysisResult, CharacterProfile, ScriptSegment
from audiobook_app.registry import CharacterRegistry, MINOR_CHARACTERS_ID


def chapter(character: CharacterProfile, segment_id: str = "seg") -> AnalysisResult:
    return AnalysisResult(
        characters=[
            CharacterProfile(
                id="narrator",
                name="旁白",
                voice_id="narrator_f",
            ),
            character,
        ],
        segments=[
            ScriptSegment(
                id=segment_id,
                kind="dialogue",
                text="你好。",
                speaker_id=character.id,
            )
        ],
    )


class CharacterRegistryTests(unittest.TestCase):
    def test_alias_keeps_stable_id_and_voice_across_chapters(self) -> None:
        registry = CharacterRegistry()
        first = chapter(
            CharacterProfile(
                id="lin_xia",
                name="林夏",
                aliases=["小夏"],
                gender="female",
                age_group="adult",
                voice_id="adult_f_warm",
            )
        )
        registry.reconcile(first)
        second = chapter(
            CharacterProfile(
                id="temporary",
                name="小夏",
                aliases=["林夏"],
                voice_id="adult_f_soft",
            ),
            "seg_2",
        )
        registry.reconcile(second)

        self.assertEqual(second.characters[1].id, "lin_xia")
        self.assertEqual(second.characters[1].voice_id, "adult_f_warm")
        self.assertEqual(second.segments[0].speaker_id, "lin_xia")
        self.assertEqual(registry.dialogue_counts["lin_xia"], 2)

    def test_locked_character_wins_over_future_analysis(self) -> None:
        registry = CharacterRegistry(
            characters=[
                CharacterProfile(
                    id="narrator",
                    name="旁白",
                    voice_id="narrator_f",
                ),
                CharacterProfile(
                    id="chen_mo",
                    name="陈默",
                    gender="male",
                    age_group="adult",
                    voice_id="adult_m_calm",
                    locked=True,
                ),
            ]
        )
        result = chapter(
            CharacterProfile(
                id="new_id",
                name="陈默",
                gender="female",
                age_group="teen",
                voice_id="teen_f",
            )
        )
        registry.reconcile(result)

        self.assertEqual(result.characters[1].id, "chen_mo")
        self.assertEqual(result.characters[1].gender, "male")
        self.assertEqual(result.characters[1].voice_id, "adult_m_calm")

    def test_overflow_is_grouped_without_losing_dialogue(self) -> None:
        registry = CharacterRegistry(primary_limit=2)
        for index in range(3):
            result = chapter(
                CharacterProfile(
                    id=f"person_{index}",
                    name=f"人物{index}",
                    voice_id="adult_m_bright",
                ),
                f"seg_{index}",
            )
            registry.reconcile(result)

        self.assertEqual(registry.primary_count, 2)
        self.assertEqual(result.segments[0].speaker_id, MINOR_CHARACTERS_ID)
        self.assertEqual(result.characters[1].name, "其他角色")
        self.assertIn("人物2", registry.minor_character_names)
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
