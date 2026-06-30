from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from yumani.config import Profile
from yumani.context import build_context_pack, pack_chat_messages
from yumani.state import StateStore


class ContextStateTests(unittest.TestCase):
    def test_state_dir_is_yumani_not_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = Profile(name="local-small", endpoint="http://127.0.0.1:11434/v1", model="tiny").validate()
            store = StateStore(root, profile)
            run = store.create_run("work", "hello", status="TEST")
            self.assertTrue((root / ".yumani" / "state.db").exists())
            self.assertTrue(run.artifact_dir.exists())
            self.assertFalse((root / ".legacy").exists())

    def test_context_pack_blocks_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root.parent / "outside-yumani-test.txt"
            outside.write_text("secret", encoding="utf-8")
            profile = Profile(name="local-small", endpoint="http://127.0.0.1:11434/v1", model="tiny").validate()
            with self.assertRaises(Exception):
                build_context_pack(profile=profile, project_root=root, request="read", mode="work", include=[str(outside)])
            outside.unlink(missing_ok=True)

    def test_proxy_pack_caps_tokens_and_drops_old_messages(self) -> None:
        profile = Profile(
            name="local-small",
            endpoint="http://127.0.0.1:11434/v1",
            model="tiny",
            safe_input_tokens=80,
            hard_input_tokens=120,
            output_tokens=16,
        ).validate()
        payload = {
            "model": "tiny",
            "messages": [{"role": "user", "content": "old " * 300}, {"role": "user", "content": "new task"}],
            "max_tokens": 1000,
        }
        packed, manifest = pack_chat_messages(payload, profile)
        self.assertLessEqual(packed["max_tokens"], 16)
        self.assertTrue(manifest["actions"])
        self.assertLess(manifest["packed_estimated_tokens"], manifest["original_estimated_tokens"])


if __name__ == "__main__":
    unittest.main()

