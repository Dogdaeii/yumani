from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from yumani.config import Profile
from yumani.proxy import make_handler


class FakeUpstream(BaseHTTPRequestHandler):
    last_payload = None

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps({"data": [{"id": "fake-local"}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        FakeUpstream.last_payload = json.loads(self.rfile.read(length).decode("utf-8"))
        body = json.dumps(
            {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ProxyTests(unittest.TestCase):
    def test_proxy_caps_max_tokens_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstream)
            upstream_port = upstream.server_address[1]
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            profile = Profile(
                name="proxy-local",
                endpoint=f"http://127.0.0.1:{upstream_port}/v1",
                model="fake-local",
                safe_input_tokens=80,
                hard_input_tokens=160,
                output_tokens=7,
            ).validate()
            proxy = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(profile, home))
            proxy_port = proxy.server_address[1]
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()
            try:
                payload = {
                    "model": "fake-local",
                    "messages": [{"role": "user", "content": "old " * 300}, {"role": "user", "content": "next"}],
                    "max_tokens": 999,
                    "stream": False,
                }
                body = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"http://127.0.0.1:{proxy_port}/v1/chat/completions",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(result["choices"][0]["message"]["content"], "ok")
                self.assertEqual(FakeUpstream.last_payload["max_tokens"], 7)
                manifests = list((home / "sessions" / "proxy-local" / "turns").glob("*.manifest.json"))
                self.assertEqual(len(manifests), 1)
                manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
                self.assertTrue(manifest["actions"])
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()


if __name__ == "__main__":
    unittest.main()
