# Agent Setup Guide

This file is written for frontier coding agents such as Codex, Claude Code, or
GPT-based coding assistants that are asked by a user to install Yumani.

## Top-Level Safety Rule

Yumani is for explicit local LLM profiles only.

Do not edit, wrap, route, or migrate cloud profiles such as:

```text
default, hay, gpt55, gpt44, GPT, Claude, Gemini, Codex, OpenAI, Anthropic
```

Do not put cloud API URLs into Yumani. Valid default endpoints must be loopback
OpenAI-compatible local endpoints, such as:

```text
http://127.0.0.1:11434/v1
http://127.0.0.1:1234/v1
http://127.0.0.1:8080/v1
```

## Preferred Install Flow

```bash
git clone <YUMANI_REPO_URL>
cd yumani
python3 -m pip install -e .
yumani setup
```

`yumani setup` is intentionally a question-driven CUI flow. Read the scan
results, choose the local runtime, choose the model, pick a budget preset or
custom budget, then start the proxy only if the user asks for it.

## Non-Interactive Agent Flow

Use this when the user already knows their local endpoint and model:

```bash
yumani setup \
  --yes \
  --skip-scan \
  --profile m3-small \
  --endpoint http://127.0.0.1:11434/v1 \
  --model qwen3:4b-instruct \
  --safe-input-tokens 6000 \
  --hard-input-tokens 12000 \
  --output-tokens 1024
```

Then verify:

```bash
yumani doctor --profile m3-small --probe-provider
yumani isolation-check
```

Start the proxy:

```bash
yumani serve --profile m3-small --port 18138
```

Configure the user's local-agent client to use:

```text
http://127.0.0.1:18138/v1
```

## Refusal Conditions

Stop and ask the user before proceeding if:

- the endpoint is not loopback;
- the requested profile name is a known cloud/shared profile;
- the user asks you to change GPT/Claude/Gemini/Codex cloud profile routing;
- provider probing exposes secrets or cloud API URLs;
- installation would overwrite an unrelated existing profile.
