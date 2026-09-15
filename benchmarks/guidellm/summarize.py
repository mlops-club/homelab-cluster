#!/usr/bin/env python3
"""
Summarize a GuideLLM benchmark suite into a single Markdown report.

Reads every *.json file in the given directory (one per scenario),
extracts the key latency/throughput metrics, and writes a Markdown
report comparing them.

Usage:
    summarize.py <results_dir> [--out <report.md>]
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


def load_benchmark(path: Path) -> dict:
    with path.open() as f:
        data = json.load(f)
    benchmarks = data.get("benchmarks", [])
    if not benchmarks:
        raise ValueError(f"{path}: no benchmarks block")
    return benchmarks[0]


def stat(metric: dict, kind: str, key: str) -> float | None:
    """Pull a single statistic out of a guidellm metric block.
    `key` can be a top-level field (mean, median, ...) or a percentile (p95, p99, ...).
    """
    block = metric.get(kind, {})
    if not block:
        return None
    if key.startswith("p") and key not in block:
        return (block.get("percentiles") or {}).get(key)
    return block.get(key)


def fmt_ms(v):
    return "—" if v is None else f"{v:,.1f}"


def fmt_int(v):
    return "—" if v is None else f"{v:,.0f}"


def fmt_float(v, n=2):
    return "—" if v is None else f"{v:,.{n}f}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("results_dir", type=Path)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    if not args.results_dir.is_dir():
        sys.exit(f"not a directory: {args.results_dir}")

    json_files = sorted(args.results_dir.glob("*.json"))
    if not json_files:
        sys.exit(f"no *.json found in {args.results_dir}")

    rows = []
    for jf in json_files:
        try:
            b = load_benchmark(jf)
        except Exception as exc:
            print(f"warn: {jf.name}: {exc}", file=sys.stderr)
            continue
        cfg = b.get("config", {})
        model = (cfg.get("backend", {}) or {}).get("model") or "?"
        m = b.get("metrics", {})
        rt = m.get("request_totals", {})

        rows.append({
            "scenario": jf.stem,
            "model": model,
            "n_total": rt.get("total"),
            "n_ok": rt.get("successful"),
            "n_err": rt.get("errored"),
            "duration_s": b.get("duration"),
            "prompt_tok_median": stat(m.get("prompt_token_count", {}), "successful", "median"),
            "output_tok_median": stat(m.get("output_token_count", {}), "successful", "median"),
            "output_tok_p95": stat(m.get("output_token_count", {}), "successful", "p95"),
            "ttft_ms_median": stat(m.get("time_to_first_token_ms", {}), "successful", "median"),
            "ttft_ms_p95": stat(m.get("time_to_first_token_ms", {}), "successful", "p95"),
            "tpot_ms_median": stat(m.get("time_per_output_token_ms", {}), "successful", "median"),
            "tpot_ms_p95": stat(m.get("time_per_output_token_ms", {}), "successful", "p95"),
            "itl_ms_median": stat(m.get("inter_token_latency_ms", {}), "successful", "median"),
            "latency_s_median": stat(m.get("request_latency", {}), "successful", "median"),
            "latency_s_p95": stat(m.get("request_latency", {}), "successful", "p95"),
            "rps": stat(m.get("requests_per_second", {}), "successful", "mean"),
            "out_tps": stat(m.get("output_token_count", {}), "successful", "rate_mean")
                       or stat(m.get("output_token_count_per_second", {}), "successful", "mean"),
        })

    today = dt.date.today().isoformat()
    # ./benchmarks/guidellm/out → ./benchmarks/reports
    default_reports = args.results_dir.resolve().parent.parent / "reports"
    out_path = args.out or default_reports / f"{today}-qwen3-8b.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    md = []
    md.append(f"# Qwen3 8B on RTX 5080 — GuideLLM benchmark ({today})")
    md.append("")
    md.append("**Server**: Ollama 0.30.6, single replica, cluster-node-4 (RTX 5080, 16 GB VRAM)")
    md.append("**Client**: GuideLLM 0.6.0 in-cluster pod, synchronous profile (1 request at a time)")
    md.append(f"**Scenarios**: {len(rows)} runs, ~{sum((r['duration_s'] or 0) for r in rows):.0f} s total benchmark time")
    md.append("")
    md.append("## Caveats")
    md.append("")
    md.append("- **Qwen3 thinking mode is on by default** — the model emits a long `<think>` block before its actual answer. Observed median output tokens (~900) are much higher than the requested cap (`output_tokens=128/256`). TPOT/throughput are the right metrics to compare across scenarios; raw latency is dominated by output length.")
    md.append("- **Synchronous profile**: one request at a time. The Ollama deploy uses `OLLAMA_NUM_PARALLEL=1` on the 16 GB VRAM budget, so concurrent benchmarks would just queue — measured RPS equals 1/median-latency.")
    md.append("- **First request in each scenario eats a cold-load cost** if Ollama unloaded the model between scenarios. With `OLLAMA_KEEP_ALIVE=24h` this is usually only for the very first scenario.")
    md.append("")
    figures_dir = out_path.parent / "figures"
    cross_fig = figures_dir / "00-cross-scenario.png"
    if cross_fig.exists():
        rel = cross_fig.relative_to(out_path.parent)
        md.append("## Cross-scenario comparison")
        md.append("")
        md.append(f"![Cross-scenario comparison]({rel})")
        md.append("")
        md.append("See `../EXPERIMENT_DESIGN.md` for narrative interpretation of these figures.")
        md.append("")
    md.append("## Summary table")
    md.append("")
    md.append("| Scenario | Model | n (ok/total) | Prompt tok (med) | Output tok (med / p95) | Latency (s med / p95) | TTFT (ms med / p95) | TPOT (ms med / p95) | RPS (mean) |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        md.append(
            f"| {r['scenario']} | `{r['model']}` "
            f"| {fmt_int(r['n_ok'])}/{fmt_int(r['n_total'])} "
            f"| {fmt_int(r['prompt_tok_median'])} "
            f"| {fmt_int(r['output_tok_median'])} / {fmt_int(r['output_tok_p95'])} "
            f"| {fmt_float(r['latency_s_median'], 2)} / {fmt_float(r['latency_s_p95'], 2)} "
            f"| {fmt_ms(r['ttft_ms_median'])} / {fmt_ms(r['ttft_ms_p95'])} "
            f"| {fmt_ms(r['tpot_ms_median'])} / {fmt_ms(r['tpot_ms_p95'])} "
            f"| {fmt_float(r['rps'], 3)} |"
        )
    md.append("")
    md.append("## Per-scenario raw JSON")
    md.append("")
    for jf in json_files:
        md.append(f"- `{jf.name}` ({jf.stat().st_size:,} bytes)")
    md.append("")
    md.append("---")
    md.append("")
    md.append("_Generated by `benchmarks/guidellm/summarize.py`._")

    out_path.write_text("\n".join(md))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
