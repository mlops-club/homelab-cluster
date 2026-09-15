# Prefix-cache probe

A custom benchmark that measures Ollama's **KV cache reuse for repeated prompt prefixes**, captured directly from Ollama's native API metrics rather than from GuideLLM's streaming-aware view.

## Why this is a separate tool from `benchmarks/guidellm/`

GuideLLM measures **TTFT** (time to first token) from the client's perspective. That includes:
1. HTTP roundtrip
2. Server queue time
3. Ollama's actual prefill compute
4. Ollama's streaming chunk-batching delay before flushing the first token

The v1 GuideLLM run found a ~4-5 s TTFT floor on *every* scenario regardless of prompt length — i.e., (4) dominates and (3) gets buried. So even if prefix caching cuts prefill from 150 ms to 8 ms, the user-visible TTFT change is invisible.

To actually measure cache hit/miss, you need Ollama's `prompt_eval_duration` field from `/api/generate`, which reports the literal time spent on prompt prefill. That's what this probe captures.

| Metric source | What it sees | Best for |
|---|---|---|
| GuideLLM TTFT | Client-visible time to first streamed token | User-experience latency, streaming SLOs |
| `prompt_eval_duration` | Ollama's actual prefill compute time | KV cache hit/miss analysis |

## How the experiment is structured

```
Axis 1: prompt length   {1024, 4096, 16384}      (3 levels)
Axis 2: prefix hit rate {0%, 25%, 50%, 75%, 100%} (5 levels)

= 15 scenarios × 8 requests each
```

For each scenario, all 8 requests share `hit_rate%` of their prompt tokens; the rest is a unique tail per request. The shared prefix is deterministic (md5-seeded), so re-running the probe is reproducible.

Each request also starts with `/no_think` to suppress qwen3's reasoning block — we want clean prefill numbers, not thinking-mode noise. `num_predict=32` keeps decode short for the same reason; we're measuring prefill, not decode throughput.

### What we expect to see

- **First request in each scenario** = cold cache. `prompt_eval_duration` reflects the full prefill compute cost for the prompt size.
- **Requests 2+ at hit_rate=100%** = identical prompt to request 1. Cache should hit for the entire prompt; `prompt_eval_duration` should drop to ~0.
- **Requests 2+ at hit_rate=0%** = each prompt completely different from the previous. Cache should miss; `prompt_eval_duration` stays near the cold value.
- **Requests 2+ at hit_rate=50%** = first half cached, second half fresh. `prompt_eval_duration` should be ~half the cold value.

The bench captures this as a cleanly interpretable curve.

## How to run

```bash
./run.sh             # ~5-10 min total against qwen3:8b
uv run plot.py out/results.json    # generates 4 figures
```

`run.sh` bundles `probe.py` into a ConfigMap, launches the Job, tails logs until `DONE`, and `kubectl cp`'s `out/results.json` back. `plot.py` reads that JSON and writes figures into `../reports/figures/prefix-cache/` (or `figures/` next to results.json if invoked directly).

## Output files

- `out/results.json` — per-scenario per-request native metrics
- `figures/01-cold-vs-warm.png` — bar chart: first request vs warm-cache median, faceted by prompt length
- `figures/02-speedup-heatmap.png` — prompt_length × hit_rate → speedup factor heatmap
- `figures/03-prefill-over-requests.png` — per-request prefill ms over the 8-request sequence, one line per hit rate
- `figures/04-warm-anatomy.png` — warm-state breakdown of prefill vs decode per scenario
