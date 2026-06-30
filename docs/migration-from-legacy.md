# Migration From legacy Harness

The original legacy harness was an effective field prototype, but it was tied to:

- `legacy` as the profile name;
- `.legacy` as the state directory;
- `18036` upstream and `18037` proxy ports;
- `HARNESS_INTERCEPT` as a Hermes-specific recovery tool;
- local files under `~/.hermes/local-harness`.

Yumani keeps the successful ideas and removes the legacy lock-in.

## Mapping

| legacy Harness | Yumani |
| --- | --- |
| `legacy-harness` | `yumani` |
| `.legacy/` | `.yumani/` |
| `profiles.yaml` | `~/.yumani/profiles.json` |
| legacy endpoint | profile `endpoint` |
| legacy model id | profile `model` |
| `HARNESS_INTERCEPT` | profile `recovery_tool_name` |
| legacy-only proxy | per-profile proxy |

## Suggested legacy Profile

```bash
python3 -m yumani profile add \
  --name legacy-local \
  --endpoint http://127.0.0.1:18036/v1 \
  --model legacy \
  --safe-input-tokens 12000 \
  --hard-input-tokens 24000 \
  --output-tokens 2048
```

Then run the proxy on a separate port:

```bash
python3 -m yumani serve --profile legacy-local --port 18137
```

Do not replace the existing legacy production proxy until `yumani doctor`,
`yumani isolation-check`, and a real workload validation pass.

