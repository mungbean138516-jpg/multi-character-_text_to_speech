import io
import unittest
import zipfile

from audiobook_app.epub import MAX_CHAPTER_CHARACTERS, parse_epub


def make_epub(chapter_one: str, chapter_two: str = "") -> bytes:
    container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
      media-type="application/oebps-package+xml" />
  </rootfiles>
</container>"""
    second_item = (
        '<item id="c2" href="chapter-2.xhtml" media-type="application/xhtml+xml"/>'
        if chapter_two
        else ""
    )
    second_spine = '<itemref idref="c2"/>' if chapter_two else ""
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
  <metadata><dc:title>北城来信</dc:title><dc:creator>测试作者</dc:creator></metadata>
  <manifest>
    <item id="c1" href="chapter-1.xhtml" media-type="application/xhtml+xml"/>
    {second_item}
  </manifest>
  <spine>{second_spine}<itemref idref="c1"/></spine>
</package>"""
    chapter_template = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title}</title>'
        '<style>不应朗读</style></head><body><h1>{title}</h1><p>{body}</p>'
        '<script>不应朗读</script></body></html>'
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr(
            "OEBPS/chapter-1.xhtml",
            chapter_template.format(title="第一章", body=chapter_one),
        )
        if chapter_two:
            archive.writestr(
                "OEBPS/chapter-2.xhtml",
                chapter_template.format(title="第二章", body=chapter_two),
            )
    return output.getvalue()


class EpubImportTests(unittest.TestCase):
    def test_reads_metadata_and_spine_order(self) -> None:
        project = parse_epub(make_epub("第一段。", "第二段。"), "novel.epub")

        self.assertEqual(project.title, "北城来信")
        self.assertEqual(project.author, "测试作者")
        self.assertEqual([chapter.title for chapter in project.chapters], ["第二章", "第一章"])
        self.assertIn("第二段", project.chapters[0].text)
        self.assertEqual(project.chapters[0].text.count("第二章"), 1)
        self.assertNotIn("不应朗读", project.chapters[0].text)

    def test_splits_oversized_chapter_for_analysis(self) -> None:
        text = "这是很长的一句。" * (MAX_CHAPTER_CHARACTERS // 7 + 100)
        project = parse_epub(make_epub(text))

        self.assertGreater(len(project.chapters), 1)
        self.assertTrue(
            all(len(chapter.text) <= MAX_CHAPTER_CHARACTERS for chapter in project.chapters)
        )
        self.assertTrue(project.chapters[0].title.endswith("）"))

    def test_rejects_path_traversal(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("../escape.xhtml", "<p>bad</p>")
        with self.assertRaisesRegex(ValueError, "越界"):
            parse_epub(output.getvalue())

    def test_rejects_non_epub_zip(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("hello.txt", "hello")
        with self.assertRaisesRegex(ValueError, "container"):
            parse_epub(output.getvalue())

    def test_rejects_xml_entity_declarations(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(
                "META-INF/container.xml",
                '<!DOCTYPE x [<!ENTITY a "x">]><container>&a;</container>',
            )
        with self.assertRaisesRegex(ValueError, "XML 声明"):
            parse_epub(output.getvalue())


if __name__ == "__main__":
    unittest.main()
