# CUI Setup

Yumani targets CLI-comfortable users, so setup should feel like a clear terminal
installer rather than a hidden one-liner.

The main entrypoint is:

```bash
yumani setup
```

The setup flow:

1. Prints the Yumani home and confirms cloud profiles are not touched.
2. Scans common local OpenAI-compatible endpoints.
3. Shows detected runtimes and model ids.
4. Lets the user choose runtime, model, profile name, and budgets.
5. Registers the local profile under `~/.yumani/profiles.json`.
6. Prints the proxy command and local proxy URL.

For agent-driven installs or scripted setup:

```bash
yumani setup \
  --yes \
  --skip-scan \
  --profile local-small \
  --endpoint http://127.0.0.1:11434/v1 \
  --model qwen3:4b-instruct
```

The CUI is deliberately conservative:

- it does not mutate Hermes, Claude Code, Codex, or other client configs by
  default;
- it does not touch cloud profiles;
- it rejects non-loopback endpoints unless a future explicit remote mode is
  implemented with a separate threat model.

