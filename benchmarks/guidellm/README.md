# GuideLLM benchmarks

In-cluster LLM inference benchmarks for the model serving stack, using [GuideLLM](https://github.com/vllm-project/guidellm) (vllm-project / Neural Magic).

## What this measures

For each scenario, GuideLLM sends a sequence of chat completions to Ollama (in-cluster service `http://ollama.ollama.svc.cluster.local:11434`) and records:

| Metric | Meaning |
|---|---|
| **TTFT** | Time-to-first-token (ms). Prefill cost — dominates short-output use cases like classification or routing. |
| **TPOT** | Time-per-output-token (ms). Decode cost. Lower = faster streaming, more tokens/s. |
| **ITL** | Inter-token latency (ms). TPOT minus prefill amortization — the actual gap between tokens during decode. |
| **Request latency** | End-to-end (s). |
| **RPS** | Requests per second (mean over the run). |

The current suite runs everything as **synchronous** (one request at a time). That's the realistic profile for this homelab: Ollama is deployed with `OLLAMA_NUM_PARALLEL=1` because the 16 GB RTX 5080 can't comfortably hold a second KV cache at full context. With NUM_PARALLEL=1, concurrent benchmarks would just queue — there's no information in a "concurrency=8" run that isn't in a sync run.

## Quickstart

```bash
./run-suite.sh                    # launches the Job, streams logs, copies out JSONs
./summarize.py out                # builds a Markdown report in ../reports/<date>-qwen3-8b.md
```

Total runtime is about 20 minutes for the default scenario set (one pod install + 4 scenarios sequenced).

## Files

| File | Purpose |
|---|---|
| `job.yaml` | The Kubernetes Job spec. Mounts `suite.sh` from a ConfigMap, installs `guidellm` in a `python:3.12-slim` pod, runs the suite, sleeps 30 min so the driver can `kubectl cp` results. |
| `suite.sh` | The scenario list. Each row calls `guidellm benchmark run` with a different `(model, prompt_tokens, output_tokens, n_requests)`. |
| `run-suite.sh` | Driver that bundles `suite.sh` into a ConfigMap, applies `job.yaml`, tails logs until `DONE`, copies `/work/*.json` into `./out/`. |
| `summarize.py` | Reads every JSON in `out/` and produces a Markdown report in `../reports/`. |

## Editing the scenario list

Open `suite.sh` and edit the `run_scenario` calls at the bottom:

```bash
run_scenario <name> <model> <prompt_tokens> <output_tokens> <n_requests>
```

Names show up as the scenario column in the report. Keep them short and stable across runs so diffs across reports are readable.

## Caveats baked into the design

- **Qwen3 thinking mode is on by default.** The model emits a long `<think>...</think>` block before its actual answer, so observed output token counts always exceed the requested cap. Affects raw latency but TPOT/throughput are still informative for comparing scenarios.
- **`--processor Qwen/Qwen3-8B`** is hardcoded — that's the HF repo id GuideLLM uses to count tokens. Change it if you're benchmarking a non-Qwen model.
- **`validate_backend: false`** is hardcoded in `--backend-kwargs`. Ollama doesn't expose `/health` which is what GuideLLM probes by default; skipping is harmless because the first real request would fail loudly if the endpoint were dead.

## Where reports go

`../reports/<YYYY-MM-DD>-qwen3-8b.md`. Reports are committed alongside the benchmark configuration — each commit captures both the scenarios and the numbers they produced.
