import os
import re
import stat
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LINUX_LAUNCHER = ROOT / "Start-VoxCast.sh"
WINDOWS_LAUNCHER = ROOT / "Start-VoxCast.ps1"


class CrossPlatformQuickStartTests(unittest.TestCase):
    def test_linux_launcher_is_executable_and_dry_runs(self) -> None:
        self.assertTrue(LINUX_LAUNCHER.stat().st_mode & stat.S_IXUSR)
        syntax = subprocess.run(
            ["bash", "-n", str(LINUX_LAUNCHER)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        environment = os.environ.copy()
        environment.update(
            {
                "VOXCAST_QUICKSTART_DRY_RUN": "1",
                "VOXCAST_QUICKSTART_PYTHON": sys.executable,
                "VOXCAST_PORT": "8124",
            }
        )
        result = subprocess.run(
            ["bash", str(LINUX_LAUNCHER)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VOXCAST_QUICKSTART_OK=1", result.stdout)
        self.assertIn("http://127.0.0.1:8124", result.stdout)

    def test_windows_launcher_has_safe_local_install_contract(self) -> None:
        launcher = WINDOWS_LAUNCHER.read_text(encoding="utf-8")

        self.assertNotRegex(launcher, r"(?im)^\s*(?:Start-Process\s+PowerShell.*-Verb\s+RunAs|sudo)\b")
        self.assertIn(".voxcast-venv", launcher)
        self.assertIn('.[neural]', launcher)
        self.assertIn("Add Python to PATH", launcher)
        self.assertIn("/api/health", launcher)
        self.assertIn("python.exe", launcher)
        self.assertIn("-m audiobook_app serve --port", launcher)
        self.assertIn("VOXCAST_QUICKSTART_DRY_RUN", launcher)


if __name__ == "__main__":
    unittest.main()
