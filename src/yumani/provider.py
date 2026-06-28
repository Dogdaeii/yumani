from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .context import estimate_tokens


@dataclass
class ProviderResult:
    status: str
    failure_class: str
    content: str = ""
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "failure_class": self.failure_class,
            "content": self.content,
            "finish_reason": self.finish_reason,
            "usage": self.usage or {},
            "raw": self.raw or {},
            "error": self.error,
        }


def join_url(endpoint: str, path: str) -> str:
    return f"{endpoint.rstrip('/')}/{path.lstrip('/')}"


def post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def get_json(url: str, *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def fetch_models(endpoint: str, *, timeout: float = 5.0) -> dict[str, Any]:
    return get_json(join_url(endpoint, "models"), timeout=timeout)


def provider_fingerprint(endpoint: str, model: str, models_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = models_payload or {}
    source = {
        "endpoint": endpoint,
        "model": model,
        "models": payload,
    }
    encoded = json.dumps(source, ensure_ascii=True, sort_keys=True)
    return {
        "endpoint": endpoint,
        "model": model,
        "models_hash": hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest(),
        "fingerprint_hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def chat_completion(
    *,
    endpoint: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    timeout: float,
) -> ProviderResult:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        data = post_json(join_url(endpoint, "chat/completions"), payload, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if "memory" in body.lower() or "oom" in body.lower() or "prefill" in body.lower():
            failure = "PROVIDER_MEMORY_LIMIT"
        else:
            failure = "PROVIDER_HTTP_ERROR"
        return ProviderResult("FAIL", failure, error=f"HTTP {exc.code}: {body[:500]}")
    except TimeoutError as exc:
        return ProviderResult("FAIL", "TIMEOUT", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return ProviderResult("FAIL", "PROVIDER_UNAVAILABLE", error=str(exc))

    choices = data.get("choices") or []
    first = choices[0] if choices else {}
    message = first.get("message") or {}
    content = message.get("content") or ""
    return ProviderResult(
        status="PASS",
        failure_class="NONE",
        content=content,
        finish_reason=first.get("finish_reason"),
        usage=data.get("usage") or {},
        raw=data,
    )


def synthetic_user_message(target_tokens: int) -> str:
    unit = "calibration-token "
    estimated_unit = max(1, estimate_tokens(unit))
    count = max(1, int(target_tokens / estimated_unit))
    return unit * count

