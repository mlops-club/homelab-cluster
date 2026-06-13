# Open WebUI Pipe — one-time install

The Pipe lives inside Open WebUI's SQLite DB once uploaded. This file is the source-of-truth so you can re-upload after a fresh install.

## Install

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
| 401 from agent | `auth_token` valve doesn't match the agent's `AGENT_TOKEN_EXPECTED` env var |
| Pipe not in model picker | Function disabled, or pipe class missing `id` / `name` |
| Status shimmer never stops | Missing `done: True` at the end of a status sequence (Pipe always emits one — if you forked the code, preserve that final emit) |
| `Pipe transport error` | Network reachability — agent service down, or DNS not resolving over Tailscale |
