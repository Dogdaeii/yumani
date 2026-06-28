from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .calibration import calibrate
from .config import (
    Profile,
    default_home,
    ensure_home,
    get_profile,
    list_profiles,
    profile_summary,
    register_profile,
    registry_path,
)
from .context import build_context_pack
from .provider import chat_completion, fetch_models, provider_fingerprint
from .proxy import serve
from .safety import SafetyError, validate_local_endpoint
from .setup_flow import run_setup
from .state import StateStore, project_root


def emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    status = payload.get("status", "OK")
    command = payload.get("command", "yumani")
    print(f"[yumani:{command}] status={status}")
    for key in ("home", "profile", "model", "endpoint", "project", "run_id", "state_dir", "path", "reason", "next"):
        if key in payload and payload[key] not in (None, ""):
            print(f"{key}: {payload[key]}")


def home_from_args(args: argparse.Namespace) -> Path:
    return Path(args.home).expanduser() if getattr(args, "home", None) else default_home()


def cmd_version(args: argparse.Namespace) -> int:
    emit({"command": "version", "status": "OK", "version": __version__}, as_json=args.json)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    home = ensure_home(home_from_args(args))
    payload = {
        "command": "init",
        "status": "OK",
        "home": str(home),
        "registry": str(registry_path(home)),
        "local_only": True,
    }
    emit(payload, as_json=args.json)
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    payload = run_setup(args)
    if args.json:
        emit(payload, as_json=True)
    if payload.get("start_proxy"):
        profile = get_profile(payload["profile"], home_from_args(args))
        print()
        print(f"[yumani:serve] profile={profile.name} listening={payload['proxy_url']} upstream={profile.endpoint}")
        serve(profile, home=home_from_args(args), host="127.0.0.1", port=args.proxy_port)
    return 0


def cmd_profile_add(args: argparse.Namespace) -> int:
    home = home_from_args(args)
    profile = Profile(
        name=args.name,
        endpoint=args.endpoint,
        model=args.model,
        adapter=args.adapter,
        state_dir_name=args.state_dir_name,
        safe_input_tokens=args.safe_input_tokens,
        hard_input_tokens=args.hard_input_tokens,
        output_tokens=args.output_tokens,
        allow_remote=args.allow_remote,
        metadata={"notes": args.note or []},
    )
    path = register_profile(profile, home, force_local_profile_name=args.force_local_profile_name)
    payload = {
        "command": "profile-add",
        "status": "OK",
        "home": str(home),
        "path": str(path),
        "profile": profile.name,
        "endpoint": profile.endpoint,
        "model": profile.model,
        "next": f"Run `yumani doctor --profile {profile.name}`.",
    }
    emit(payload, as_json=args.json)
    return 0


def cmd_profile_list(args: argparse.Namespace) -> int:
    home = home_from_args(args)
    profiles = [profile_summary(profile) for profile in list_profiles(home)]
    if args.json:
        emit({"command": "profile-list", "status": "OK", "home": str(home), "profiles": profiles}, as_json=True)
    else:
        print("[yumani:profiles] status=OK")
        if not profiles:
            print("No profiles registered.")
        for profile in profiles:
            print(f"- {profile['name']} -> {profile['endpoint']} model={profile['model']} enabled={profile['enabled']}")
    return 0


def cmd_profile_show(args: argparse.Namespace) -> int:
    profile = get_profile(args.profile, home_from_args(args))
    emit({"command": "profile-show", "status": "OK", "profile": profile_summary(profile)}, as_json=args.json)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    home = ensure_home(home_from_args(args))
    profile = get_profile(args.profile, home)
    endpoint_safety = validate_local_endpoint(profile.endpoint, allow_remote=profile.allow_remote)
    provider_status = "SKIPPED"
    provider_error = None
    fingerprint = None
    if args.probe_provider:
        try:
            models = fetch_models(profile.endpoint, timeout=args.timeout)
            fingerprint = provider_fingerprint(profile.endpoint, profile.model, models)
            provider_status = "OK"
        except Exception as exc:  # noqa: BLE001
            provider_status = "FAIL"
            provider_error = str(exc)
    payload = {
        "command": "doctor",
        "status": "OK" if endpoint_safety.allowed and provider_status != "FAIL" else "FAIL",
        "home": str(home),
        "profile": profile.name,
        "model": profile.model,
        "endpoint": profile.endpoint,
        "endpoint_safety": endpoint_safety.__dict__,
        "provider_status": provider_status,
        "provider_error": provider_error,
        "fingerprint": fingerprint,
    }
    emit(payload, as_json=args.json)
    return 0 if payload["status"] == "OK" else 2


def cmd_isolation_check(args: argparse.Namespace) -> int:
    home = ensure_home(home_from_args(args))
    profiles = [profile_summary(profile) for profile in list_profiles(home)]
    bad = []
    for profile_data in profiles:
        safety = validate_local_endpoint(profile_data["endpoint"])
        if not safety.allowed:
            bad.append({"profile": profile_data["name"], "reason": safety.reason})
    payload = {
        "command": "isolation-check",
        "status": "PASS" if not bad else "FAIL",
        "home": str(home),
        "checked_profiles": len(profiles),
        "violations": bad,
        "cloud_profiles_affected": False,
    }
    emit(payload, as_json=args.json)
    return 0 if not bad else 2


def cmd_state_init(args: argparse.Namespace) -> int:
    home = home_from_args(args)
    profile = get_profile(args.profile, home)
    root = project_root(args.project)
    store = StateStore(root, profile)
    store.ensure()
    payload = {
        "command": "state-init",
        "status": "OK",
        "profile": profile.name,
        "project": str(root),
        "state_dir": str(store.dir),
    }
    emit(payload, as_json=args.json)
    return 0


def cmd_context_pack(args: argparse.Namespace) -> int:
    home = home_from_args(args)
    profile = get_profile(args.profile, home)
    root = project_root(args.project)
    store = StateStore(root, profile)
    request = " ".join(args.request).strip()
    run = store.create_run(args.mode, request, status="CONTEXT_PACKING")
    pack = build_context_pack(profile=profile, project_root=root, request=request, mode=args.mode, include=args.include)
    pack_path = run.artifact_dir / "context" / "pack.md"
    accounting_path = run.artifact_dir / "context" / "accounting.json"
    pack_path.write_text(pack.text, encoding="utf-8")
    accounting_path.write_text(json.dumps(pack.accounting, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = pack.accounting["status"]
    store.update_run(
        run.run_id,
        status=status,
        failure_class=pack.accounting["failure_class"],
        context_pack_hash=pack.context_pack_hash,
        observed_result={
            "wrapper_facts_authoritative": True,
            "provider_called": False,
            "context_pack": str(pack_path),
            "accounting": pack.accounting,
        },
        model_claims={"claims": [], "attributed_to": profile.model},
    )
    payload = {
        "command": "context-pack",
        "status": status,
        "profile": profile.name,
        "model": profile.model,
        "project": str(root),
        "run_id": run.run_id,
        "context_pack": str(pack_path),
        "context_pack_hash": pack.context_pack_hash,
        "accounting": pack.accounting,
    }
    emit(payload, as_json=args.json)
    return 0 if status == "CONTEXT_PACKED" else 3


def cmd_run(args: argparse.Namespace) -> int:
    home = home_from_args(args)
    profile = get_profile(args.profile, home)
    root = project_root(args.project)
    request = " ".join(args.request).strip()
    store = StateStore(root, profile)
    run = store.create_run(args.mode, request, status="RUNNING")
    pack = build_context_pack(profile=profile, project_root=root, request=request, mode=args.mode, include=args.include)
    pack_path = run.artifact_dir / "context" / "pack.md"
    pack_path.write_text(pack.text, encoding="utf-8")
    provider_called = False
    provider_result = None
    status = pack.accounting["status"]
    failure = pack.accounting["failure_class"]
    if args.execute and status == "CONTEXT_PACKED":
        provider_called = True
        provider_result = chat_completion(
            endpoint=profile.endpoint,
            model=profile.model,
            messages=[{"role": "user", "content": pack.text}],
            max_tokens=profile.output_tokens,
            timeout=args.timeout,
        ).to_dict()
        status = "DONE" if provider_result["status"] == "PASS" else "FAILED"
        failure = provider_result["failure_class"]
    observed = {
        "wrapper_facts_authoritative": True,
        "provider_called": provider_called,
        "context_pack": str(pack_path),
        "accounting": pack.accounting,
        "provider_result": provider_result,
    }
    model_claims = {
        "attributed_to": profile.model,
        "claims": [{"claim_type": "TEXT_RESPONSE", "claim_text": provider_result["content"]}]
        if provider_result and provider_result.get("content")
        else [],
    }
    result_path = run.artifact_dir / "results" / "observed-result.json"
    claims_path = run.artifact_dir / "results" / "model-claims.json"
    result_path.write_text(json.dumps(observed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    claims_path.write_text(json.dumps(model_claims, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    store.update_run(
        run.run_id,
        status=status,
        failure_class=failure,
        context_pack_hash=pack.context_pack_hash,
        observed_result=observed,
        model_claims=model_claims,
    )
    payload = {
        "command": "run",
        "status": status,
        "failure_class": failure,
        "profile": profile.name,
        "model": profile.model,
        "project": str(root),
        "run_id": run.run_id,
        "provider_called": provider_called,
        "observed_result": str(result_path),
        "model_claims": str(claims_path),
        "next": "Use `yumani serve` for agent integration, or rerun with --execute for direct provider execution.",
    }
    emit(payload, as_json=args.json)
    return 0 if status in {"DONE", "CONTEXT_PACKED"} else 4


def cmd_calibrate(args: argparse.Namespace) -> int:
    home = home_from_args(args)
    profile = get_profile(args.profile, home)
    result = calibrate(
        profile,
        home=home,
        min_tokens=args.min_tokens,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )
    result["command"] = "calibrate"
    emit(result, as_json=args.json)
    return 0 if result["status"] in {"PASS", "DRY_RUN"} else 5


def cmd_serve(args: argparse.Namespace) -> int:
    home = home_from_args(args)
    profile = get_profile(args.profile, home)
    print(f"[yumani:serve] profile={profile.name} listening=http://{args.host}:{args.port}/v1 upstream={profile.endpoint}")
    serve(profile, home=home, host=args.host, port=args.port)
    return 0


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--home", default="", help="Yumani home directory. Defaults to $YUMANI_HOME or ~/.yumani.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yumani")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    sub = parser.add_subparsers(dest="command")

    init = sub.add_parser("init")
    add_common(init)
    init.set_defaults(func=cmd_init)

    setup = sub.add_parser("setup")
    add_common(setup)
    setup.add_argument("--profile", default="")
    setup.add_argument("--endpoint", default="")
    setup.add_argument("--model", default="")
    setup.add_argument("--adapter", default="openai-compatible")
    setup.add_argument("--safe-input-tokens", type=int, default=0)
    setup.add_argument("--hard-input-tokens", type=int, default=0)
    setup.add_argument("--output-tokens", type=int, default=0)
    setup.add_argument("--proxy-port", type=int, default=18137)
    setup.add_argument("--scan-timeout", type=float, default=1.5)
    setup.add_argument("--skip-scan", action="store_true")
    setup.add_argument("--yes", action="store_true", help="Non-interactive setup. Requires endpoint/model if no runtime is detected.")
    setup.add_argument("--dry-run", action="store_true")
    setup.add_argument("--start-proxy", action="store_true", help="Start the proxy after registration.")
    setup.add_argument("--force-local-profile-name", action="store_true")
    setup.set_defaults(func=cmd_setup)

    profile = sub.add_parser("profile")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    profile_add = profile_sub.add_parser("add")
    add_common(profile_add)
    profile_add.add_argument("--name", required=True)
    profile_add.add_argument("--endpoint", required=True)
    profile_add.add_argument("--model", required=True)
    profile_add.add_argument("--adapter", default="openai-compatible")
    profile_add.add_argument("--state-dir-name", default=".yumani")
    profile_add.add_argument("--safe-input-tokens", type=int, default=12_000)
    profile_add.add_argument("--hard-input-tokens", type=int, default=24_000)
    profile_add.add_argument("--output-tokens", type=int, default=2_048)
    profile_add.add_argument("--allow-remote", action="store_true")
    profile_add.add_argument("--force-local-profile-name", action="store_true")
    profile_add.add_argument("--note", action="append")
    profile_add.set_defaults(func=cmd_profile_add)

    profile_list = profile_sub.add_parser("list")
    add_common(profile_list)
    profile_list.set_defaults(func=cmd_profile_list)

    profile_show = profile_sub.add_parser("show")
    add_common(profile_show)
    profile_show.add_argument("--profile", required=True)
    profile_show.set_defaults(func=cmd_profile_show)

    doctor = sub.add_parser("doctor")
    add_common(doctor)
    doctor.add_argument("--profile", required=True)
    doctor.add_argument("--probe-provider", action="store_true")
    doctor.add_argument("--timeout", type=float, default=5.0)
    doctor.set_defaults(func=cmd_doctor)

    isolation = sub.add_parser("isolation-check")
    add_common(isolation)
    isolation.set_defaults(func=cmd_isolation_check)

    state_init = sub.add_parser("state-init")
    add_common(state_init)
    state_init.add_argument("--profile", required=True)
    state_init.add_argument("--project", default=".")
    state_init.set_defaults(func=cmd_state_init)

    pack = sub.add_parser("context-pack")
    add_common(pack)
    pack.add_argument("--profile", required=True)
    pack.add_argument("--project", default=".")
    pack.add_argument("--mode", choices=["chat", "work", "deep", "loop", "recovery"], default="work")
    pack.add_argument("--include", action="append", default=[])
    pack.add_argument("request", nargs="*")
    pack.set_defaults(func=cmd_context_pack)

    run = sub.add_parser("run")
    add_common(run)
    run.add_argument("--profile", required=True)
    run.add_argument("--project", default=".")
    run.add_argument("--mode", choices=["chat", "work", "deep", "loop", "recovery"], default="work")
    run.add_argument("--include", action="append", default=[])
    run.add_argument("--execute", action="store_true")
    run.add_argument("--timeout", type=float, default=300.0)
    run.add_argument("request", nargs="*")
    run.set_defaults(func=cmd_run)

    cal = sub.add_parser("calibrate")
    add_common(cal)
    cal.add_argument("--profile", required=True)
    cal.add_argument("--min-tokens", type=int, default=1024)
    cal.add_argument("--max-tokens", type=int, default=16000)
    cal.add_argument("--timeout", type=float, default=60.0)
    cal.add_argument("--dry-run", action="store_true")
    cal.set_defaults(func=cmd_calibrate)

    server = sub.add_parser("serve")
    add_common(server)
    server.add_argument("--profile", required=True)
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=18137)
    server.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "version", False):
        return cmd_version(argparse.Namespace(json=False))
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except SafetyError as exc:
        emit({"command": args.command, "status": "BLOCKED", "reason": str(exc)}, as_json=getattr(args, "json", False))
        return 10
    except Exception as exc:  # noqa: BLE001
        emit({"command": getattr(args, "command", "unknown"), "status": "FAIL", "reason": str(exc)}, as_json=getattr(args, "json", False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
