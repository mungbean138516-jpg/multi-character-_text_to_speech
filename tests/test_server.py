import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import audiobook_app.server as app_server


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
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
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

    def test_private_cache_path_is_not_served(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(
                self.base_url + "/outputs/_cache/not-public.wav"
            )
        self.assertEqual(context.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
