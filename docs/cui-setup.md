# CUI Setup

Yumani targets CLI-comfortable users, so setup should feel like a clear terminal
installer rather than a hidden one-liner.

The main entrypoint is:

```bash
yumani setup
```

The default setup flow is question-driven:

1. Confirms the Yumani home and that cloud profiles are not touched.
2. Asks whether to scan common local OpenAI-compatible endpoints.
3. Shows detected runtimes and lets the user choose one or enter a manual endpoint.
4. Lets the user choose a discovered model or type a model id.
5. Asks for the local profile name.
6. Offers `Small`, `Balanced`, `Large/reasoning`, and `Custom` budget presets.
7. Asks whether to probe the provider.
8. Asks for the proxy port and whether to start the proxy immediately.
9. Prints the client-facing proxy URL.

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
