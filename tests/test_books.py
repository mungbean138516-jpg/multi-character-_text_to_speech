import unittest

from audiobook_app.books import BookChapter, BookProject, PROJECT_SCHEMA
from audiobook_app.models import AnalysisResult, CharacterProfile, ScriptSegment
from audiobook_app.registry import CharacterRegistry


class BookProjectTests(unittest.TestCase):
    def test_project_round_trip_keeps_chapter_analysis_and_registry(self) -> None:
        analysis = AnalysisResult(
            characters=[
                CharacterProfile(
                    id="narrator",
                    name="旁白",
                    voice_id="narrator_f",
                )
            ],
            segments=[
                ScriptSegment(
                    id="seg_1",
                    kind="narration",
                    text="雨停了。",
                    speaker_id="narrator",
                )
            ],
            pronunciations={"单": "善"},
        )
        project = BookProject(
            title="北城来信",
            author="测试作者",
            chapters=[
                BookChapter(
                    id="chapter_1",
                    title="第一章",
                    text="雨停了。",
                    analysis=analysis,
                )
            ],
            character_registry=CharacterRegistry(
                characters=analysis.characters
            ),
            pronunciations={"单": "善"},
        )

        payload = project.to_dict()
        restored = BookProject.from_dict(payload)

        self.assertEqual(payload["schema"], PROJECT_SCHEMA)
        self.assertEqual(restored.title, "北城来信")
        self.assertEqual(restored.chapters[0].analysis.segments[0].text, "雨停了。")
        self.assertEqual(restored.pronunciations, {"单": "善"})
        self.assertEqual(
            restored.character_registry.characters[0].id,
            "narrator",
        )

    def test_rejects_unrelated_json_file(self) -> None:
        with self.assertRaisesRegex(ValueError, "不是声场"):
            BookProject.from_dict({"title": "普通 JSON"})


if __name__ == "__main__":
    unittest.main()
