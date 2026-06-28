from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from yumani.config import Profile, get_profile, register_profile
from yumani.safety import SafetyError, validate_local_endpoint


class ConfigTests(unittest.TestCase):
    def test_register_local_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            profile = Profile(name="m3-small", endpoint="http://localhost:11434/v1", model="qwen3:4b")
            register_profile(profile, home)
            loaded = get_profile("m3-small", home)
            self.assertEqual(loaded.endpoint, "http://127.0.0.1:11434/v1")
            self.assertEqual(loaded.state_dir_name, ".yumani")

    def test_cloud_profile_name_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            profile = Profile(name="gpt55", endpoint="http://127.0.0.1:18036/v1", model="local")
            with self.assertRaises(SafetyError):
                register_profile(profile, home)

    def test_cloud_endpoint_is_blocked(self) -> None:
        safety = validate_local_endpoint("https://api.openai.com/v1")
        self.assertFalse(safety.allowed)


if __name__ == "__main__":
    unittest.main()

