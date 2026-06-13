# Open WebUI Pipe — install + configuration

The Pipe lives inside Open WebUI's SQLite DB once uploaded. This file is the source-of-truth so you can re-upload after a fresh install.

Two install paths:
- [**Automated install**](#automated-install) — recommended. Runs `install.sh`, which hits Open WebUI's admin REST API.
- [**Manual install**](#manual-install-fallback) — paste the Pipe source into the admin UI. Use when the API isn't reachable from your shell.

---

## Automated install

### One-time prerequisite: get an Open WebUI bearer token

Open WebUI's admin REST API needs a bearer token. Two ways to obtain one, pick whichever is easier:

**Option A — admin email + password (recommended).** The install script trades them for a short-lived JWT via `POST /api/v1/auths/signin`. Works on any Open WebUI deploy out of the box (no admin-side config switches).

```bash
export OPENWEBUI_EMAIL='you@example.com'
export OPENWEBUI_PASSWORD='…'
```

**Option B — long-lived API key.** Open WebUI hides this behind a config flag that is **off by default**.

1. As admin, open `https://chat.priv.mlops-club.org`.
2. Admin Panel → Settings → General → toggle **Enable API Key** ON. Save.
3. Click your avatar (top-right) → **Settings** → **Account** → **API Keys** → **+ Create new secret key**. Copy the `sk-…` value.
4. Export:

```bash
export OPENWEBUI_API_KEY='sk-…'
```

### Run the installer

```bash
# loseit-agent's bearer token — read from the existing k8s Secret:
export AUTH_TOKEN="$(kubectl -n loseit-agent get secret agent-token \
    -o jsonpath='{.data.token}' | base64 -d)"

# (If you skip this, install.sh will try kubectl itself.)

bash apps/loseit-agent/pipe/install.sh
```

Optional overrides:

| Env var | Default |
|---|---|
| `OPENWEBUI_URL` | `https://chat.priv.mlops-club.org` |
| `AGENT_URL` | `https://loseit-agent.priv.mlops-club.org` |

### What it does

1. Authenticates (sk- key OR signin → JWT).
2. Reads `apps/loseit-agent/pipe/openwebui_pipe.py`.
3. `POST /api/v1/functions/create` (or `/id/loseit_agent/update` if it exists).
4. `POST /api/v1/functions/id/loseit_agent/valves/update` with `{agent_url, auth_token}`.
5. `POST /api/v1/functions/id/loseit_agent/toggle` if not already enabled.
6. `GET /api/v1/functions/id/loseit_agent` to verify.

### Expected output

```text
[install.sh] using OPENWEBUI_API_KEY (bearer)
[install.sh] authenticated against https://chat.priv.mlops-club.org
[install.sh] function 'loseit_agent' not found (HTTP 401) — POST /create
[install.sh] setting valves (agent_url=https://loseit-agent.priv.mlops-club.org, auth_token=<redacted>)
[install.sh] enabling function
[install.sh] toggle HTTP 200
[install.sh] remote content length: 5427 (local: 5453)
[install.sh] remote is_active: true
[install.sh] OK — 'loseit-agent' should now appear in the model picker.
```

(The remote/local content length usually differs by a few bytes because Open WebUI rewrites a couple of `from open_webui…` imports during upload — this is expected. The verify step asserts the function exists and is enabled, not byte equality.)

The script is idempotent. Re-runs print `function 'loseit_agent' exists — POST /id/loseit_agent/update` and `function already enabled`.

### Caveat: function id is `loseit_agent` (underscore)

Open WebUI requires function ids to be Python identifiers (`[A-Za-z_][A-Za-z0-9_]*`), so the database row is `loseit_agent`. The **display name** in the model picker is `loseit-agent` (with the hyphen) — this comes from the `name` field on the function and from `self.id` / `self.name` on the Pipe class. End-users only ever see `loseit-agent`.

---

## Manual install (fallback)

Use this if you can't reach the Open WebUI API from your shell — e.g. you're on a phone, or `kubectl` isn't set up.

1. Open `https://chat.priv.mlops-club.org` (Tailscale only).
2. Workspace → Functions → **+ New Function**.
3. Paste the entire contents of `openwebui_pipe.py` into the editor.
4. Set the function name to `loseit-agent`. Save.
5. Open the function's Valves (gear icon) and set:
   - `agent_url` = `https://loseit-agent.priv.mlops-club.org`
   - `auth_token` = output of:
     ```bash
     kubectl -n loseit-agent get secret agent-token -o jsonpath='{.data.token}' | base64 -d
     ```
6. Toggle the function ON.

---

## Use

1. Start a new chat.
2. Model picker → **loseit-agent**.
3. Type a prompt (e.g. `"log 100g guacamole as a snack"`).

You should see live status updates appear above the streamed reply.

## Multi-turn resume

When the agent pauses for clarification, the Pipe stores `exec_id` on the chat's metadata. The user's next message in the same chat is forwarded to `POST /resume` rather than `POST /run`. To start fresh, open a new chat.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `install.sh` exits 2 with "Open WebUI auth not configured" | Neither `OPENWEBUI_API_KEY` nor `OPENWEBUI_EMAIL`+`OPENWEBUI_PASSWORD` were exported. See [Automated install](#automated-install). |
| `install.sh` says `auth probe failed (HTTP 401)` | `OPENWEBUI_API_KEY` is wrong or the underlying user isn't an admin; or `ENABLE_API_KEYS` is off on the server (use Option A: email + password instead). |
| `install.sh` says `create failed: … Only alphanumeric characters and underscores are allowed in the id` | You changed `FUNCTION_ID` to something with a hyphen. Open WebUI requires Python-identifier ids. |
| 401 from agent | `auth_token` valve doesn't match the agent's `AGENT_TOKEN_EXPECTED` env var |
| Pipe not in model picker | Function disabled, or pipe class missing `id` / `name` |
| Status shimmer never stops | Missing `done: True` at the end of a status sequence (Pipe always emits one — if you forked the code, preserve that final emit) |
| `Pipe transport error` | Network reachability — agent service down, or DNS not resolving over Tailscale |
