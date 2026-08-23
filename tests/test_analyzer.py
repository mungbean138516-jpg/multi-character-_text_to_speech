import unittest

from audiobook_app.analyzer import HeuristicNovelAnalyzer


class HeuristicNovelAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = HeuristicNovelAnalyzer()

    def dialogue_rows(self, text: str):
        result = self.analyzer.analyze(text)
        characters = {character.id: character for character in result.characters}
        return [
            (characters[segment.speaker_id].name, segment.text, segment.confidence)
            for segment in result.segments
            if segment.kind == "dialogue"
        ]

    def test_speaker_before_quote(self) -> None:
        rows = self.dialogue_rows("张三说：“我来晚了。”")
        self.assertEqual(rows[0][0], "张三")
        self.assertEqual(rows[0][1], "我来晚了。")
        self.assertGreaterEqual(rows[0][2], 0.8)

    def test_speaker_after_quote(self) -> None:
        rows = self.dialogue_rows("“别动！”李警官低声说。")
        self.assertEqual(rows[0][0], "李警官")

    def test_action_before_quote(self) -> None:
        rows = self.dialogue_rows("林澈笑了笑：“当然可以。”")
        self.assertEqual(rows[0][0], "林澈")

    def test_role_alias_before_quote(self) -> None:
        rows = self.dialogue_rows(
            "长椅旁的老爷爷抬起头，缓慢地说道：“路还很长。”"
        )
        self.assertEqual(rows[0][0], "老爷爷")
        result = self.analyzer.analyze(
            "长椅旁的老爷爷抬起头，缓慢地说道：“路还很长。”"
        )
        profile = next(
            character for character in result.characters if character.name == "老爷爷"
        )
        self.assertEqual(profile.gender, "male")
        self.assertEqual(profile.age_group, "elder")

    def test_child_role_and_emotion(self) -> None:
        result = self.analyzer.analyze(
            "一个小男孩兴奋地叫道：“火车来啦！”"
        )
        characters = {character.id: character for character in result.characters}
        dialogue = next(
            segment for segment in result.segments if segment.kind == "dialogue"
        )
        self.assertEqual(characters[dialogue.speaker_id].name, "小男孩")
        self.assertEqual(characters[dialogue.speaker_id].age_group, "child")
        self.assertEqual(dialogue.emotion, "excited")

    def test_no_dialogue_uses_narrator(self) -> None:
        result = self.analyzer.analyze("雨一直下。站台上没有人。")
        self.assertEqual(len(result.segments), 1)
        self.assertEqual(result.segments[0].speaker_id, "narrator")
        self.assertTrue(result.warnings)

    def test_named_character_traits_do_not_borrow_age_from_next_sentence(self) -> None:
        result = self.analyzer.analyze(
            "“等等。”陈默喊道。旁边的老爷爷抬起头。"
        )
        profile = next(
            character for character in result.characters if character.name == "陈默"
        )
        self.assertEqual(profile.age_group, "unknown")

    def test_pronoun_with_turn_adverb_resolves_to_recent_character(self) -> None:
        rows = self.dialogue_rows(
            "林夏是个少女。林夏说：“我们出发吧。”"
            "她又问道：“地图带了吗？”"
        )

        self.assertEqual([row[0] for row in rows], ["林夏", "林夏"])

    def test_nested_chinese_quotes_remain_one_dialogue(self) -> None:
        rows = self.dialogue_rows(
            "林夏说：“她只留下一句『别回头。』然后就走了。”"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "林夏")
        self.assertEqual(
            rows[0][1],
            "她只留下一句『别回头。』然后就走了。",
        )

    def test_nested_same_style_quotes_use_balanced_stack(self) -> None:
        rows = self.dialogue_rows("陈默说：“外层“内层”仍在外层。”")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "外层“内层”仍在外层。")

    def test_unclosed_quote_is_kept_as_narration_with_warning(self) -> None:
        result = self.analyzer.analyze("林夏说：“这句话没有结束。")
        self.assertFalse(
            any(segment.kind == "dialogue" for segment in result.segments)
        )
        self.assertTrue(any("未闭合引号" in warning for warning in result.warnings))

    def test_ascii_double_quotes_are_supported(self) -> None:
        rows = self.dialogue_rows('陈默说："我们出发。"')
        self.assertEqual(rows[0][0], "陈默")
        self.assertEqual(rows[0][1], "我们出发。")


if __name__ == "__main__":
    unittest.main()
