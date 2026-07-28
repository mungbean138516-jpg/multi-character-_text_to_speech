import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from audiobook_app.jobs import RenderJobManager
from audiobook_app.models import (
    AnalysisResult,
    CharacterProfile,
    ScriptSegment,
)
from audiobook_app.providers.demo import DemoToneProvider


class GateProvider(DemoToneProvider):
    def __init__(self) -> None:
        self.calls = 0
        self.second_started = threading.Event()
        self.release_second = threading.Event()

    def synthesize(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 2:
            self.second_started.set()
            if not self.release_second.wait(timeout=2):
                raise RuntimeError("test gate timed out")
        return super().synthesize(*args, **kwargs)


class RenderJobManagerTests(unittest.TestCase):
    def test_progressive_playback_pause_and_resume(self) -> None:
        analysis = AnalysisResult(
            characters=[
                CharacterProfile(
                    id="narrator",
                    name="旁白",
                    voice_id="narrator_f",
                )
            ],
            segments=[
                ScriptSegment(
                    id=f"seg_{index:03d}",
                    kind="narration",
                    text=f"第 {index} 句话。",
                    speaker_id="narrator",
                )
                for index in range(1, 4)
            ],
        )
        provider = GateProvider()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = RenderJobManager(
                root / "outputs",
                root / "cache",
                max_workers=1,
            )
            try:
                created = manager.create_job(
                    analysis,
                    provider,
                    provider_name="demo",
                    chapter_id="chapter_1",
                    chapter_title="第一章",
                )
                self.assertTrue(provider.second_started.wait(timeout=2))
                running = manager.get_job(created["job_id"])
                self.assertEqual(running["completed_segments"], 1)
                self.assertEqual(len(running["playable_segments"]), 1)
                first_url = running["playable_segments"][0]["audio_url"]
                self.assertTrue(first_url.endswith("001_seg_001.wav"))

                pausing = manager.pause_job(created["job_id"])
                self.assertEqual(pausing["status"], "pausing")
                provider.release_second.set()
                paused = self._wait_for_status(
                    manager,
                    created["job_id"],
                    {"paused"},
                )
                self.assertEqual(paused["completed_segments"], 2)
                self.assertEqual(len(paused["playable_segments"]), 2)

                resumed = manager.resume_job(created["job_id"])
                self.assertEqual(resumed["status"], "queued")
                completed = self._wait_for_status(
                    manager,
                    created["job_id"],
                    {"completed"},
                )
                self.assertEqual(completed["progress_percent"], 100)
                self.assertEqual(completed["completed_segments"], 3)
                self.assertEqual(len(completed["playable_segments"]), 3)
                self.assertTrue(completed["audio_url"].endswith("audiobook.wav"))
                self.assertEqual(provider.calls, 3)

                private_snapshot = (
                    root
                    / "outputs"
                    / "_jobs"
                    / f"{created['job_id']}.json"
                )
                payload = json.loads(
                    private_snapshot.read_text(encoding="utf-8")
                )
                self.assertNotIn("analysis", payload)
                self.assertEqual(payload["chapter_title"], "第一章")
            finally:
                provider.release_second.set()
                manager.shutdown(wait=True)

    @staticmethod
    def _wait_for_status(
        manager: RenderJobManager,
        job_id: str,
        statuses: set[str],
    ) -> dict:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            snapshot = manager.get_job(job_id)
            if snapshot["status"] in statuses:
                return snapshot
            time.sleep(0.01)
        raise AssertionError(f"job did not reach {sorted(statuses)}")


if __name__ == "__main__":
    unittest.main()
