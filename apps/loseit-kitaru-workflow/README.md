# loseit-kitaru-workflow

Pydantic-AI agent deployed to Kitaru as a flow. Drives the `loseit` CLI.

This package contains ONLY the flow code — no FastAPI, no Open WebUI Pipe.
Those live in sibling apps (`loseit-openwebui-agent`, `loseit-openwebui-pipe`).

## Architecture

```
chat → openwebui-pipe → loseit-openwebui-agent (FastAPI)
                              │
                              ↓
                       KitaruClient.deployments.invoke()
                              │
                              ↓
                       Kitaru server (kubernetes stack)
                              │
                              ↓
                       pod running loseit_agent_flow
                              │
                              ↓
                       Ollama + loseit CLI
```

## ⚠️ Deployment is NOT YET WIRED — needs a Kubernetes stack on Kitaru

`kitaru deploy` only works against a **remote-executable** stack (Kubernetes,
Vertex, SageMaker, AzureML). Our current `default-s3` stack uses
LocalOrchestrator and will be rejected by `kitaru deploy`.

**TODO (operator)**: create a Kubernetes stack and deploy the flow.

```bash
# 1. Create the Kubernetes stack
env -u KITARU_SERVER_URL -u KITARU_API_KEY -u KITARU_AUTH_TOKEN \
  uvx --from "kitaru[local]" kitaru stack create k8s-homelab \
    --type kubernetes \
    --artifact-store s3://kitaru-artifacts \
    --container-registry cr.priv.mlops-club.org/loseit-kitaru-workflow \
    --cluster default \
    --namespace loseit-kitaru-workflow \
    --no-verify

# 2. Deploy the flow (Kitaru builds + pushes the container image automatically)
uvx --from "kitaru[local]" kitaru deploy \
  apps/loseit-kitaru-workflow/src/loseit_kitaru_workflow/flow.py:loseit_agent_flow \
  --image '{"requirements": ["s3fs>2022.3.0,!=2025.3.1", "boto3"]}'

# 3. Verify
kitaru deployments list
```

Once deployed, the FastAPI service (`loseit-openwebui-agent`) can invoke
the flow and stream events back via `KitaruClient.executions.events(exec_id)`.

## Why this isn't deployed yet

The Kubernetes orchestrator setup requires:
- ServiceAccount RBAC for the Kitaru server to launch pods in `loseit-kitaru-workflow`
- A working Harbor pull secret in `loseit-kitaru-workflow` namespace
- Possibly a node selector to pin pods to the GPU node (so they can reach Ollama)
- Verifying that the deployed pod's pyproject can resolve our private `lose-it` git dep

These are real operator tasks. The code in this package is structurally correct
and ready to be deployed once the stack is in place.

## Local development (without deployment)

You can still run the flow locally for iteration:

```bash
uv run --with kitaru[pydantic-ai] python -c "\
  from loseit_kitaru_workflow import loseit_agent_flow
  handle = loseit_agent_flow.run('log 100g guacamole')
  print(handle.wait())"
```

This uses Kitaru's local orchestrator and runs entirely in your process —
NOT the desired production architecture, just useful for iteration.
