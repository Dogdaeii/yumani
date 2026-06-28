from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


CLOUD_PROFILE_DENYLIST = {
    "default",
    "hay",
    "gpt55",
    "gpt44",
    "codexspark",
    "gpt",
    "claude",
    "gemini",
    "openai",
    "anthropic",
    "codex",
}

CLOUD_PROFILE_PATTERNS = (
    re.compile(r"^gpt[-_0-9a-z]*$"),
    re.compile(r"^claude[-_0-9a-z]*$"),
    re.compile(r"^gemini[-_0-9a-z]*$"),
    re.compile(r"^codex[-_0-9a-z]*$"),
)

CLOUD_HOST_HINTS = (
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "openrouter.ai",
    "groq.com",
    "together.ai",
    "fireworks.ai",
)

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


class SafetyError(ValueError):
    """Raised when a profile or endpoint violates local-only isolation."""


@dataclass(frozen=True)
class EndpointSafety:
    allowed: bool
    reason: str
    normalized_url: str | None = None


def is_cloud_profile_name(name: str) -> bool:
    normalized = name.strip().lower()
    if normalized in CLOUD_PROFILE_DENYLIST:
        return True
    return any(pattern.match(normalized) for pattern in CLOUD_PROFILE_PATTERNS)


def validate_profile_name(name: str, *, force_local_profile_name: bool = False) -> None:
    if not name or not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$", name):
        raise SafetyError("PROFILE_NAME_INVALID")
    if is_cloud_profile_name(name) and not force_local_profile_name:
        raise SafetyError("PROFILE_NAME_RESERVED_FOR_CLOUD_OR_SHARED_PROFILE")


def validate_local_endpoint(endpoint: str, *, allow_remote: bool = False) -> EndpointSafety:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http"}:
        return EndpointSafety(False, "ENDPOINT_SCHEME_MUST_BE_LOCAL_HTTP")
    if not parsed.hostname:
        return EndpointSafety(False, "ENDPOINT_HOST_MISSING")
    host = parsed.hostname.lower()
    if any(hint in host for hint in CLOUD_HOST_HINTS):
        return EndpointSafety(False, "ENDPOINT_LOOKS_LIKE_CLOUD_PROVIDER")
    if not allow_remote and host not in LOOPBACK_HOSTS:
        return EndpointSafety(False, "ENDPOINT_NOT_LOOPBACK")
    if parsed.port is None:
        return EndpointSafety(False, "ENDPOINT_PORT_REQUIRED")
    if parsed.port < 1 or parsed.port > 65535:
        return EndpointSafety(False, "ENDPOINT_PORT_INVALID")
    path = parsed.path.rstrip("/") or "/v1"
    if not path.endswith("/v1"):
        path = f"{path.rstrip('/')}/v1"
    if host == "::1":
        host_part = "[::1]"
    else:
        host_part = "127.0.0.1" if host == "localhost" else host
    return EndpointSafety(True, "OK", f"http://{host_part}:{parsed.port}{path}")


def redact_secret(value: str) -> str:
    redacted = value
    redacted = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-***", redacted)
    redacted = re.sub(r"(?i)(api[_-]?key|token|secret)=([^\\s]+)", r"\1=***", redacted)
    return redacted

