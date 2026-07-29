import os
import re
import stat
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "Start-VoxCast.command"


class MacQuickStartTests(unittest.TestCase):
    def test_launcher_is_executable_and_has_valid_bash_syntax(self) -> None:
        self.assertTrue(LAUNCHER.is_file())
        self.assertTrue(LAUNCHER.stat().st_mode & stat.S_IXUSR)
        result = subprocess.run(
            ["bash", "-n", str(LAUNCHER)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dry_run_uses_current_python_without_creating_environment(
        self,
    ) -> None:
        environment_path = ROOT / ".voxcast-venv"
        existed_before = environment_path.exists()
        environment = os.environ.copy()
        environment.update(
            {
                "VOXCAST_QUICKSTART_DRY_RUN": "1",
                "VOXCAST_QUICKSTART_PYTHON": sys.executable,
                "VOXCAST_PORT": "8123",
            }
        )
        result = subprocess.run(
            ["bash", str(LAUNCHER)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VOXCAST_QUICKSTART_OK=1", result.stdout)
        self.assertIn("http://127.0.0.1:8123", result.stdout)
        self.assertEqual(environment_path.exists(), existed_before)

    def test_launcher_keeps_install_local_and_has_offline_fallback(self) -> None:
        launcher = LAUNCHER.read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"(?m)^[ \t]*sudo(?:[ \t]|$)", launcher),
        )
        self.assertIn('.voxcast-venv', launcher)
        self.assertIn('-e ".[neural]"', launcher)
        self.assertIn("仍将启动基础版", launcher)
        self.assertIn("/api/health", launcher)
        self.assertIn("open_app", launcher)


if __name__ == "__main__":
    unittest.main()
