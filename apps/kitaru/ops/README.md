# Kitaru ops — one-time bootstrap

`bootstrap.sh` is the operator-side companion to `apps/kitaru/deploy.sh`. Run it once after Kitaru is deployed (and once again any time you rotate the Lose It! JWT) to plant the Lose It! token in Kitaru's secret store, mint a Kitaru API key for the `loseit-agent` service, and mirror that key into the cluster as a K8s Secret the Deployment can consume.

## When to run

- **First-time setup**, after `./apps/kitaru/deploy.sh` is green and `curl https://kitaru.priv.mlops-club.org/health` returns 200.
- **After rotating** `~/.config/loseit/token` (e.g. you logged into Lose It! again on your laptop): re-run to push the fresh JWT into Kitaru. Step 3 is the only one that strictly needs to re-run, but the script handles it cleanly end-to-end.

## Prerequisites

- You are on the Tailnet (so `kitaru.priv.mlops-club.org` resolves and TLS works).
- `kubectl` is pointed at the homelab cluster (`kubectl config current-context` shows the right one).
- `uvx` is installed (`brew install uv` or see https://docs.astral.sh/uv/).
- `~/.config/loseit/token` exists and is non-empty — i.e. you've already logged into Lose It! with the `lose-it` CLI on this machine.
- The `loseit-agent` namespace exists (i.e. `apps/loseit-agent/deploy.sh` has run at least once).

## Run it

From the repo root:

```bash
bash apps/kitaru/ops/bootstrap.sh
```

Step 2 will pop open a browser for the Kitaru OAuth flow — complete the login there, then come back. The rest is non-interactive (with one confirmation prompt if a stale K8s Secret already exists).

## What gets created

| Where | Name | Key(s) | Notes |
|---|---|---|---|
| Kitaru secret store | `loseit-token` | `token` | The raw Lose It! JWT. Per homelab mandate, app secrets live here, not in K8s. |
| Kitaru | service account `loseit-agent` | — | Created if missing; safe to re-run. |
| Kitaru | API key `loseit-agent-bootstrap` on the SA above | — | A new one is minted each run; the raw value is shown only once and is mirrored to K8s. |
| K8s | Secret `loseit-agent/kitaru-api-key` | `api_key`, `server_url` | What the Deployment mounts so it can auth to Kitaru and pull `loseit-token` at startup. `server_url` is `https://kitaru.priv.mlops-club.org`. |

## Rotate

- **Lose It! JWT**: re-run `bash apps/kitaru/ops/bootstrap.sh`. The Kitaru `loseit-token` secret is re-asserted; the existing K8s Secret will be detected and you'll be prompted before overwriting (you can decline that part if you only wanted to refresh the JWT — the new API key is discarded if you say no).
- **Kitaru API key only** (rare): re-run the script and confirm "overwrite". Then `kubectl -n loseit-agent rollout restart deploy/loseit-agent`.
- **Revoke**: `uvx --from "kitaru[local]" kitaru auth api-keys delete loseit-agent <key-name-or-id>`.

## Confirm it worked

```bash
# Kitaru side
uvx --from "kitaru[local]" kitaru secrets list             # 'loseit-token' should appear
uvx --from "kitaru[local]" kitaru auth service-accounts list  # 'loseit-agent' should appear
uvx --from "kitaru[local]" kitaru auth api-keys list loseit-agent

# K8s side
kubectl -n loseit-agent get secret kitaru-api-key
kubectl -n loseit-agent get secret kitaru-api-key -o jsonpath='{.data.server_url}' | base64 -d; echo
```

Then bounce the agent so it picks the new key up:

```bash
kubectl -n loseit-agent rollout restart deploy/loseit-agent
kubectl -n loseit-agent rollout status  deploy/loseit-agent
```

## Override knobs

The script reads a few env vars if you need to deviate from the defaults (you almost never will):

| Var | Default |
|---|---|
| `KITARU_URL` | `https://kitaru.priv.mlops-club.org` |
| `LOSEIT_TOKEN_FILE` | `~/.config/loseit/token` |
| `KITARU_SECRET_NAME` | `loseit-token` |
| `KITARU_SERVICE_ACCOUNT` | `loseit-agent` |
| `KITARU_API_KEY_NAME` | `loseit-agent-bootstrap` |
| `K8S_NAMESPACE` | `loseit-agent` |
| `K8S_SECRET_NAME` | `kitaru-api-key` |

## Safety notes

- The script never echoes the Lose It! JWT or the Kitaru API key to stdout. Both are passed inline and unset as soon as they've been written.
- If you abort during step 5 (refuse to overwrite the K8s Secret), the freshly minted API key is discarded — it's never persisted anywhere. Re-run the script to mint a new one.
- `set -euo pipefail` is on; any failure aborts and leaves state where it was.
