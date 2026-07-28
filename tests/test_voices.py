import unittest

from audiobook_app.models import CharacterProfile
from audiobook_app.voices import VOICE_BY_ID, VOICE_CATALOG, cast_characters


class VoiceCastingTests(unittest.TestCase):
    def test_narrator_is_cast_to_narrator_voice(self) -> None:
        characters = [
            CharacterProfile(
                id="narrator",
                name="旁白",
                gender="female",
                age_group="adult",
            )
        ]
        cast_characters(characters)
        self.assertTrue(characters[0].voice_id.startswith("narrator"))

    def test_child_and_elder_receive_compatible_voices(self) -> None:
        characters = [
            CharacterProfile(
                id="child", name="小男孩", gender="male", age_group="child"
            ),
            CharacterProfile(
                id="elder", name="老奶奶", gender="female", age_group="elder"
            ),
        ]
        cast_characters(characters)
        child_voice = VOICE_BY_ID[characters[0].voice_id]
        elder_voice = VOICE_BY_ID[characters[1].voice_id]
        self.assertEqual((child_voice.gender, child_voice.age_group), ("male", "child"))
        self.assertEqual(
            (elder_voice.gender, elder_voice.age_group), ("female", "elder")
        )

    def test_catalog_is_curated_and_provider_ids_are_unique(self) -> None:
        self.assertGreaterEqual(len(VOICE_CATALOG), 20)
        self.assertLessEqual(len(VOICE_CATALOG), 30)
        provider_ids = [voice.provider_voice for voice in VOICE_CATALOG]
        self.assertEqual(len(provider_ids), len(set(provider_ids)))
        self.assertTrue(
            all(voice.provider_voice.endswith("_v3") for voice in VOICE_CATALOG)
        )


if __name__ == "__main__":
    unittest.main()
