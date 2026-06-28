from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, home: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "yumani", *args, "--home", str(home), "--json"],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_setup_noninteractive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home = base / "home"
            project = base / "project"
            project.mkdir()

            setup = run_cli(
                "setup",
                "--yes",
                "--skip-scan",
                "--profile",
                "local-small",
                "--endpoint",
                "http://127.0.0.1:11434/v1",
                "--model",
                "tiny",
                home=home,
                cwd=project,
            )
            self.assertEqual(setup.returncode, 0, setup.stderr)
            payload = json.loads(setup.stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertFalse(payload["cloud_profiles_affected"])
            self.assertTrue((home / "profiles.json").exists())

    def test_setup_blocks_cloud_profile_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home = base / "home"
            project = base / "project"
            project.mkdir()
            setup = run_cli(
                "setup",
                "--yes",
                "--skip-scan",
                "--profile",
                "gpt55",
                "--endpoint",
                "http://127.0.0.1:11434/v1",
                "--model",
                "tiny",
                home=home,
                cwd=project,
            )
            self.assertEqual(setup.returncode, 10)
            payload = json.loads(setup.stdout)
            self.assertEqual(payload["status"], "BLOCKED")

    def test_cli_profile_and_context_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home = base / "home"
            project = base / "project"
            project.mkdir()
            (project / "main.py").write_text("print('hello')\n", encoding="utf-8")

            init = run_cli("init", home=home, cwd=project)
            self.assertEqual(init.returncode, 0, init.stderr)

            add = run_cli(
                "profile",
                "add",
                "--name",
                "local-small",
                "--endpoint",
                "http://127.0.0.1:11434/v1",
                "--model",
                "tiny",
                home=home,
                cwd=project,
            )
            self.assertEqual(add.returncode, 0, add.stderr)

            pack = run_cli(
                "context-pack",
                "--profile",
                "local-small",
                "--project",
                str(project),
                "--include",
                "main.py",
                "review this",
                home=home,
                cwd=project,
            )
            self.assertEqual(pack.returncode, 0, pack.stderr)
            payload = json.loads(pack.stdout)
            self.assertEqual(payload["status"], "CONTEXT_PACKED")
            self.assertTrue((project / ".yumani" / "state.db").exists())


if __name__ == "__main__":
    unittest.main()
