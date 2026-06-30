# Cloud Isolation

Yumani must never affect cloud profiles.

This is not a preference; it is the top-level safety rule. Hermes or another
agent runner may load many model profiles from the same runtime, so Yumani has
to make accidental cross-profile contamination hard.

## Current Enforcement

- Cloud-looking profile names are blocked unless the caller uses an explicit
  force flag.
- Only loopback HTTP endpoints are accepted by default.
- Runtime state is separated into `~/.yumani/` and `<project>/.yumani/`.
- No automatic Hermes profile mutation is performed in v0.1.

## Blocked By Default

Examples:

```text
hay
default
gpt55
gpt44
gpt
claude
gemini
codex
openai
anthropic
```

## Allowed By Default

Examples:

```text
my-local-agent -> http://127.0.0.1:18036/v1
m3-small  -> http://127.0.0.1:11434/v1
mlx-dev   -> http://localhost:8080/v1
```

