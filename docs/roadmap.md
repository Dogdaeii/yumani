# Roadmap

Yumani starts as the clean product extraction from the q36 local harness.
The first target is correctness and isolation; public polish comes after the
local safety contract is trustworthy.

## M0 - Product Extraction

- New project folder and package name.
- No q36 runtime hardcoding in `src/yumani`.
- Local-only profile registry.
- `.yumani` project state.
- Context packer and OpenAI-compatible proxy.
- Unit tests for isolation, state, context packing, and proxy token caps.

Status: complete.

## M1 - Adapter Contract

- CUI setup flow for CLI-comfortable users.
- Agent setup guide for Codex/Claude/GPT-assisted installs.
- Define a generic recovery tool contract.
- Provide a Hermes adapter for `YUMANI_INTERCEPT`.
- Keep q36 `HARNESS_INTERCEPT` as a compatibility adapter, not a core concept.
- Add adapter tests that prove unknown tools are not injected into clients that
  have not registered them.

## M2 - Profile Installer

- Add a dry-run-first Hermes profile planner.
- Require explicit target profile and backup path.
- Refuse known cloud/shared profiles without a separate force flag and a local
  endpoint proof.
- Verify route guard before serving.

## M3 - Calibration Hardening

- Persist calibration by model fingerprint.
- Add crash-safe interrupted calibration recovery.
- Compare Ollama, MLX, oMLX, llama.cpp, and LM Studio endpoints.
- Produce recommended budgets by hardware class.

## M4 - Agent Workload Validation

- Synthetic loop, bad-tool, long-log, and side-effect recovery tests.
- Real workload cases on q36 and M3-small profiles.
- Publish reproducible validation reports without private project content.

## M5 - Public Release

- Installable package.
- Screenshots and terminal UX pass.
- Security policy.
- Contributor guide.
- Example configs for common local runtimes.
