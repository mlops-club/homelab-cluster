# loseit-agent platform — specification

## Goal

Run a Kitaru-wrapped pydantic-ai agent on the homelab that drives the [`lose-it` CLI](https://github.com/phitoduck/lose-it) on behalf of a user typing in Open WebUI. The user watches each tool call land as a live status update above the streamed reply; when the agent hits a genuine ambiguity (e.g. "log some berries"), it pauses, asks the user a multiple-choice or free-text question, and resumes from the same checkpoint on the user's next message — no token replay.

Foundational infrastructure (Kitaru, Ollama already present, Open WebUI already present) and the agent application itself both live in `mlops-club/homelab-cluster`. The `lose-it` CLI continues to live in its own repo and ships as a Python wheel installed into the agent image.

## Non-goals

- Multi-user / multi-tenant. Single-user homelab use, account = the operator.
- Public exposure. Everything sits behind `traefik-private` on `*.priv.mlops-club.org`, Tailscale only.
- Production-grade observability at scale. Kitaru's bundled UI + SQLite is sufficient.
- Migrating Ollama or Open WebUI deployments. Those are already in `apps/` and stay where they are; we only add new components and reference their existing Service DNS.

## Components and contracts

| # | Component | Lives in | Talks to | Talks via |
|---|---|---|---|---|
| 1 | Open WebUI | `apps/open-webui/` (existing) | Pipe function, Ollama | HTTPS chat, in-process Python |
| 2 | Pipe function | uploaded to Open WebUI (also stored in `apps/loseit-agent/pipe/`) | FastAPI `/run` and `/resume` | Server-Sent Events over HTTPS |
| 3 | FastAPI agent server | `apps/loseit-agent/` (new) | KitaruAgent | in-process Python |
| 4 | KitaruAgent wrapper | inside the agent image | pydantic-ai Agent, Kitaru server | in-process; HTTPS to Kitaru API |
| 5 | pydantic-ai Agent | inside the agent image | Ollama, `loseit` CLI | OpenAI `/v1/chat/completions`; subprocess |
| 6 | Kitaru server + UI | `apps/kitaru/` (new) | SQLite + NFS artifact store | local PVC |
| 7 | Ollama | `apps/ollama/` (existing) | qwen3:8b on GPU node | OpenAI `/v1/...` |
| 8 | `loseit` CLI | installed inside agent image from PyPI/git | Lose It! HTTPS API | httpx + bearer token from mounted secret |

### Network topology

```
User → chat.priv.mlops-club.org (Open WebUI)
            └── Pipe function (in Open WebUI's Python process)
                    └── HTTPS SSE
                          └── loseit-agent.priv.mlops-club.org (FastAPI)
                                  ├── HTTPS → ollama.ollama.svc.cluster.local:11434
                                  ├── HTTPS → kitaru.kitaru.svc.cluster.local:8080
                                  └── subprocess `loseit` → HTTPS → loseit.com

User → kitaru.priv.mlops-club.org → Kitaru UI (browse / compare runs)
```

All same-namespace + cross-namespace traffic uses Kubernetes DNS. Edge traffic from the user's browser uses Tailscale-routed HTTPS via the existing `traefik-private` ingress class with the reflector-replicated `priv-wildcard-tls` secret. No public ingress, no Cloudflare tunnel.

### Auth

- **Open WebUI ↔ Pipe**: in-process, no auth boundary.
- **Pipe ↔ agent**: shared bearer token in a Kubernetes Secret, set as `AGENT_TOKEN` env var inside Open WebUI pod (via `extraEnvVars`) and as `AGENT_TOKEN_EXPECTED` env var inside the agent pod. Pipe sends `Authorization: Bearer <AGENT_TOKEN>`. Defense in depth — Tailscale already gates external reach, this guards against accidental in-cluster cross-namespace calls.
- **Agent ↔ Ollama**: none (Ollama ClusterIP is already in-cluster only; ingress also has no auth, lives on Tailscale).
- **Agent ↔ Kitaru**: API key stored in the `kitaru` namespace Secret, mounted into agent pod. (Kitaru's local mode uses no auth, but the server image likely requires a token — confirmed in S1.)
- **Agent ↔ Lose It!**: the user's existing JWT, mounted from a Kubernetes Secret (`loseit-token`) sourced from `~/.config/loseit/token` at deploy time. Read-only mount at `/home/agent/.config/loseit/token`.

### Streaming wire format (FastAPI → Pipe)

`POST /run` returns `text/event-stream`. Every event is one `data: <json>\n\n` line. Schema:

```json
{"kind": "tool",        "name": "search", "args_preview": "yogurt", "call_id": "..."}
{"kind": "tool_done",   "call_id": "..."}
{"kind": "model_call",  "turn": 1}
{"kind": "wait",        "exec_id": "abc", "wait_name": "clarify_berry",
                        "prompt": "Which berry?", "options": ["strawberry","blueberry","raspberry"]}
{"kind": "final",       "text": "Logged 85g yogurt..."}
{"kind": "error",       "message": "..."}
```

The Pipe maps:
- `tool` / `tool_done` → `__event_emitter__({"type":"status", ...})`
- `wait` → emit a `chat:message:delta` describing the question + options, end the response with `status: done`, store `exec_id` in `body["metadata"]` for the next turn.
- `final` → return as the Pipe's return value (streamed to chat).
- `error` → `__event_emitter__({"type":"notification","data":{"type":"error","content":...}})`.

`POST /resume` accepts `{"exec_id": "...", "value": "..."}` and returns the same SSE schema, continuing from the paused checkpoint.

### Auth on the chat side (which user am I?)

For the single-user homelab case, the agent uses the operator's loseit credentials from a fixed Secret. The Pipe does NOT pass per-user identity. If we later want multi-user, the Pipe will need to map Open WebUI's `__user__` to a per-user Lose It! token; out of scope for v1.

## Vertical slice plan

Each slice is end-to-end runnable. After each slice the system is at a strictly higher capability level than before. No slice leaves the platform in a half-built state.

### S0 — Spec + diagrams (this commit)
- Land `SPEC.md` and `ARCHITECTURE.md` (mermaid).
- **Verify:** GitHub renders both, mermaid blocks display correctly.

### S1 — Kitaru deployed, reachable, CLI connects
- `apps/kitaru/{manifest.yaml, deploy.sh, values.yaml, README.md}` — Helm-deployed `zenmldocker/zenml-server` image OR `kitaru` server image, single Deployment, PVC for SQLite + artifacts, Ingress at `kitaru.priv.mlops-club.org`.
- **Verify:**
  - `curl -sSf https://kitaru.priv.mlops-club.org/health` returns 200.
  - From laptop: `pipx install kitaru && kitaru login https://kitaru.priv.mlops-club.org` succeeds.
  - `kitaru executions list` returns an empty page (no errors).

### S2 — Echo FastAPI agent service deployed
- `apps/loseit-agent/Dockerfile` — uv slim base, FastAPI + httpx; no agent code yet.
- `apps/loseit-agent/server.py` — `POST /run` accepts `{"prompt": "..."}`, returns an SSE stream emitting `{"kind":"tool","name":"echo","args_preview":<prompt>}` then `{"kind":"tool_done"}` then `{"kind":"final","text":"echo: <prompt>"}`. Health endpoint `GET /healthz` returns 200.
- `apps/loseit-agent/manifest.yaml` — Namespace, Deployment, Service, Ingress at `loseit-agent.priv.mlops-club.org`. Image pulled from Harbor (`cr.priv.mlops-club.org/loseit-agent/agent:<sha>`); image built locally and pushed via `deploy.sh`.
- **Verify:**
  - `curl -N -X POST https://loseit-agent.priv.mlops-club.org/run -H "Authorization: Bearer $AGENT_TOKEN" -H "Content-Type: application/json" -d '{"prompt":"hi"}'` streams the 3 expected events.

### S3 — Open WebUI Pipe ↔ echo round-trip in chat
- `apps/loseit-agent/pipe/openwebui_pipe.py` — async Pipe class with valves for `agent_url` and `auth_token`; subscribes to SSE, maps `tool`/`tool_done` to `status` event_emitter calls, returns `final.text`.
- Pipe uploaded to Open WebUI Workspace → Functions (manual one-time step, documented in README). A `pipe-config-snapshot.json` is committed for repeatability.
- Add `AGENT_TOKEN` to Open WebUI's `extraEnvVars` in `apps/open-webui/values.yaml` (sourced from a Secret) and `helm upgrade`.
- **Verify:** In the chat UI, pick model "loseit-agent" (the Pipe appears as a model), type "hi", see status `→ echo(hi)` appear, then a streamed assistant message "echo: hi".

### S4 — Replace echo with real pydantic-ai loseit-search agent
- Install `lose-it` + `pydantic-ai` in the agent image.
- `server.py`: `POST /run` calls a real pydantic-ai `Agent(model=qwen3:8b)` with a single `search` tool wrapping `loseit search`.
- Mount the loseit token Secret into the agent pod.
- **Verify:** Chat "find guacamole" → Pipe shows `→ search(guacamole)` status, then a streamed list of 3-5 top results.

### S5 — KitaruAgent wrapper + live status events
- Add `KitaruAgent(...)` wrapping the inner Agent; configure `event_stream_handler` to forward Kitaru events to the SSE queue.
- Configure Kitaru client to point at `https://kitaru.kitaru.svc.cluster.local:8080` with API key from Secret.
- **Verify:**
  - Chat shows `→ search(...)` status as before, plus `→ model_call (turn 1)` etc.
  - `kitaru.priv.mlops-club.org` shows the run in the executions list; opening it shows the checkpoint tree with prompts and responses.
  - Run twice with different prompts; both appear, and `kitaru executions statistics` shows token aggregates.

### S6 — Full agent (5 tools) — log a real meal via chat
- Port the 5-tool agent (`search`, `describe_food`, `log_food`, `diary`, `whoami`) from the lose-it repo's `tools/agent-sandbox/agent.py` — same system prompt and guardrails.
- Keep the magnitude guardrail (`tbsp/tsp > 30` refused).
- **Verify:** Chat "log 100g guacamole as a snack" → status updates for search → describe_food → log → diary; final message confirms entry; `loseit diary --date $TODAY` on operator's laptop shows the new row.

### S7 — Ambiguity → `kitaru.wait` → resume via next chat message
- Add a `kitaru.wait()` checkpoint inside a wrapping tool when the agent decides a food query has too many plausible matches and no strong heuristic to pick (or when the user input is genuinely ambiguous like "berries").
- `POST /resume` endpoint accepts `{"exec_id", "value"}` and calls `client.executions.input(...)`.
- Pipe stores `exec_id` in `body["metadata"]["loseit_exec_id"]`; on the next user message in the same chat, routes to `/resume` instead of `/run`.
- **Verify:** Chat "log some berries" → agent emits a `wait` event → Pipe shows "Which berry? strawberry / blueberry / raspberry / type your own" → user types "blueberry" → agent resumes, logs, confirms. The Kitaru UI for this execution shows two segments separated by a `wait` checkpoint with the value the user provided.

### S8 — PR open with diagrams + per-slice verification log
- `feat/loseit-agent-platform` branch pushed to `mlops-club/homelab-cluster`.
- PR body: summary, vertical-slice checklist with ✅, embedded mermaid (architecture + sequence), links to `SPEC.md` + `ARCHITECTURE.md`.
- Codex review run on each slice's diff; review comments either resolved or filed as follow-ups in the PR description.

## Repository layout

```
apps/
├── kitaru/
│   ├── README.md
│   ├── manifest.yaml          # Namespace, PVC, Ingress
│   ├── values.yaml            # if Helm-deployed
│   └── deploy.sh
├── loseit-agent/
│   ├── README.md
│   ├── SPEC.md                # this file
│   ├── ARCHITECTURE.md        # mermaid diagrams
│   ├── Dockerfile
│   ├── server.py              # FastAPI + KitaruAgent
│   ├── manifest.yaml          # Namespace, Secrets refs, Deployment, Service, Ingress
│   ├── deploy.sh              # build + push to Harbor + kubectl apply
│   └── pipe/
│       ├── openwebui_pipe.py  # the Pipe Function (uploaded via Open WebUI UI)
│       └── pipe-config.md     # one-time setup instructions
└── open-webui/                # existing — touched only to add AGENT_TOKEN env var
```

## Verification primitives

Each slice ends with a real command that another human (or Codex) could run to confirm. Specifically:

- **Health curl** for any HTTP service.
- **End-to-end chat** via the Open WebUI web UI captured as a screenshot or browser log.
- **Diary readback** via the `loseit` CLI on the operator's laptop, for slices that should produce diary entries.
- **Kitaru UI snapshot** for slices that should produce executions.
- **`codex review`** of the diff after each commit. The agent will surface any high-confidence correctness, security, or architecture concerns; concerns either get fixed in the same slice or move to a follow-up issue tracked in the PR body.

## Open questions to resolve as we build

1. **Does the `kitaru` Helm path exist, or do we deploy the OCI image directly with kubectl?** S1's job to answer. If Helm chart exists, use it. If not, plain Deployment.
2. **How does Open WebUI persist Functions across restarts?** They're stored in its SQLite DB inside the PVC, so manual upload survives restarts. We commit the function source to the repo but the install step is one-time-per-environment. Acceptable.
3. **Does Kitaru's `wait()` API accept a list of `options` for the Pipe to render as multi-choice?** Per the adapter source the `wait` checkpoint takes a name and arbitrary kwargs. We'll pass `options=[...]` and read them server-side; if the API requires a schema we adapt in S7.
4. **Does qwen3:8b reliably emit the right tool calls under Kitaru's added checkpoint overhead?** S5 verifies.

## Things explicitly deferred

- **Eval / scoring of runs** — Opik or Logfire layer can come later (matrix already drafted).
- **Scheduled flows** (`/log breakfast` at 9am) — needs Kitaru `flow.deploy()` + a scheduler.
- **Per-user identity** — requires Pipe-side user-token mapping.
- **Run-diff UI** — Kitaru doesn't have it natively; we use programmatic diff via `client.artifacts.load()` if needed.
