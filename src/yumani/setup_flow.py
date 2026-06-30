from __future__ import annotations

import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .config import Profile, ensure_home, register_profile
from .cui import choose, header, kv, paragraph, prompt, prompt_int, prompt_yes_no, section, status_line
from .provider import fetch_models
from .safety import SafetyError, validate_local_endpoint


@dataclass
class CandidateRuntime:
    name: str
    endpoint: str
    kind: str
    status: str = "unknown"
    model_ids: list[str] | None = None
    error: str | None = None

    def display(self) -> str:
        models = ", ".join((self.model_ids or [])[:3])
        if self.model_ids and len(self.model_ids) > 3:
            models += f", +{len(self.model_ids) - 3}"
        detail = f"{self.endpoint}"
        if models:
            detail += f"  models: {models}"
        return f"{self.name} ({self.kind}) - {detail}"


KNOWN_RUNTIMES = [
    CandidateRuntime("Ollama", "http://127.0.0.1:11434/v1", "ollama"),
    CandidateRuntime("LM Studio", "http://127.0.0.1:1234/v1", "lm-studio"),
    CandidateRuntime("llama.cpp / MLX", "http://127.0.0.1:8080/v1", "openai-compatible"),
    CandidateRuntime("vLLM", "http://127.0.0.1:8000/v1", "openai-compatible"),
    CandidateRuntime("oMLX Default", "http://127.0.0.1:18036/v1", "omlx"),
]


def model_ids_from_payload(payload: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for item in payload.get("data") or []:
        if isinstance(item, dict):
            model_id = item.get("id") or item.get("name")
            if model_id:
                ids.append(str(model_id))
    return ids


def scan_runtimes(timeout: float = 1.5) -> list[CandidateRuntime]:
    results: list[CandidateRuntime] = []
    for candidate in KNOWN_RUNTIMES:
        runtime = CandidateRuntime(candidate.name, candidate.endpoint, candidate.kind)
        safety = validate_local_endpoint(runtime.endpoint)
        if not safety.allowed:
            runtime.status = "blocked"
            runtime.error = safety.reason
            results.append(runtime)
            continue
        try:
            payload = fetch_models(runtime.endpoint, timeout=timeout)
            runtime.status = "ok"
            runtime.model_ids = model_ids_from_payload(payload)
        except Exception as exc:  # noqa: BLE001
            runtime.status = "miss"
            runtime.error = str(exc)
        results.append(runtime)
    return results


def slugify_profile_name(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip().lower()).strip("-._")
    slug = slug[:48] or "local-model"
    if not slug.startswith("local-") and not slug.endswith("-local"):
        slug = f"{slug}-local"
    return slug


def default_budgets(model: str) -> dict[str, int]:
    lowered = model.lower()
    if any(marker in lowered for marker in ("0.5b", "1b", "2b", "3b", "4b", "7b", "8b", "tiny", "small", "mini")):
        return {"safe_input_tokens": 6000, "hard_input_tokens": 12000, "output_tokens": 1024}
    return {"safe_input_tokens": 12000, "hard_input_tokens": 24000, "output_tokens": 2048}


def selected_runtime_from_args(args: Any) -> CandidateRuntime | None:
    if args.endpoint:
        return CandidateRuntime("Manual", args.endpoint, args.adapter, status="manual", model_ids=[args.model] if args.model else [])
    return None


def is_interactive(args: Any) -> bool:
    return not args.yes and not args.json and sys.stdin.isatty()


def choose_runtime(scanned: list[CandidateRuntime], args: Any) -> CandidateRuntime | None:
    ok = [item for item in scanned if item.status == "ok"]
    if not is_interactive(args):
        return ok[0] if ok else None

    section("2. Runtime")
    if ok:
        options = [item.display() for item in ok] + ["Enter endpoint manually"]
        choice = choose("Which local runtime should Yumani protect?", options)
        if choice < len(ok):
            return ok[choice]
    endpoint = prompt("http://127.0.0.1:11434/v1", "OpenAI-compatible local endpoint")
    return CandidateRuntime("Manual", endpoint, args.adapter, status="manual")


def choose_model(runtime: CandidateRuntime, args: Any) -> str:
    models = runtime.model_ids or []
    explicit_model = args.model or ""
    if is_interactive(args):
        section("3. Model")
        if models:
            default_index = models.index(explicit_model) if explicit_model in models else 0
            options = models + ["Enter model id manually"]
            choice = choose("Which model should Yumani route to?", options, default_index=default_index)
            if choice < len(models):
                return models[choice]
        return prompt(explicit_model, "Model id")
    model = explicit_model or (models[0] if models else "")
    if not model:
        raise SafetyError("SETUP_REQUIRES_MODEL")
    return model


def choose_budgets(model: str, args: Any) -> dict[str, int]:
    defaults = default_budgets(model)
    if not is_interactive(args):
        if args.safe_input_tokens:
            defaults["safe_input_tokens"] = args.safe_input_tokens
        if args.hard_input_tokens:
            defaults["hard_input_tokens"] = args.hard_input_tokens
        if args.output_tokens:
            defaults["output_tokens"] = args.output_tokens
        return defaults

    section("5. Context Budget")
    presets = [
        ("Small local model", {"safe_input_tokens": 6000, "hard_input_tokens": 12000, "output_tokens": 1024}),
        ("Balanced local model", {"safe_input_tokens": 12000, "hard_input_tokens": 24000, "output_tokens": 2048}),
        ("Large/reasoning local model", {"safe_input_tokens": 24000, "hard_input_tokens": 48000, "output_tokens": 4096}),
        ("Custom", {}),
    ]
    default_index = 0 if defaults["safe_input_tokens"] <= 6000 else 1
    options = [
        f"{name} ({budget.get('safe_input_tokens', 'custom')}/{budget.get('hard_input_tokens', 'custom')}/{budget.get('output_tokens', 'custom')})"
        for name, budget in presets
    ]
    choice = choose("Choose a starting budget preset", options, default_index=default_index)
    if presets[choice][0] != "Custom":
        return dict(presets[choice][1])
    return {
        "safe_input_tokens": prompt_int(args.safe_input_tokens or defaults["safe_input_tokens"], "Safe input tokens"),
        "hard_input_tokens": prompt_int(args.hard_input_tokens or defaults["hard_input_tokens"], "Hard input tokens"),
        "output_tokens": prompt_int(args.output_tokens or defaults["output_tokens"], "Output tokens"),
    }


def probe_provider(endpoint: str, timeout: float) -> tuple[str, str | None, list[str]]:
    try:
        payload = fetch_models(endpoint, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return "FAIL", str(exc), []
    return "OK", None, model_ids_from_payload(payload)


def run_setup(args: Any) -> dict[str, Any]:
    home = ensure_home(Path(args.home).expanduser() if args.home else None)
    if not args.json:
        header("Yumani Setup", "Answer a few questions. Cloud profiles will not be touched.")
        kv("home", home)
        kv("cloud profiles", "not touched")

    interactive = is_interactive(args)
    manual = selected_runtime_from_args(args)
    scanned: list[CandidateRuntime] = []
    runtime: CandidateRuntime | None = manual
    if not args.skip_scan and not manual:
        scan_now = True
        if interactive:
            section("1. Runtime Scan")
            paragraph("Yumani can scan common local OpenAI-compatible endpoints first.")
            scan_now = prompt_yes_no(True, "Scan local runtimes now")
        if scan_now and not args.json and not interactive:
            section("1. Local Runtime Scan")
        if scan_now:
            scanned = scan_runtimes(timeout=args.scan_timeout)
            for item in scanned:
                if not args.json:
                    detail = item.endpoint
                    if item.model_ids:
                        detail += "  " + ", ".join(item.model_ids[:3])
                    status_line(item.name, item.status, detail)
            runtime = choose_runtime(scanned, args)

    if runtime is None:
        if args.yes:
            raise SafetyError("SETUP_REQUIRES_ENDPOINT_WHEN_NO_RUNTIME_DETECTED")
        if not interactive:
            raise SafetyError("SETUP_REQUIRES_TTY_OR_EXPLICIT_ENDPOINT")
        section("2. Runtime")
        endpoint = prompt("http://127.0.0.1:11434/v1", "OpenAI-compatible local endpoint")
        runtime = CandidateRuntime("Manual", endpoint, args.adapter, status="manual")

    safety = validate_local_endpoint(runtime.endpoint)
    if not safety.allowed:
        raise SafetyError(safety.reason)
    endpoint = safety.normalized_url or runtime.endpoint

    model = choose_model(runtime, args)

    profile_name = args.profile or slugify_profile_name(model)
    if interactive:
        section("4. Profile")
        profile_name = prompt(profile_name, "Local profile name")
    budgets = choose_budgets(model, args)

    profile = Profile(
        name=profile_name,
        endpoint=endpoint,
        model=model,
        adapter=args.adapter,
        state_dir_name=".yumani",
        safe_input_tokens=budgets["safe_input_tokens"],
        hard_input_tokens=budgets["hard_input_tokens"],
        output_tokens=budgets["output_tokens"],
        metadata={"setup": "cui", "runtime": runtime.kind},
    )
    profile.validate(force_local_profile_name=args.force_local_profile_name)

    should_write = not args.dry_run
    if should_write:
        registry = register_profile(profile, home, force_local_profile_name=args.force_local_profile_name)
    else:
        registry = home / "profiles.json"

    proxy_port = args.proxy_port
    start_proxy = bool(args.start_proxy)
    provider_probe_status = "SKIPPED"
    provider_probe_error = None
    provider_probe_models: list[str] = []
    if interactive:
        section("6. Verification & Proxy")
        if prompt_yes_no(True, "Probe provider now"):
            provider_probe_status, provider_probe_error, provider_probe_models = probe_provider(endpoint, args.scan_timeout)
            status_line("Provider probe", provider_probe_status, provider_probe_error or ", ".join(provider_probe_models[:3]))
        proxy_port = prompt_int(proxy_port, "Proxy port")
        start_proxy = prompt_yes_no(False, "Start proxy now")

    payload = {
        "command": "setup",
        "status": "DRY_RUN" if args.dry_run else "OK",
        "home": str(home),
        "registry": str(registry),
        "profile": profile.name,
        "endpoint": profile.endpoint,
        "model": profile.model,
        "adapter": profile.adapter,
        "budgets": {
            "safe_input_tokens": profile.safe_input_tokens,
            "hard_input_tokens": profile.hard_input_tokens,
            "output_tokens": profile.output_tokens,
        },
        "proxy_url": f"http://127.0.0.1:{proxy_port}/v1",
        "scanned": [asdict(item) for item in scanned],
        "provider_probe": {
            "status": provider_probe_status,
            "error": provider_probe_error,
            "models": provider_probe_models,
        },
        "cloud_profiles_affected": False,
        "next": f"Run `yumani serve --profile {profile.name} --port {proxy_port}`.",
        "start_proxy": start_proxy,
    }

    if not args.json:
        section("Result")
        kv("status", payload["status"])
        kv("profile", profile.name)
        kv("upstream", profile.endpoint)
        kv("proxy", payload["proxy_url"])
        kv("provider probe", provider_probe_status)
        kv("registry", registry)
        kv("next", payload["next"])

    return payload
