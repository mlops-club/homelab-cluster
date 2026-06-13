# loseit-openwebui-agent

⚠️ **NOT FOR MERGE** ⚠️  — exploratory restructure, working but needs operator setup before it runs end-to-end.

FastAPI gateway. Translates between the Open WebUI Pipe's wire format and Kitaru's
deployed-flow API. **No agent logic lives here** — the agent is `loseit-kitaru-workflow`,
deployed onto Kitaru as a proper flow.

## Architecture

```
chat → openwebui-pipe (apps/loseit-openwebui-pipe/)
            │
            ↓ HTTPS SSE
       loseit-openwebui-agent (THIS package, FastAPI in a k8s pod)
            │
            ↓ KitaruClient.deployments.invoke()
       Kitaru server (apps/kitaru/) ─── Kubernetes orchestrator ───┐
            │                                                       │
            ↓ client.executions.events() (SSE)                      ↓
       FastAPI forwards events back to the Pipe              pod-per-execution
                                                              (loseit_agent_flow)
                                                                    │
                                                                    ↓
                                                              Ollama + loseit CLI
```

Two packages, ZERO cross-imports:
- `loseit-kitaru-workflow/` — the deployed Kitaru flow (agent code, lose-it CLI subprocess)
- `loseit-openwebui-agent/` — this package (FastAPI + KitaruClient, NO agent code)

## What's blocking end-to-end working RIGHT NOW

1. **Kitaru's default-s3 stack is LocalOrchestrator** and `kitaru deploy` rejects local
   stacks (`KitaruStackNotRemoteExecutableUsageError`). The flow can't be deployed until
   a Kubernetes-orchestrator stack is registered.
2. **No Kubernetes stack exists yet** on the homelab Kitaru. Needs:
   - ServiceAccount RBAC for the Kitaru server to launch pods in the workflow namespace
   - Harbor pull secret accessible from the orchestrator's namespace
   - Image builder configured (likely kaniko since the cluster doesn't have
     local Docker daemons)
3. **`client.executions.events()` event-kind names** in this code are guesses based on
   the research report — the exact `kind` strings need verification against
   `kitaru._client._models.ExecutionEvent.kind` once the flow is actually running.

## Deploy

```bash
./apps/loseit-openwebui-agent/deploy.sh
```

This works TODAY. It builds + pushes the FastAPI image and rolls out the k8s deployment.
But every `/run` call will fail with `KitaruUsageError: no deployment named
'loseit_agent_flow'` until the workflow is actually deployed (see
`apps/loseit-kitaru-workflow/README.md`).

## Wire format (Pipe ↔ this service)

Unchanged from prior versions. SSE frames over `POST /run` with bearer auth:

```
data: {"kind":"tool",       "name":"...", "args_preview":"...", "call_id":"..."}
data: {"kind":"tool_done",  "name":"...", "args_preview":"...", "call_id":"...",
                             "elapsed_s": 1.3, "result_preview":"...",
                             "result_truncated": false}
data: {"kind":"wait",       "exec_id":"...", "wait_name":"...",
                             "prompt":"...", "options":[...]}
data: {"kind":"final",      "text":"..."}
data: {"kind":"error",      "message":"..."}
```

The Pipe stays unchanged; the wire is the contract.
