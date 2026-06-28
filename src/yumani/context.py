from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Profile
from .safety import SafetyError, redact_secret


FILE_CHAR_LIMIT = 8_000


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    wordish = max(1, int(len(text.split()) * 1.35))
    charish = max(1, int(len(text) / 4))
    return max(wordish, charish)


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ContextPack:
    text: str
    accounting: dict[str, Any]
    context_pack_hash: str


def resolve_include(root: Path, value: str) -> Path:
    target = (root / value).expanduser().resolve() if not Path(value).is_absolute() else Path(value).expanduser().resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise SafetyError("INCLUDE_PATH_ESCAPES_PROJECT_ROOT") from exc
    if not target.exists():
        raise FileNotFoundError(str(target))
    if not target.is_file():
        raise IsADirectoryError(str(target))
    return target


def read_excerpt(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    truncated = len(raw) > FILE_CHAR_LIMIT
    text = raw[:FILE_CHAR_LIMIT].decode("utf-8", errors="replace")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "truncated": truncated,
        "text": redact_secret(text),
    }


def build_context_pack(
    *,
    profile: Profile,
    project_root: Path,
    request: str,
    mode: str,
    include: list[str] | None = None,
) -> ContextPack:
    include = include or []
    hard_sections = [
        (
            "Yumani Operating Contract",
            "\n".join(
                [
                    "You are running behind Yumani, a local-only LLM harness.",
                    "Treat wrapper-observed facts as authoritative.",
                    "Separate model claims from verified observations.",
                    "Avoid repeating failed actions; choose the next concrete tool or answer.",
                    f"Profile: {profile.name}",
                    f"Model: {profile.model}",
                    f"Mode: {mode}",
                ]
            ),
        ),
        ("User Request", request.strip() or "(empty request)"),
    ]
    elastic_sections: list[tuple[str, str]] = []
    include_records = []
    for item in include:
        path = resolve_include(project_root, item)
        record = read_excerpt(path)
        include_records.append({k: v for k, v in record.items() if k != "text"})
        rel = path.relative_to(project_root)
        elastic_sections.append((f"Included File: {rel}", record["text"]))

    budget = {
        "safe_input_tokens": profile.safe_input_tokens,
        "hard_input_tokens": profile.hard_input_tokens,
        "output_tokens": profile.output_tokens,
        "target_tokens": min(profile.safe_input_tokens, profile.hard_input_tokens - profile.output_tokens),
    }
    lines = ["# Yumani Context Pack", ""]
    mandatory_tokens = 0
    for title, body in hard_sections:
        section = f"## {title}\n\n{body.strip()}\n"
        mandatory_tokens += estimate_tokens(section)
        lines.append(section)

    included = []
    dropped = []
    current_tokens = estimate_tokens("\n".join(lines))
    target = max(512, budget["target_tokens"])
    for title, body in elastic_sections:
        section = f"## {title}\n\n```text\n{body.strip()}\n```\n"
        section_tokens = estimate_tokens(section)
        if current_tokens + section_tokens <= target:
            lines.append(section)
            included.append(title)
            current_tokens += section_tokens
        else:
            dropped.append(title)

    accounting = {
        "status": "CONTEXT_PACKED" if mandatory_tokens <= target else "BUDGET_PACK_FAILURE",
        "failure_class": "NONE" if mandatory_tokens <= target else "BUDGET_PACK_FAILURE",
        "estimated_tokens": current_tokens,
        "mandatory_tokens": mandatory_tokens,
        "budget": budget,
        "included_sections": included,
        "dropped_sections": dropped,
        "include_records": include_records,
    }
    if dropped:
        lines.append("## Dropped Elastic Sections")
        lines.extend(f"- {name}" for name in dropped)
        lines.append("")
    lines.append("## Accounting")
    lines.append("```json")
    lines.append(json.dumps(accounting, ensure_ascii=False, indent=2, sort_keys=True))
    lines.append("```")
    text = "\n".join(lines).strip() + "\n"
    return ContextPack(text=text, accounting=accounting, context_pack_hash=hash_text(text))


def pack_chat_messages(payload: dict[str, Any], profile: Profile) -> tuple[dict[str, Any], dict[str, Any]]:
    messages = list(payload.get("messages") or [])
    original_tokens = estimate_tokens(json.dumps(messages, ensure_ascii=False))
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "profile": profile.name,
        "model": payload.get("model") or profile.model,
        "original_estimated_tokens": original_tokens,
        "safe_input_tokens": profile.safe_input_tokens,
        "actions": [],
    }
    if original_tokens <= profile.safe_input_tokens:
        manifest["packed_estimated_tokens"] = original_tokens
        return payload, manifest

    hard = [m for m in messages if m.get("role") in {"system", "developer"}]
    tail: list[dict[str, Any]] = []
    tail_tokens = estimate_tokens(json.dumps(hard, ensure_ascii=False))
    dropped_count = 0
    for message in reversed(messages):
        if message.get("role") in {"system", "developer"}:
            continue
        candidate_tokens = estimate_tokens(json.dumps(message, ensure_ascii=False))
        if not tail or tail_tokens + candidate_tokens <= profile.safe_input_tokens:
            tail.insert(0, message)
            tail_tokens += candidate_tokens
        else:
            dropped_count += 1

    notice = {
        "role": "system",
        "content": (
            f"[Yumani] {dropped_count} older messages were compacted to protect local memory. "
            "Do not assume missing details are still verified; inspect files or state again when needed."
        ),
    }
    packed_messages = hard + ([notice] if dropped_count else []) + tail
    new_payload = dict(payload)
    new_payload["messages"] = packed_messages
    new_payload["model"] = payload.get("model") or profile.model
    requested_max = int(payload.get("max_tokens") or payload.get("max_completion_tokens") or profile.output_tokens)
    capped_max = min(requested_max, profile.output_tokens)
    new_payload["max_tokens"] = capped_max
    new_payload.pop("max_completion_tokens", None)
    manifest["actions"].append(
        {
            "type": "drop_old_messages",
            "dropped_messages": dropped_count,
            "requested_max_tokens": requested_max,
            "capped_max_tokens": capped_max,
        }
    )
    manifest["packed_estimated_tokens"] = estimate_tokens(json.dumps(packed_messages, ensure_ascii=False))
    return new_payload, manifest

