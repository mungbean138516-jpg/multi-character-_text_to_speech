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


if __name__ == "__main__":
    unittest.main()
