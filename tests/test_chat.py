import unittest

from audiobook_app.chat import build_chat_context
from audiobook_app.models import CharacterProfile


class ChatContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.character = CharacterProfile(
            id="char-linxia",
            name="林夏",
            aliases=["小夏"],
            evidence=["林夏抱紧书包"],
        )

    def test_selects_character_and_question_relevant_passages(self) -> None:
        unrelated = "雨落在空无一人的站台。" * 200
        source = (
            f"{unrelated}\n\n"
            "林夏抱紧书包，望向北城的方向。\n\n"
            "“我必须去北城送信。”小夏说。\n\n"
            f"{unrelated}"
        )

        context = build_chat_context(
            source,
            self.character,
            "你为什么要去北城送信？",
            max_characters=2_000,
        )

        self.assertIn("林夏抱紧书包", context.text)
        self.assertIn("北城送信", context.text)
        self.assertLess(context.selected_characters, context.source_characters)
        self.assertTrue(context.truncated)

    def test_alias_mentions_are_selected(self) -> None:
        source = "开场。\n\n小夏转过身：“等我回来。”\n\n结尾。"

        context = build_chat_context(source, self.character, "你会回来吗？")

        self.assertIn("小夏转过身", context.text)

    def test_hard_character_limit_includes_labels_and_separators(self) -> None:
        source = "\n\n".join(
            f"林夏在第 {index} 个场景里说：“我记得这件事。”" * 20
            for index in range(30)
        )

        context = build_chat_context(
            source,
            self.character,
            "你记得什么？",
            max_characters=1_500,
        )

        self.assertLessEqual(len(context.text), 1_500)
        self.assertEqual(context.selected_characters, len(context.text))
        self.assertTrue(context.truncated)

    def test_falls_back_to_opening_when_no_terms_match(self) -> None:
        source = "这是开场背景。\n\n第二个场景。"

        context = build_chat_context(source, self.character, "告诉我你是谁")

        self.assertIn("这是开场背景", context.text)
        self.assertGreaterEqual(context.passage_count, 1)


if __name__ == "__main__":
    unittest.main()
