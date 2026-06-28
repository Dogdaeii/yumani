from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Profile, ensure_home, utc_now
from .provider import chat_completion, fetch_models, provider_fingerprint, synthetic_user_message


def calibration_path(home: Path, fingerprint_hash: str) -> Path:
    return home / "calibration" / f"{fingerprint_hash}.json"


def load_calibration(home: Path, fingerprint_hash: str) -> dict[str, Any] | None:
    path = calibration_path(home, fingerprint_hash)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_calibration(home: Path, result: dict[str, Any]) -> Path:
    path = calibration_path(home, result["fingerprint"]["fingerprint_hash"])
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)
    return path


def calibrate(
    profile: Profile,
    *,
    home: Path | None = None,
    min_tokens: int = 1_024,
    max_tokens: int = 16_000,
    timeout: float = 60.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = ensure_home(home)
    attempts: list[dict[str, Any]] = []
    try:
        models = fetch_models(profile.endpoint, timeout=min(timeout, 10.0))
    except Exception as exc:  # noqa: BLE001
        models = {"error": str(exc)}
        fingerprint = provider_fingerprint(profile.endpoint, profile.model, models)
        return {
            "schema_version": 1,
            "status": "FAIL",
            "failure_class": "PROVIDER_UNAVAILABLE",
            "profile": profile.name,
            "fingerprint": fingerprint,
            "attempts": attempts,
            "error": str(exc),
            "created_at": utc_now(),
        }

    fingerprint = provider_fingerprint(profile.endpoint, profile.model, models)
    if dry_run:
        result = {
            "schema_version": 1,
            "status": "DRY_RUN",
            "failure_class": "NONE",
            "profile": profile.name,
            "fingerprint": fingerprint,
            "min_tokens": min_tokens,
            "max_tokens": max_tokens,
            "attempts": [],
            "created_at": utc_now(),
        }
        save_calibration(root, result)
        return result

    low = 0
    high = max(min_tokens, max_tokens)
    cursor = min_tokens
    while cursor <= max_tokens:
        message = synthetic_user_message(cursor)
        result = chat_completion(
            endpoint=profile.endpoint,
            model=profile.model,
            messages=[{"role": "user", "content": message}],
            max_tokens=1,
            timeout=timeout,
        )
        attempts.append({"tokens": cursor, "status": result.status, "failure_class": result.failure_class})
        if result.status == "PASS":
            low = cursor
            cursor *= 2
        else:
            high = cursor
            break
    if low == 0:
        high = min_tokens
    while high - low > 512:
        mid = (low + high) // 2
        message = synthetic_user_message(mid)
        result = chat_completion(
            endpoint=profile.endpoint,
            model=profile.model,
            messages=[{"role": "user", "content": message}],
            max_tokens=1,
            timeout=timeout,
        )
        attempts.append({"tokens": mid, "status": result.status, "failure_class": result.failure_class})
        if result.status == "PASS":
            low = mid
        else:
            high = mid

    max_safe = max(0, low)
    result_payload = {
        "schema_version": 1,
        "status": "PASS" if max_safe else "FAIL",
        "failure_class": "NONE" if max_safe else "CALIBRATION_FAILED",
        "profile": profile.name,
        "fingerprint": fingerprint,
        "max_safe_input_tokens": max_safe,
        "recommended_budgets": {
            "chat": {"safe_input_tokens": max(512, int(max_safe * 0.4)), "output_tokens": min(1024, profile.output_tokens)},
            "work": {"safe_input_tokens": max(1024, int(max_safe * 0.5)), "output_tokens": min(2048, profile.output_tokens)},
            "deep": {"safe_input_tokens": max(2048, int(max_safe * 0.65)), "output_tokens": profile.output_tokens},
            "recovery": {"safe_input_tokens": max(512, int(max_safe * 0.3)), "output_tokens": min(2048, profile.output_tokens)},
        },
        "attempts": attempts,
        "created_at": utc_now(),
    }
    save_calibration(root, result_payload)
    return result_payload

