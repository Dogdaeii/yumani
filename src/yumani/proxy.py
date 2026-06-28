from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import Profile, ensure_home
from .context import pack_chat_messages
from .provider import join_url


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def turn_manifest_path(home: Path, profile: Profile) -> Path:
    stamp = f"turn_{int(time.time() * 1000)}_{threading.get_ident()}.manifest.json"
    return home / "sessions" / profile.name / "turns" / stamp


def make_handler(profile: Profile, home: Path):
    class YumaniProxyHandler(BaseHTTPRequestHandler):
        server_version = "YumaniProxy/0.1"

        def log_message(self, fmt: str, *args: object) -> None:
            return

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "proxy": "yumani",
                        "profile": profile.name,
                        "endpoint": profile.endpoint,
                        "local_only": True,
                    },
                )
                return
            if self.path.rstrip("/") == "/v1/models":
                self._forward_get(join_url(profile.endpoint, "models"))
                return
            self._send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path.rstrip("/") != "/v1/chat/completions":
                self._send_json(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                self._send_json(400, {"error": f"invalid_json: {exc}"})
                return

            packed, manifest = pack_chat_messages(payload, profile)
            manifest.update(
                {
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "stream": bool(packed.get("stream")),
                    "endpoint": profile.endpoint,
                }
            )
            manifest_path = turn_manifest_path(home, profile)
            write_json(manifest_path, manifest)

            upstream_url = join_url(profile.endpoint, "chat/completions")
            if packed.get("stream"):
                self._forward_stream(upstream_url, packed)
            else:
                self._forward_json(upstream_url, packed)

        def _forward_get(self, url: str) -> None:
            try:
                req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    body = resp.read()
                    status = resp.status
                    headers = resp.headers
            except urllib.error.HTTPError as exc:
                body = exc.read()
                status = exc.code
                headers = exc.headers
            except Exception as exc:  # noqa: BLE001
                self._send_json(502, {"error": str(exc)})
                return
            self.send_response(status)
            self.send_header("Content-Type", headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _forward_json(self, url: str, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=300.0) as resp:
                    response_body = resp.read()
                    status = resp.status
                    content_type = resp.headers.get("Content-Type", "application/json")
            except urllib.error.HTTPError as exc:
                response_body = exc.read()
                status = exc.code
                content_type = exc.headers.get("Content-Type", "application/json")
            except Exception as exc:  # noqa: BLE001
                self._send_json(502, {"error": str(exc)})
                return
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def _forward_stream(self, url: str, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            )
            try:
                resp = urllib.request.urlopen(req, timeout=300.0)
            except Exception as exc:  # noqa: BLE001
                self._send_json(502, {"error": str(exc)})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                for line in resp:
                    if not line:
                        continue
                    if line.startswith(b"data:"):
                        event = line.rstrip(b"\r\n") + b"\n\n"
                    elif line.strip() == b"":
                        continue
                    else:
                        event = line.rstrip(b"\r\n") + b"\n\n"
                    size = f"{len(event):x}".encode("ascii")
                    self.wfile.write(size + b"\r\n" + event + b"\r\n")
                    self.wfile.flush()
            finally:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
                resp.close()

    return YumaniProxyHandler


def serve(profile: Profile, *, home: Path | None, host: str, port: int) -> None:
    root = ensure_home(home)
    handler = make_handler(profile, root)
    server = ThreadingHTTPServer((host, port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()

