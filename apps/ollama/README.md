# Ollama

GPU-backed LLM inference service. Deployed in the `ollama` namespace, bound to `cluster-node-4` (the only GPU node), reachable in-cluster at `http://ollama.ollama.svc.cluster.local:11434`. Not exposed via ingress — only other workloads in the cluster talk to it.

## Storage layout

All model weights for this cluster live on `cluster-node-4`'s NVMe under one predictable root:

```
/srv/models/
├── ollama/         ← Ollama blob store (this app's PVC)
└── huggingface/    ← reserved for future vLLM / TGI / huggingface-cli pulls
```

Both directories are exposed as static `hostPath` PVs (`ollama-models`, `huggingface-cache`) pinned to `cluster-node-4` via `nodeAffinity`. The HF cache PV is created up-front so the path exists and is mountable the moment you add a second GPU workload — no need to touch `manifest.yaml` again.

**Don't put PVCs of this from other namespaces.** A `hostPath` PV with `accessModes: ReadWriteOnce` only binds to one PVC. If you want another namespace to use the HF cache, you'll create a PVC for `huggingface-cache` in that namespace.

## Model choice

Pre-pulled on first start: **qwen3:8b** (Q4_K_M, ~4.5 GB).

VRAM budget on a single RTX 5080 (16 GB):

| Component | Cost |
|---|---|
| qwen3:8b Q4_K_M weights | ~4.5 GB |
| 128K-token KV cache, Q8_0 quantization | ~9.4 GB |
| Activations / scratch | ~2 GB |
| **Total** | **~16 GB** (just fits) |

Why not qwen3:14b? At 128K context with Q8 KV the math comes out to ~18.6 GB → OOM. To run 14b you'd need to either drop `OLLAMA_CONTEXT_LENGTH` to ~32K or switch `OLLAMA_KV_CACHE_TYPE` to `q4_0`. Either works; both are easy `values.yaml` edits. I picked qwen3:8b because "biggest comfortable fit at full 128K" was the prompt.

To add more models, either:
1. Pull through the Open WebUI model picker (downloads to the same PV).
2. Or `ollama pull <model>` inside the pod: `kubectl -n ollama exec deploy/ollama -- ollama pull llama3.1:8b`.

## Runtime configuration

These env vars are set in `values.yaml`:

| Var | Value | Why |
|---|---|---|
| `OLLAMA_FLASH_ATTENTION` | `1` | Required to use KV cache quantization |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | Halves KV cache size vs FP16 with minimal quality loss |
| `OLLAMA_CONTEXT_LENGTH` | `131072` | Default 128K context window |
| `OLLAMA_KEEP_ALIVE` | `24h` | Keep model in VRAM between requests |
| `OLLAMA_NUM_PARALLEL` | `1` | 16 GB VRAM can't handle 128K × 2 concurrent |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | Only one model in VRAM at a time |

## Deploy

```bash
./apps/ollama/deploy.sh
```

Idempotent — re-running it converges to whatever's in `values.yaml`. First boot takes 3-5 minutes because the chart pulls qwen3:8b before it reports ready.

## Verify

```bash
kubectl -n ollama get pods
kubectl -n ollama logs deploy/ollama | tail
kubectl -n ollama exec deploy/ollama -- ollama list   # see installed models
kubectl -n ollama exec deploy/ollama -- nvidia-smi    # confirm GPU is bound
```

End-to-end test from another pod or a port-forward:

```bash
kubectl -n ollama port-forward svc/ollama 11434:11434 &
curl http://localhost:11434/api/generate -d '{
  "model": "qwen3:8b",
  "prompt": "Say hello in three words.",
  "stream": false
}'
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Pod `Pending` with `0/4 nodes are available: 3 didn't match Pod's node affinity, 1 Insufficient nvidia.com/gpu` | Another GPU pod is holding `nvidia.com/gpu: 1`. Scale it down or wait. |
| `CUDA out of memory` in logs | Context length × KV cache too big. Drop `OLLAMA_CONTEXT_LENGTH` or switch to `q4_0`. |
| First boot takes >15 min | Model download is slow over the home connection. Check `kubectl logs` — look for `pulling manifest`. |
| Model pulled but inference hangs | GPU isn't actually attached. `kubectl exec ... -- nvidia-smi` to verify. |
