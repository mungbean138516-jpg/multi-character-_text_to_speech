import io
import unittest
import zipfile

from audiobook_app.directing import consistency_check, direct_text
from audiobook_app.document_import import parse_docx


def make_docx(paragraphs: list[str]) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return output.getvalue()


class DocumentImportTests(unittest.TestCase):
    def test_docx_is_split_on_chapter_headings(self) -> None:
        project = parse_docx(
            make_docx(["第一章 雨夜", "雨停了。", "第二章 北城", "火车进站。"]),
            "北城来信.docx",
        )
        self.assertEqual(project.source_type, "docx")
        self.assertEqual(
            [chapter.title for chapter in project.chapters],
            ["第一章 雨夜", "第二章 北城"],
        )
        self.assertEqual(project.chapters[1].text, "火车进站。")


class QualityRuleTests(unittest.TestCase):
    def test_rule_director_combines_text_features(self) -> None:
        result = direct_text("他沉默片刻，低声说道：“别走！”")
        self.assertLess(result["pace"], 1)
        self.assertGreaterEqual(result["pause_after_ms"], 600)
        self.assertIn("低声表达", result["reasons"])

    def test_consistency_check_finds_age_and_voice_drift(self) -> None:
        def chapter(title: str, age: str, voice: str) -> dict:
            return {
                "id": title,
                "title": title,
                "analysis": {
                    "characters": [{
                        "id": "lin_xia",
                        "name": "林夏",
                        "age_group": age,
                        "gender": "female",
                        "voice_id": voice,
                        "traits": ["冷静"],
                    }]
                },
            }

        result = consistency_check([
            chapter("第一章", "adult", "adult_f_warm"),
            chapter("第二十章", "teen", "teen_f_bright"),
        ])
        self.assertEqual(result["issue_count"], 2)
        self.assertEqual(
            {issue["field"] for issue in result["issues"]},
            {"age_group", "voice_id"},
        )


if __name__ == "__main__":
    unittest.main()
