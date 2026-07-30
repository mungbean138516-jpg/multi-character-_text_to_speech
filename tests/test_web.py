import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        for name, value in attrs:
            if name == "id" and value:
                self.ids.append(value)


class WebContractTests(unittest.TestCase):
    def test_all_javascript_element_bindings_exist_once(self) -> None:
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        collector = IdCollector()
        collector.feed(html)
        duplicates = {
            element_id
            for element_id in collector.ids
            if collector.ids.count(element_id) > 1
        }
        binding_block = re.search(
            r"for \(const id of \[(.*?)\]\) \{",
            javascript,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(binding_block)
        bound_ids = re.findall(r'"([A-Za-z][A-Za-z0-9]*)"', binding_block.group(1))

        self.assertEqual(duplicates, set())
        self.assertTrue(bound_ids)
        self.assertEqual(
            sorted(set(bound_ids) - set(collector.ids)),
            [],
        )

    def test_consumer_primary_actions_are_present(self) -> None:
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("自动识别角色", html)
        self.assertIn("开始生成", html)
        self.assertIn("这个字读错了", javascript)
        self.assertIn("重做这句", javascript)
        self.assertIn("高级设置", html)

    def test_natural_local_speech_replaces_user_facing_test_tones(self) -> None:
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="neuralRenderButton"', html)
        self.assertIn('id="localRenderButton"', html)
        self.assertNotIn('id="demoRenderButton"', html)
        self.assertIn("selectNaturalBrowserVoice", javascript)
        self.assertIn("NOVELTY_VOICE_HINTS", javascript)
        self.assertIn('segment.language === "en"', javascript)
        self.assertIn('"en-US" : "zh-CN"', javascript)
        self.assertIn("HIGH_QUALITY_BROWSER_VOICE_HINTS", javascript)
        self.assertIn('renderAudio("neural")', javascript)

    def test_book_project_controls_and_storage_contract_are_present(self) -> None:
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn(".epub", html)
        self.assertIn('id="bookPanel"', html)
        self.assertIn("打开书籍项目", html)
        self.assertIn("下载项目备份", html)
        self.assertIn("voxcast-book-project", javascript)
        self.assertIn("indexedDB", javascript)
        self.assertIn("await restoreDraft()", javascript)

    def test_progressive_render_controls_and_refresh_recovery_are_present(self) -> None:
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="renderJobPanel"', html)
        self.assertIn('id="renderProgress"', html)
        self.assertIn("播放已完成内容", html)
        self.assertIn("暂停生成", html)
        self.assertIn('requestJson("/api/render/jobs"', javascript)
        self.assertIn("/pause", javascript)
        self.assertIn("/resume", javascript)
        self.assertIn("render_job_ids", javascript)
        self.assertIn("restoreRenderJobForCurrentContext", javascript)

    def test_voice_similarity_offers_actionable_replacement(self) -> None:
        javascript = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("renderVoiceReplacementChoices", javascript)
        self.assertIn("replacement-preview", javascript)
        self.assertIn("replacement-apply", javascript)
        self.assertIn("applyReplacementVoice", javascript)


if __name__ == "__main__":
    unittest.main()
