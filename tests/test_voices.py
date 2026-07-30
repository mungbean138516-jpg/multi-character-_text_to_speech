import unittest

from audiobook_app.models import CharacterProfile
from audiobook_app.voices import (
    FREE_VOICE_IDS,
    VOICE_BY_ID,
    VOICE_CATALOG,
    cast_characters,
    catalog_as_dicts,
)


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

    def test_child_is_specific_and_elder_uses_natural_adult_fallback(self) -> None:
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
            (elder_voice.gender, elder_voice.age_group), ("female", "adult")
        )
        self.assertTrue(
            all(character.voice_id in FREE_VOICE_IDS for character in characters)
        )

    def test_free_catalog_is_five_roles_and_premium_remains_visible(self) -> None:
        catalog = catalog_as_dicts()
        free = [voice for voice in catalog if voice["access"] == "free"]
        premium = [voice for voice in catalog if voice["access"] == "premium"]

        self.assertEqual({voice["id"] for voice in free}, set(FREE_VOICE_IDS))
        self.assertEqual(len(free), 5)
        self.assertGreater(len(premium), 0)

        automatic = CharacterProfile(
            id="automatic",
            name="旧版自动角色",
            gender="male",
            age_group="adult",
            voice_id="adult_m_bright",
        )
        locked = CharacterProfile(
            id="locked",
            name="人工确认角色",
            gender="male",
            age_group="adult",
            voice_id="adult_m_bright",
            locked=True,
        )
        cast_characters([automatic, locked])
        self.assertIn(automatic.voice_id, FREE_VOICE_IDS)
        self.assertEqual(locked.voice_id, "adult_m_bright")

    def test_catalog_is_curated_and_provider_ids_are_unique(self) -> None:
        self.assertGreaterEqual(len(VOICE_CATALOG), 20)
        self.assertLessEqual(len(VOICE_CATALOG), 30)
        provider_ids = [voice.provider_voice for voice in VOICE_CATALOG]
        self.assertEqual(len(provider_ids), len(set(provider_ids)))
        self.assertTrue(
            all(voice.provider_voice.endswith("_v3") for voice in VOICE_CATALOG)
        )

    def test_browser_approximations_stay_in_natural_ranges(self) -> None:
        self.assertTrue(
            all(0.92 <= voice.browser_pitch <= 1.10 for voice in VOICE_CATALOG)
        )
        self.assertTrue(
            all(0.88 <= voice.browser_rate <= 1.08 for voice in VOICE_CATALOG)
        )


if __name__ == "__main__":
    unittest.main()
