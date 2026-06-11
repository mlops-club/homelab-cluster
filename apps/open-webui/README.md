# Open WebUI

Browser chat UI for the cluster's LLM serving stack. Deployed in the `open-webui` namespace, reachable at **https://chat.priv.mlops-club.org** (tailnet only). The UI itself has no GPU access — it forwards every chat to the Ollama service running in the `ollama` namespace.

```
You (browser, tailnet)
   ↓ HTTPS via Traefik-private
chat.priv.mlops-club.org
   ↓ in-cluster
open-webui.open-webui.svc → ollama.ollama.svc:11434 → RTX 5080 on cluster-node-4
```

## Prereqs

Deploy Ollama first — Open WebUI's `values.yaml` hard-codes its service URL:

```bash
./apps/ollama/deploy.sh
./apps/open-webui/deploy.sh
```

## Deploy

```bash
./apps/open-webui/deploy.sh
```

Idempotent. Re-running converges to `values.yaml`.

## First-time setup

1. Open https://chat.priv.mlops-club.org (must be on the tailnet).
2. Create the **first** account — Open WebUI auto-promotes the first signup to admin.
3. Once you're in as admin, head to Admin Settings → Users and either disable signups (`ENABLE_SIGNUP=false`) or leave the default `pending` role on new signups so they need your approval.
4. The qwen3:8b model should already show up in the model picker (pulled by the Ollama chart on first start). If not, give it a few more minutes — first-deploy model pull takes ~3-5 min.

## Auth defaults (in `values.yaml`)

| Env | Default here | What it does |
|---|---|---|
| `WEBUI_AUTH` | `true` | Force login on every visit |
| `ENABLE_SIGNUP` | `true` | Lets you create the first account; flip to `false` after |
| `DEFAULT_USER_ROLE` | `pending` | New signups can't use the app until admin approves |
| `ENABLE_COMMUNITY_SHARING` | `false` | No chat sharing to the public Open WebUI community |

## Persistence

Open WebUI stores user accounts + chat history in a SQLite DB on a 5 Gi PVC backed by K3s's default `local-path` storage class — node-local on whichever worker the pod lands on (currently always `cluster-node-1/2/3` since the GPU node is loaded). Survives pod restarts and re-deploys.

To back up: `kubectl -n open-webui exec deploy/open-webui -- tar c -C /app/backend/data .` and stash somewhere safe.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `chat.priv.mlops-club.org` doesn't resolve | Not on the tailnet, OR external-dns hasn't created the record yet (check `kubectl -n traefik-private logs deploy/external-dns`) |
| TLS error in browser | `priv-wildcard-tls` not replicated to `open-webui` namespace — check reflector logs |
| Model picker shows no models | Ollama still pulling on first start. `kubectl -n ollama logs deploy/ollama` to confirm. |
| "Failed to connect to Ollama" | Service DNS resolution issue. From inside the open-webui pod: `wget -qO- ollama.ollama.svc.cluster.local:11434` should return "Ollama is running". |
