#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib>=3.9",
#     "numpy>=2.0",
# ]
# ///
"""
Plot the prefix-cache probe results.

Reads probe.py's results.json and produces figures showing how
prompt_eval_duration depends on prefix hit rate and prompt length.

Usage:
    uv run plot.py <results.json> [--out <figures_dir>]
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


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def per_request_arrays(scenario: dict) -> dict:
    reqs = scenario["requests"]
    return {
        "idx": np.arange(1, len(reqs) + 1),
        "wall_ms": np.array([r["wall_total_ms"] for r in reqs]),
        "prefill_ms": np.array([r["prompt_eval_duration_ms"] for r in reqs]),
        "decode_ms": np.array([r["eval_duration_ms"] for r in reqs]),
        "load_ms": np.array([r["load_duration_ms"] for r in reqs]),
        "prompt_eval_count": np.array([r["prompt_eval_count"] for r in reqs]),
        "eval_count": np.array([r["eval_count"] for r in reqs]),
    }


def by_prompt_length(scenarios: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for s in scenarios:
        out.setdefault(s["prompt_length_target"], []).append(s)
    return out


def plot_first_vs_repeat(scenarios, out_dir):
    """Show first-request prefill vs warm-cache median for each scenario."""
    by_len = by_prompt_length(scenarios)
    prompt_lens = sorted(by_len.keys())
    hit_rates = sorted(by_len[prompt_lens[0]], key=lambda s: s["hit_rate_pct"])
    hit_rate_labels = [s["hit_rate_pct"] for s in hit_rates]

    fig, axes = plt.subplots(1, len(prompt_lens), figsize=(5 * len(prompt_lens), 4.5), sharey=True)
    if len(prompt_lens) == 1:
        axes = [axes]

    for ax, plen in zip(axes, prompt_lens):
        ordered = sorted(by_len[plen], key=lambda s: s["hit_rate_pct"])
        first_ms = []
        warm_med_ms = []
        for s in ordered:
            a = per_request_arrays(s)
            first_ms.append(a["prefill_ms"][0])
            if len(a["prefill_ms"]) > 1:
                warm_med_ms.append(float(np.median(a["prefill_ms"][1:])))
            else:
                warm_med_ms.append(float("nan"))

        x = np.arange(len(hit_rate_labels))
        w = 0.4
        ax.bar(x - w / 2, first_ms, w, color="#EE6677", label="First request (cold)")
        ax.bar(x + w / 2, warm_med_ms, w, color="#228833", label="Median of req 2..N (warm)")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{h}%" for h in hit_rate_labels])
        ax.set_xlabel("Prefix hit rate (% of prompt shared across requests)")
        ax.set_ylabel("Prefill duration (ms)")
        ax.set_title(f"~{plen:,} prompt tokens")
        ax.legend(fontsize=8)

    fig.suptitle("Ollama prefill duration — first request vs warm cache", y=1.02, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_dir / "01-cold-vs-warm.png")
    plt.close(fig)


def plot_speedup_heatmap(scenarios, out_dir):
    """Heatmap: speedup factor (cold/warm) for each (prompt_length, hit_rate)."""
    by_len = by_prompt_length(scenarios)
    prompt_lens = sorted(by_len.keys())
    hit_rates = sorted({s["hit_rate_pct"] for s in scenarios})

    grid = np.zeros((len(prompt_lens), len(hit_rates)))
    for i, plen in enumerate(prompt_lens):
        for j, hr in enumerate(hit_rates):
            s = next((s for s in by_len[plen] if s["hit_rate_pct"] == hr), None)
            if s is None:
                grid[i, j] = np.nan
                continue
            a = per_request_arrays(s)
            cold = a["prefill_ms"][0]
            warm = float(np.median(a["prefill_ms"][1:])) if len(a["prefill_ms"]) > 1 else cold
            grid[i, j] = cold / max(warm, 1e-3)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    im = ax.imshow(grid, aspect="auto", cmap="viridis", vmin=1.0)
    ax.set_xticks(range(len(hit_rates)))
    ax.set_xticklabels([f"{h}%" for h in hit_rates])
    ax.set_yticks(range(len(prompt_lens)))
    ax.set_yticklabels([f"{p:,}" for p in prompt_lens])
    ax.set_xlabel("Prefix hit rate")
    ax.set_ylabel("Prompt tokens")
    ax.set_title("Prefill speedup factor (cold / warm-median)")
    for i in range(len(prompt_lens)):
        for j in range(len(hit_rates)):
            v = grid[i, j]
            label = f"{v:.1f}×" if not np.isnan(v) else "—"
            color = "white" if v < grid.max() * 0.6 else "black"
            ax.text(j, i, label, ha="center", va="center", color=color, fontsize=11)
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Speedup factor (×)")
    fig.savefig(out_dir / "02-speedup-heatmap.png")
    plt.close(fig)


def plot_prefill_over_requests(scenarios, out_dir):
    """For each prompt length, plot per-request prefill ms vs request index, one line per hit rate."""
    by_len = by_prompt_length(scenarios)
    prompt_lens = sorted(by_len.keys())

    fig, axes = plt.subplots(1, len(prompt_lens), figsize=(5 * len(prompt_lens), 4), sharey=False)
    if len(prompt_lens) == 1:
        axes = [axes]

    colors = ["#EE6677", "#CCBB44", "#228833", "#4477AA", "#AA3377"]

    for ax, plen in zip(axes, prompt_lens):
        ordered = sorted(by_len[plen], key=lambda s: s["hit_rate_pct"])
        for s, c in zip(ordered, colors):
            a = per_request_arrays(s)
            ax.plot(a["idx"], a["prefill_ms"], marker="o", color=c, label=f"hit {s['hit_rate_pct']}%", linewidth=1.5)
        ax.set_xlabel("Request #")
        ax.set_ylabel("Prefill duration (ms)")
        ax.set_title(f"~{plen:,} prompt tokens")
        ax.set_yscale("log")
        ax.legend(fontsize=8)

    fig.suptitle("Prefill cost over request order — cache warms after request 1", y=1.02, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_dir / "03-prefill-over-requests.png")
    plt.close(fig)


def plot_anatomy_breakdown(scenarios, out_dir):
    """Stacked bars showing load / prefill / decode for the warm-state median per scenario."""
    ordered = sorted(scenarios, key=lambda s: (s["prompt_length_target"], s["hit_rate_pct"]))
    labels = [f"{s['prompt_length_target']//1024}K · hit {s['hit_rate_pct']}%" for s in ordered]
    prefill = []
    decode = []
    for s in ordered:
        a = per_request_arrays(s)
        warm_p = float(np.median(a["prefill_ms"][1:])) if len(a["prefill_ms"]) > 1 else float(a["prefill_ms"][0])
        warm_d = float(np.median(a["decode_ms"][1:])) if len(a["decode_ms"]) > 1 else float(a["decode_ms"][0])
        prefill.append(warm_p)
        decode.append(warm_d)

    fig, ax = plt.subplots(figsize=(max(8, len(ordered) * 0.6), 4.5))
    x = np.arange(len(ordered))
    ax.bar(x, prefill, color="#EE6677", label="Prefill")
    ax.bar(x, decode, bottom=prefill, color="#4477AA", label="Decode")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Warm-state median duration (ms)")
    ax.set_title("Warm-state anatomy — prefill vs decode")
    ax.legend()
    fig.savefig(out_dir / "04-warm-anatomy.png")
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("results", type=Path)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    data = load(args.results)
    scenarios = data["scenarios"]
    if not scenarios:
        raise SystemExit("no scenarios in results")

    out_dir = args.out or args.results.resolve().parent.parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    plot_first_vs_repeat(scenarios, out_dir)
    plot_speedup_heatmap(scenarios, out_dir)
    plot_prefill_over_requests(scenarios, out_dir)
    plot_anatomy_breakdown(scenarios, out_dir)
    print(f"wrote 4 figures → {out_dir}")


if __name__ == "__main__":
    main()
