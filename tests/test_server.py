import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

import audiobook_app.server as app_server
from tests.test_epub import make_epub


class QuietHandler(app_server.AudiobookRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


class ServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.previous_output = app_server.OUTPUT_ROOT
        cls.previous_cache = app_server.CACHE_ROOT
        app_server.OUTPUT_ROOT = Path(cls.temporary.name) / "outputs"
        app_server.CACHE_ROOT = Path(cls.temporary.name) / "cache"
        cls.server = app_server.AudiobookHTTPServer(
            ("127.0.0.1", 0), QuietHandler
        )
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()
        cls.base_url = (
            f"http://127.0.0.1:{cls.server.server_address[1]}"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        app_server.OUTPUT_ROOT = cls.previous_output
        app_server.CACHE_ROOT = cls.previous_cache
        cls.temporary.cleanup()

    @classmethod
    def post(cls, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            cls.base_url + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    @classmethod
    def post_bytes(cls, path: str, data: bytes, filename: str) -> dict:
        request = urllib.request.Request(
            cls.base_url + path,
            data=data,
            headers={
                "Content-Type": "application/epub+zip",
                "X-VoxCast-Filename": urllib.parse.quote(filename),
            },
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    @classmethod
    def get_json(cls, path: str) -> dict:
        with urllib.request.urlopen(cls.base_url + path) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_analyze_render_download_and_cached_plan(self) -> None:
        analysis = self.post(
            "/api/analyze",
            {
                "mode": "local",
                "text": "林夏说：“她只说『别回头。』然后离开。”",
            },
        )
        first_plan = self.post(
            "/api/render/plan",
            {"provider": "demo", "analysis": analysis},
        )
        result = self.post(
            "/api/render",
            {
                "provider": "demo",
                "format": "wav",
                "analysis": analysis,
            },
        )
        with urllib.request.urlopen(self.base_url + result["audio_url"]) as response:
            audio = response.read()
        cached_plan = self.post(
            "/api/render/plan",
            {"provider": "demo", "analysis": analysis},
        )

        self.assertEqual(result["status"], "completed")
        self.assertGreater(first_plan["estimated_requests"], 0)
        self.assertGreater(len(audio), 44)
        self.assertEqual(cached_plan["estimated_requests"], 0)

    def test_auto_analysis_and_single_sentence_render(self) -> None:
        with patch.object(app_server, "qwen_is_configured", return_value=False):
            analysis = self.post(
                "/api/analyze",
                {
                    "mode": "auto",
                    "text": "雨停了。林夏说：“出发吧。”陈默点了点头。",
                },
            )
        target = analysis["segments"][-1]
        result = self.post(
            "/api/render/segment",
            {
                "provider": "demo",
                "analysis": analysis,
                "segment_id": target["id"],
            },
        )
        with urllib.request.urlopen(self.base_url + result["audio_url"]) as response:
            audio = response.read()

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["segment_id"], target["id"])
        self.assertEqual(result["segment_count"], 1)
        self.assertGreater(len(audio), 44)

    def test_private_cache_path_is_not_served(self) -> None:
        for private_root in ("_cache", "_jobs"):
            with self.subTest(private_root=private_root):
                with self.assertRaises(urllib.error.HTTPError) as context:
                    urllib.request.urlopen(
                        self.base_url
                        + f"/outputs/{private_root}/not-public.json"
                    )
                self.assertEqual(context.exception.code, 404)

    def test_background_render_job_exposes_playable_segments(self) -> None:
        analysis = self.post(
            "/api/analyze",
            {
                "mode": "local",
                "text": "夜色落下。林夏说：“我们出发吧。”远处传来汽笛声。",
            },
        )
        created = self.post(
            "/api/render/jobs",
            {
                "provider": "demo",
                "format": "wav",
                "analysis": analysis,
                "chapter_id": "chapter_1",
                "chapter_title": "第一章",
            },
        )
        deadline = time.monotonic() + 3
        result = created
        while (
            result["status"] in {"queued", "running", "pausing"}
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
            result = self.get_json(
                f"/api/render/jobs/{created['job_id']}"
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["progress_percent"], 100)
        self.assertEqual(
            len(result["playable_segments"]),
            result["total_segments"],
        )
        first_audio_url = result["playable_segments"][0]["audio_url"]
        with urllib.request.urlopen(
            self.base_url + first_audio_url
        ) as response:
            first_audio = response.read()
        with urllib.request.urlopen(
            self.base_url + result["audio_url"]
        ) as response:
            final_audio = response.read()
        self.assertGreater(len(first_audio), 44)
        self.assertGreater(len(final_audio), len(first_audio))

    def test_epub_import_returns_book_project(self) -> None:
        project = self.post_bytes(
            "/api/import/epub",
            make_epub("雨停了。", "火车进站了。"),
            "北城来信.epub",
        )

        self.assertEqual(project["schema"], "voxcast-book-project")
        self.assertEqual(project["title"], "北城来信")
        self.assertEqual(len(project["chapters"]), 2)
        self.assertEqual(project["source_name"], "北城来信.epub")

    def test_analysis_respects_locked_book_character(self) -> None:
        analysis = self.post(
            "/api/analyze",
            {
                "mode": "local",
                "text": "陈默说：“出发吧。”",
                "character_registry": {
                    "primary_limit": 10,
                    "characters": [
                        {
                            "id": "narrator",
                            "name": "旁白",
                            "voice_id": "narrator_f",
                        },
                        {
                            "id": "book_chen_mo",
                            "name": "陈默",
                            "gender": "male",
                            "age_group": "adult",
                            "voice_id": "adult_m_calm",
                            "locked": True,
                        },
                    ],
                },
            },
        )

        character = next(
            item for item in analysis["characters"] if item["name"] == "陈默"
        )
        self.assertEqual(character["id"], "book_chen_mo")
        self.assertEqual(character["voice_id"], "adult_m_calm")
        self.assertEqual(
            analysis["segments"][-1]["speaker_id"],
            "book_chen_mo",
        )
        self.assertEqual(
            analysis["character_registry"]["primary_count"],
            1,
        )

    def test_config_exposes_optional_neural_voice_pack(self) -> None:
        with patch.object(
            app_server,
            "neural_voice_pack_is_available",
            return_value=True,
        ):
            config = self.get_json("/api/config")

        self.assertTrue(config["providers"]["neural"]["ready"])
        self.assertTrue(config["providers"]["neural"]["experimental"])
        self.assertIn(
            "edge-tts",
            config["providers"]["neural"]["install_command"],
        )

    def test_character_chat_returns_the_selected_character_reply(self) -> None:
        analysis = self.post(
            "/api/analyze",
            {"mode": "local", "text": "林夏说：“我们出发吧。”"},
        )
        character = next(
            item for item in analysis["characters"] if item["name"] == "林夏"
        )
        with patch.object(
            app_server,
            "chat_with_character",
            return_value="我已经准备好了。",
        ) as chat:
            result = self.post(
                "/api/character-chat",
                {
                    "analysis": analysis,
                    "character_id": character["id"],
                    "source_text": "林夏说：“我们出发吧。”",
                    "message": "你准备好了吗？",
                    "history": [{"role": "user", "content": "之前的问题"}],
                },
            )

        self.assertEqual(result["character_id"], character["id"])
        self.assertEqual(result["character_name"], "林夏")
        self.assertEqual(result["reply"], "我已经准备好了。")
        self.assertEqual(chat.call_args.kwargs["user_message"], "你准备好了吗？")


if __name__ == "__main__":
    unittest.main()
