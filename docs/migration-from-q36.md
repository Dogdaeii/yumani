# Migration From q36 Harness

The original q36 harness was an effective field prototype, but it was tied to:

- `q36` as the profile name;
- `.q36` as the state directory;
- `18036` upstream and `18037` proxy ports;
- `HARNESS_INTERCEPT` as a Hermes-specific recovery tool;
- local files under `~/.hermes/local-harness`.

Yumani keeps the successful ideas and removes the q36 lock-in.

## Mapping

| q36 Harness | Yumani |
| --- | --- |
| `q36-harness` | `yumani` |
| `.q36/` | `.yumani/` |
| `profiles.yaml` | `~/.yumani/profiles.json` |
| q36 endpoint | profile `endpoint` |
| q36 model id | profile `model` |
| `HARNESS_INTERCEPT` | profile `recovery_tool_name` |
| q36-only proxy | per-profile proxy |

## Suggested q36 Profile

```bash
python3 -m yumani profile add \
  --name q36-local \
  --endpoint http://127.0.0.1:18036/v1 \
  --model q36 \
  --safe-input-tokens 12000 \
  --hard-input-tokens 24000 \
  --output-tokens 2048
```

Then run the proxy on a separate port:

```bash
python3 -m yumani serve --profile q36-local --port 18137
```

Do not replace the existing q36 production proxy until `yumani doctor`,
`yumani isolation-check`, and a real workload validation pass.

