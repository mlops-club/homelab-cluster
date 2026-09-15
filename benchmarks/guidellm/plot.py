#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib>=3.9",
#     "numpy>=2.0",
# ]
# ///
"""
Generate per-scenario diagnostic plots from GuideLLM JSON output.

Usage:
    uv run plot.py <results_dir> [--out <figures_dir>]

For each *.json in results_dir, writes a set of PNG plots into
figures_dir (default: <results_dir>/../../reports/figures/<scenario>/).
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "figure.dpi": 130,
    "savefig.dpi": 130,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
})


def load(path: Path) -> tuple[dict, dict]:
    """Return (top_level, first benchmark)."""
    with path.open() as f:
        top = json.load(f)
    return top, top["benchmarks"][0]


def per_request_arrays(b: dict) -> dict:
    """Extract per-request series for plotting; skip rows with missing key fields."""
    reqs = [
        r for r in b["requests"]["successful"]
        if r.get("time_to_first_token_ms") is not None
        and r.get("inter_token_latency_ms") is not None
        and r.get("output_tokens")
    ]
    a = {
        "start": np.array([r["request_start_time"] for r in reqs]),
        "latency_s": np.array([r["request_latency"] for r in reqs]),
        "prompt_tokens": np.array([r["prompt_tokens"] for r in reqs]),
        "output_tokens": np.array([r["output_tokens"] for r in reqs]),
        "ttft_ms": np.array([r["time_to_first_token_ms"] for r in reqs]),
        "tpot_ms": np.array([r["time_per_output_token_ms"] for r in reqs]),
        "itl_ms": np.array([r["inter_token_latency_ms"] for r in reqs]),
        "out_tps": np.array([r["output_tokens_per_second"] for r in reqs]),
    }
    a["t0"] = a["start"] - a["start"].min()
    a["n_kept"] = len(reqs)
    a["n_total"] = len(b["requests"]["successful"])
    return a


def pct(arr, p):
    return float(np.percentile(arr, p))


def plot_ttft_distribution(a, scenario, out: Path):
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(a["ttft_ms"], bins=12, color="#4477AA", edgecolor="white")
    for q, ls, label in [(50, "-", "median"), (95, "--", "p95")]:
        v = pct(a["ttft_ms"], q)
        ax.axvline(v, color="#EE6677", linestyle=ls, linewidth=1.5, label=f"{label}: {v:,.0f} ms")
    ax.set_xlabel("Time to first token (ms)")
    ax.set_ylabel("Request count")
    ax.set_title(f"{scenario} — TTFT distribution (prefill cost)")
    ax.legend()
    fig.savefig(out / "01-ttft-histogram.png")
    plt.close(fig)


def plot_tpot_distribution(a, scenario, out: Path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))

    ax1.hist(a["tpot_ms"], bins=12, color="#228833", edgecolor="white")
    for q, ls, label in [(50, "-", "median"), (95, "--", "p95")]:
        v = pct(a["tpot_ms"], q)
        ax1.axvline(v, color="#EE6677", linestyle=ls, linewidth=1.5, label=f"{label}: {v:.2f} ms")
    ax1.set_xlabel("Time per output token (ms)")
    ax1.set_ylabel("Request count")
    ax1.set_title("TPOT (includes prefill amortization)")
    ax1.legend()

    ax2.hist(a["itl_ms"], bins=12, color="#CCBB44", edgecolor="white")
    for q, ls, label in [(50, "-", "median"), (95, "--", "p95")]:
        v = pct(a["itl_ms"], q)
        ax2.axvline(v, color="#EE6677", linestyle=ls, linewidth=1.5, label=f"{label}: {v:.2f} ms")
    ax2.set_xlabel("Inter-token latency (ms)")
    ax2.set_ylabel("Request count")
    ax2.set_title("ITL (decode-only)")
    ax2.legend()

    fig.suptitle(f"{scenario} — Decode speed", y=1.02, fontweight="bold")
    fig.savefig(out / "02-tpot-itl-histogram.png")
    plt.close(fig)


def plot_latency_over_time(a, scenario, out: Path):
    fig, ax1 = plt.subplots(figsize=(8, 4))
    order = np.arange(1, len(a["latency_s"]) + 1)
    ax1.plot(order, a["latency_s"], marker="o", color="#4477AA", label="End-to-end latency (s)")
    ax1.set_xlabel("Request #")
    ax1.set_ylabel("Latency (s)", color="#4477AA")
    ax1.tick_params(axis="y", labelcolor="#4477AA")

    ax2 = ax1.twinx()
    ax2.plot(order, a["ttft_ms"], marker="s", color="#EE6677", linestyle="--", label="TTFT (ms)")
    ax2.set_ylabel("TTFT (ms)", color="#EE6677")
    ax2.tick_params(axis="y", labelcolor="#EE6677")
    ax2.grid(False)

    ax1.set_title(f"{scenario} — Latency over request order (warmup signature)")
    fig.tight_layout()
    fig.savefig(out / "03-latency-over-time.png")
    plt.close(fig)


def plot_token_counts(a, scenario, requested_prompt, requested_output, out: Path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))

    ax1.hist(a["prompt_tokens"], bins=10, color="#66CCEE", edgecolor="white")
    ax1.axvline(requested_prompt, color="#EE6677", linewidth=2, label=f"Requested: {requested_prompt}")
    ax1.set_xlabel("Prompt tokens (actual)")
    ax1.set_ylabel("Request count")
    ax1.set_title("Prompt size — close to requested")
    ax1.legend()

    ax2.hist(a["output_tokens"], bins=10, color="#AA3377", edgecolor="white")
    ax2.axvline(requested_output, color="#EE6677", linewidth=2, label=f"Requested cap: {requested_output}")
    med = pct(a["output_tokens"], 50)
    ax2.axvline(med, color="#228833", linewidth=2, linestyle="--", label=f"Actual median: {med:.0f}")
    ax2.set_xlabel("Output tokens (actual)")
    ax2.set_ylabel("Request count")
    ax2.set_title("Output size — thinking mode blows past the cap")
    ax2.legend()

    fig.suptitle(f"{scenario} — Requested vs actual token counts", y=1.02, fontweight="bold")
    fig.savefig(out / "04-token-counts.png")
    plt.close(fig)


def plot_request_anatomy(a, scenario, out: Path):
    fig, ax = plt.subplots(figsize=(8, 4))
    order = np.arange(1, len(a["latency_s"]) + 1)

    prefill_s = a["ttft_ms"] / 1000.0
    decode_s = a["latency_s"] - prefill_s

    ax.bar(order, prefill_s, color="#EE6677", label="Prefill (until first token)")
    ax.bar(order, decode_s, bottom=prefill_s, color="#4477AA", label=f"Decode ({a['output_tokens'].mean():.0f} tok avg)")
    ax.set_xlabel("Request #")
    ax.set_ylabel("Time (s)")
    ax.set_title(f"{scenario} — Per-request anatomy: prefill vs decode")
    ax.legend(loc="upper right")
    fig.savefig(out / "05-request-anatomy.png")
    plt.close(fig)


def parse_requested(top_level: dict) -> tuple[int, int]:
    """Pull the requested prompt_tokens/output_tokens from the invocation args."""
    data_args = top_level.get("args", {}).get("data") or []
    # `--data "prompt_tokens=256,output_tokens=128"` shows up as ["prompt_tokens=256,output_tokens=128"]
    for s in data_args:
        try:
            parts = dict(part.split("=") for part in str(s).split(","))
            return int(parts.get("prompt_tokens", 0)), int(parts.get("output_tokens", 0))
        except Exception:
            continue
    return 0, 0


def plot_cross_scenario(scenarios: list[tuple[str, dict]], out: Path):
    """Compare TTFT / TPOT / output token distributions across scenarios."""
    # Deterministic order by prompt length
    ordered = sorted(scenarios, key=lambda x: x[1]["prompt_tokens"].mean())

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    # TTFT box plot
    ax = axes[0, 0]
    ax.boxplot(
        [a["ttft_ms"] / 1000.0 for _, a in ordered],
        labels=[name for name, _ in ordered],
        showfliers=True,
        widths=0.5,
        patch_artist=True,
        boxprops=dict(facecolor="#4477AA88", edgecolor="#4477AA"),
        medianprops=dict(color="#EE6677", linewidth=2),
    )
    ax.set_ylabel("TTFT (s)")
    ax.set_title("TTFT vs scenario — prefill cost")
    ax.tick_params(axis="x", rotation=20)

    # TPOT box plot
    ax = axes[0, 1]
    ax.boxplot(
        [a["tpot_ms"] for _, a in ordered],
        labels=[name for name, _ in ordered],
        showfliers=True,
        widths=0.5,
        patch_artist=True,
        boxprops=dict(facecolor="#22883388", edgecolor="#228833"),
        medianprops=dict(color="#EE6677", linewidth=2),
    )
    ax.set_ylabel("Time per output token (ms)")
    ax.set_title("TPOT vs scenario — decode cost")
    ax.tick_params(axis="x", rotation=20)

    # Output token counts (log scale to handle the 40K runaway tail)
    ax = axes[1, 0]
    ax.boxplot(
        [a["output_tokens"] for _, a in ordered],
        labels=[name for name, _ in ordered],
        showfliers=True,
        widths=0.5,
        patch_artist=True,
        boxprops=dict(facecolor="#AA337788", edgecolor="#AA3377"),
        medianprops=dict(color="#EE6677", linewidth=2),
    )
    ax.set_yscale("log")
    ax.set_ylabel("Output tokens (log scale)")
    ax.set_title("Output length vs scenario — runaway thinking shows in the tail")
    ax.tick_params(axis="x", rotation=20)

    # TTFT vs prompt length scatter
    ax = axes[1, 1]
    colors = ["#4477AA", "#66CCEE", "#CCBB44", "#EE6677"]
    for (name, a), c in zip(ordered, colors):
        ax.scatter(a["prompt_tokens"], a["ttft_ms"] / 1000.0, alpha=0.7, s=40, color=c, label=name)
    ax.set_xlabel("Prompt tokens (actual)")
    ax.set_ylabel("TTFT (s)")
    ax.set_xscale("log")
    ax.set_title("TTFT vs prompt length — prefill scaling")
    ax.legend(loc="upper left", fontsize=8)

    fig.suptitle("Cross-scenario comparison — qwen3:8b on RTX 5080", y=1.00, fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "00-cross-scenario.png")
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("results_dir", type=Path)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    json_files = sorted(args.results_dir.glob("*.json"))
    if not json_files:
        raise SystemExit(f"no *.json in {args.results_dir}")

    base_out = args.out or (args.results_dir.resolve().parent.parent / "reports" / "figures")
    cross_scenarios: list[tuple[str, dict]] = []

    for jf in json_files:
        top, b = load(jf)
        scenario = jf.stem
        out_dir = base_out / scenario
        out_dir.mkdir(parents=True, exist_ok=True)

        a = per_request_arrays(b)
        req_prompt, req_output = parse_requested(top)

        plot_ttft_distribution(a, scenario, out_dir)
        plot_tpot_distribution(a, scenario, out_dir)
        plot_latency_over_time(a, scenario, out_dir)
        plot_token_counts(a, scenario, req_prompt, req_output, out_dir)
        plot_request_anatomy(a, scenario, out_dir)

        cross_scenarios.append((scenario, a))
        print(f"wrote 5 plots for {scenario} → {out_dir.relative_to(args.results_dir.resolve().parent.parent.parent)}")

    if len(cross_scenarios) > 1:
        base_out.mkdir(parents=True, exist_ok=True)
        plot_cross_scenario(cross_scenarios, base_out)
        print(f"wrote cross-scenario comparison → {(base_out / '00-cross-scenario.png').relative_to(args.results_dir.resolve().parent.parent.parent)}")


if __name__ == "__main__":
    main()
