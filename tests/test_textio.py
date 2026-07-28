import unittest

from audiobook_app.textio import decode_text_bytes


class TextDecodingTests(unittest.TestCase):
    def test_utf8_bom(self) -> None:
        decoded = decode_text_bytes(b"\xef\xbb\xbf" + "你好".encode("utf-8"))
        self.assertEqual(decoded.text, "你好")
        self.assertEqual(decoded.encoding, "UTF-8 BOM")

    def test_utf16_little_endian(self) -> None:
        decoded = decode_text_bytes(b"\xff\xfe" + "你好".encode("utf-16-le"))
        self.assertEqual(decoded.text, "你好")
        self.assertEqual(decoded.encoding, "UTF-16 LE")

    def test_gb18030(self) -> None:
        decoded = decode_text_bytes("旧车站".encode("gb18030"))
        self.assertEqual(decoded.text, "旧车站")
        self.assertEqual(decoded.encoding, "GB18030")

    def test_binary_control_characters_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "无法识别|控制字符"):
            decode_text_bytes(b"\x00\x01\x02\x03\x04")


if __name__ == "__main__":
    unittest.main()
