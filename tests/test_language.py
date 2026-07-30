import unittest

from audiobook_app.language import detect_text_language


class TextLanguageDetectionTests(unittest.TestCase):
    def test_clear_english_text_is_detected(self) -> None:
        self.assertEqual(
            detect_text_language(
                "The train arrived at midnight, and Alice opened the door."
            ),
            "en",
        )

    def test_short_identifiers_do_not_switch_the_book_to_english(self) -> None:
        self.assertEqual(detect_text_language("API TTS voice"), "zh")

    def test_any_cjk_content_keeps_mixed_book_on_chinese_route(self) -> None:
        self.assertEqual(
            detect_text_language(
                "This chapter starts in English, but 林夏随后推开了门。"
            ),
            "zh",
        )


if __name__ == "__main__":
    unittest.main()
