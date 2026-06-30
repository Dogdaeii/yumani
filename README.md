# Yumani

Yumani is a local-only LLM harness for memory-safe agent work.

It acts as a protective layer for local models that can run out of memory, lose context, repeat failed actions, or hang during long coding sessions.

## Non-Negotiable Rule

Yumani is only for explicit local LLM profiles. It must not mutate, route, wrap,
or share state with cloud profiles such as GPT, Claude, Gemini, Codex, or any
shared Hermes default/cloud profile.

The first version enforces that rule by default:

- profile names that look like cloud/shared profiles are blocked;
- endpoints must be loopback HTTP (`127.0.0.1`, `localhost`, or `::1`);
- runtime state is project-local under `.yumani/`;
- global state is under `~/.yumani/`, never under cloud profile state.

## What It Does

- Registers any OpenAI-compatible local model endpoint.
- Packs large agent contexts before they reach a local model.
- **Turn-Based Context Packing (v0.1.1)**: Safely archives old messages by full `[User -> Assistant -> Tool]` turns without breaking prompt templates (prevents HTTP 400 errors).
- **Agent-Driven State Protocol (v0.1.1)**: Forces autonomous context retention (`YUMANI_STATE.md`) by dynamically injecting survival protocols at the bottom of the prompt to defeat **Recency Bias**.
- Caps output budgets per profile.
- Records wrapper-owned observations separately from model claims.
- Provides an OpenAI-compatible proxy (`/v1/models`, `/v1/chat/completions`).
- Writes per-turn manifests for audits and crash recovery.
- Calibrates safe input boundaries for a model fingerprint.

> 📖 **Read more about how Yumani solves OOM and Recency Bias in [docs/principles.md](docs/principles.md).**

## Quick Start

```bash
cd yumani
python3 -m pip install -e .
yumani setup
```

`yumani setup` is a CUI installer. It scans common local runtimes, asks you to
answer a short sequence of questions, writes `~/.yumani/profiles.json`, and
prints the proxy command.

The default wizard asks:

1. whether to scan local runtimes;
2. which local runtime to protect;
3. which model to route to;
4. what local profile name to use;
5. which context budget preset to start with;
6. whether to probe the provider and start the proxy now.

For a generic local endpoint:

```bash
yumani setup \
  --yes \
  --skip-scan \
  --profile my-local-agent \
  --endpoint http://127.0.0.1:11434/v1 \
  --model my-model-id \
  --safe-input-tokens 12000 \
  --hard-input-tokens 24000 \
  --output-tokens 2048
yumani doctor --profile my-local-agent
yumani serve --profile my-local-agent --port 18137
```

Point an OpenAI-compatible client at:

```text
http://127.0.0.1:18137/v1
```

The upstream local model remains:

```text
http://127.0.0.1:18036/v1
```

## Small Model Example

```bash
python3 -m yumani profile add \
  --name m3-small \
  --endpoint http://127.0.0.1:11434/v1 \
  --model qwen3:4b-instruct \
  --safe-input-tokens 6000 \
  --hard-input-tokens 12000 \
  --output-tokens 1024

python3 -m yumani serve --profile m3-small --port 18138
```

## Context Pack

```bash
python3 -m yumani context-pack \
  --profile my-local-agent \
  --project /path/to/project \
  --include src/main.py \
  "Review the current failure and suggest the next action."
```

Artifacts are written to:

```text
<project>/.yumani/
  state.db
  state.md
  manifest.json
  runs/<run_id>/
    request.md
    context/pack.md
    context/accounting.json
    results/observed-result.json
    results/model-claims.json
```

## Calibration

```bash
python3 -m yumani calibrate --profile my-local-agent --min-tokens 1024 --max-tokens 16000
```

Calibration artifacts are saved under:

```text
~/.yumani/calibration/
```

Use `--dry-run` when you want to verify fingerprint and artifact flow without
stress-testing the model.

## Current Scope

This repository provides a portable core: profile registry, local-only isolation, state DB,
context packing, proxy routing, and calibration.

Agent-specific plugin bridges (`HARNESS_INTERCEPT`) are intentionally not
hardcoded here. Yumani exposes the generic recovery contract through profile
metadata and proxy manifests; model/client-specific recovery tools should be
installed as explicit adapters.

See [docs/roadmap.md](docs/roadmap.md) for the path to a public-ready release.

If you are asking a frontier coding agent to install Yumani for you, give it
[AGENT_SETUP.md](AGENT_SETUP.md). That guide tells the agent exactly what it may
and may not touch.

## Design Goal

Yumani should become the default safety layer for people who want frontier-style
agent workflows on limited local hardware without sacrificing the best reasoning
their local model can provide.
