from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .safety import SafetyError, validate_local_endpoint, validate_profile_name


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_home() -> Path:
    return Path(os.environ.get("YUMANI_HOME", "~/.yumani")).expanduser()


def registry_path(home: Path | None = None) -> Path:
    return (home or default_home()) / "profiles.json"


@dataclass
class Profile:
    name: str
    endpoint: str
    model: str
    adapter: str = "openai-compatible"
    enabled: bool = True
    state_dir_name: str = ".yumani"
    safe_input_tokens: int = 12_000
    hard_input_tokens: int = 24_000
    output_tokens: int = 2_048
    recovery_tool_name: str = "YUMANI_INTERCEPT"
    recovery_mode: str = "auto"
    allow_remote: bool = False
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self, *, force_local_profile_name: bool = False) -> "Profile":
        validate_profile_name(self.name, force_local_profile_name=force_local_profile_name)
        safety = validate_local_endpoint(self.endpoint, allow_remote=self.allow_remote)
        if not safety.allowed:
            raise SafetyError(safety.reason)
        self.endpoint = safety.normalized_url or self.endpoint
        if self.safe_input_tokens <= 0 or self.hard_input_tokens <= 0:
            raise SafetyError("TOKEN_BUDGETS_MUST_BE_POSITIVE")
        if self.safe_input_tokens > self.hard_input_tokens:
            raise SafetyError("SAFE_INPUT_TOKENS_EXCEEDS_HARD_INPUT_TOKENS")
        if self.output_tokens <= 0:
            raise SafetyError("OUTPUT_TOKENS_MUST_BE_POSITIVE")
        if self.state_dir_name in {".git", ".", ""} or "/" in self.state_dir_name:
            raise SafetyError("STATE_DIR_NAME_INVALID")
        return self


def ensure_home(home: Path | None = None) -> Path:
    root = home or default_home()
    root.mkdir(parents=True, exist_ok=True)
    (root / "calibration").mkdir(exist_ok=True)
    (root / "sessions").mkdir(exist_ok=True)
    return root


def empty_registry() -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "local_only": True,
        "profiles": {},
    }


def load_registry(home: Path | None = None) -> dict[str, Any]:
    root = ensure_home(home)
    path = registry_path(root)
    if not path.exists():
        return empty_registry()
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SafetyError("REGISTRY_SCHEMA_VERSION_UNSUPPORTED")
    data.setdefault("profiles", {})
    return data


def save_registry(registry: dict[str, Any], home: Path | None = None) -> Path:
    root = ensure_home(home)
    registry["updated_at"] = utc_now()
    path = registry_path(root)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(registry, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)
    return path


def list_profiles(home: Path | None = None) -> list[Profile]:
    registry = load_registry(home)
    profiles = []
    for data in registry.get("profiles", {}).values():
        profiles.append(Profile.from_dict(data))
    return sorted(profiles, key=lambda item: item.name)


def get_profile(name: str, home: Path | None = None) -> Profile:
    registry = load_registry(home)
    data = registry.get("profiles", {}).get(name)
    if not data:
        raise SafetyError("PROFILE_NOT_REGISTERED")
    profile = Profile.from_dict(data)
    return profile.validate(force_local_profile_name=True)


def register_profile(profile: Profile, home: Path | None = None, *, force_local_profile_name: bool = False) -> Path:
    profile.validate(force_local_profile_name=force_local_profile_name)
    registry = load_registry(home)
    existing = registry["profiles"].get(profile.name)
    if existing and not profile.created_at:
        profile.created_at = existing.get("created_at", utc_now())
    profile.updated_at = utc_now()
    registry["profiles"][profile.name] = profile.to_dict()
    return save_registry(registry, home)


def profile_summary(profile: Profile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "enabled": profile.enabled,
        "adapter": profile.adapter,
        "endpoint": profile.endpoint,
        "model": profile.model,
        "state_dir_name": profile.state_dir_name,
        "safe_input_tokens": profile.safe_input_tokens,
        "hard_input_tokens": profile.hard_input_tokens,
        "output_tokens": profile.output_tokens,
        "recovery_mode": profile.recovery_mode,
    }

