#!/usr/bin/env python3
"""
Prefix-cache prefill benchmark for Ollama.

Generates prompts with controlled prefix overlap and hits Ollama's
/api/generate endpoint directly so we can capture native metrics:

  - prompt_eval_count     total prompt tokens (constant for fixed prompt size)
  - prompt_eval_duration  ACTUAL prefill compute time — drops on a cache hit
  - eval_count, eval_duration  decode side
  - total_duration        end-to-end

GuideLLM can't see these — it only sees the streaming TTFT, which is
dominated by Ollama's chunk-batching floor and hides the prefill speedup.

Usage:
    python3 probe.py --target http://ollama:11434 --out /tmp/results.json \
        --prompt-lengths 1024,4096,16384 \
        --hit-rates 0,25,50,75,100 \
        --num-prompts 8
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import httpx
from transformers import AutoTokenizer


LOREM_SEED = (
    "The quick brown fox jumps over the lazy dog. "
    "Pack my box with five dozen liquor jugs. "
    "How vexingly quick daft zebras jump. "
    "Sphinx of black quartz, judge my vow. "
    "The five boxing wizards jump quickly. "
)
PROMPT_FRAME_PREFIX = (
    "/no_think Read the following background passage carefully, then answer "
    "the question at the end.\n\nBackground:\n"
)
PROMPT_FRAME_SUFFIX = "\n\nQuestion: Summarize the passage in one sentence."


def make_token_text(tokenizer, n_tokens: int, seed: int) -> str:
    """Generate text whose tokenization is approximately n_tokens long."""
    if n_tokens <= 0:
        return ""
    rng = random.Random(seed)
    sentences = LOREM_SEED.split(". ")
    parts: list[str] = []
    while True:
        chunk = " ".join(rng.choices(sentences, k=20))
        parts.append(chunk + ". ")
        text = " ".join(parts)
        ids = tokenizer.encode(text, add_special_tokens=False)
        if len(ids) >= n_tokens:
            return tokenizer.decode(ids[:n_tokens], skip_special_tokens=True)


def build_prompts(
    tokenizer,
    prompt_len: int,
    hit_rate_pct: int,
    n_prompts: int,
) -> list[str]:
    """Build N prompts where the first hit_rate_pct% of tokens are identical."""
    shared_tokens = prompt_len * hit_rate_pct // 100
    tail_tokens = prompt_len - shared_tokens
    seed = int(hashlib.md5(f"{prompt_len}-{hit_rate_pct}".encode()).hexdigest()[:8], 16)
    shared_text = make_token_text(tokenizer, shared_tokens, seed=seed)
    prompts = []
    for i in range(n_prompts):
        tail_text = make_token_text(tokenizer, tail_tokens, seed=seed + 1 + i)
        prompts.append(PROMPT_FRAME_PREFIX + shared_text + tail_text + PROMPT_FRAME_SUFFIX)
    return prompts


def run_scenario(
    client: httpx.Client,
    target: str,
    model: str,
    prompts: list[str],
    num_predict: int,
) -> list[dict]:
    """Send each prompt to /api/generate and capture native metrics per request."""
    results = []
    for i, prompt in enumerate(prompts):
        t0 = time.time()
        r = client.post(
            f"{target}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": num_predict, "temperature": 0.0},
            },
        )
        elapsed_ms = (time.time() - t0) * 1000.0
        d = r.json()
        results.append({
            "request_index": i,
            "wall_total_ms": elapsed_ms,
            "prompt_eval_count": d.get("prompt_eval_count"),
            "prompt_eval_duration_ms": (d.get("prompt_eval_duration") or 0) / 1e6,
            "eval_count": d.get("eval_count"),
            "eval_duration_ms": (d.get("eval_duration") or 0) / 1e6,
            "total_duration_ms": (d.get("total_duration") or 0) / 1e6,
            "load_duration_ms": (d.get("load_duration") or 0) / 1e6,
        })
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True)
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--tokenizer", default="Qwen/Qwen3-8B")
    p.add_argument("--prompt-lengths", default="1024,4096,16384")
    p.add_argument("--hit-rates", default="0,25,50,75,100")
    p.add_argument("--num-prompts", type=int, default=8)
    p.add_argument("--num-predict", type=int, default=32,
                   help="Tokens to generate per request. Keep small — we're measuring prefill, not decode.")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--warmup", action="store_true",
                   help="Send one warm-up request before each scenario to factor out model load.")
    args = p.parse_args()

    print(f"Loading tokenizer {args.tokenizer}...")
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer)

    prompt_lengths = [int(x) for x in args.prompt_lengths.split(",")]
    hit_rates = [int(x) for x in args.hit_rates.split(",")]

    all_results: list[dict] = []
    total_scenarios = len(prompt_lengths) * len(hit_rates)
    n = 0

    with httpx.Client(timeout=300.0) as client:
        if args.warmup:
            print("Initial warmup...")
            client.post(
                f"{args.target}/api/generate",
                json={"model": args.model, "prompt": "/no_think Hi", "stream": False,
                      "options": {"num_predict": 1}},
            )

        for prompt_len in prompt_lengths:
            for hit_rate in hit_rates:
                n += 1
                scenario = f"p{prompt_len}-hit{hit_rate}"
                print(f"[{n}/{total_scenarios}] {scenario}: building {args.num_prompts} prompts (shared={prompt_len*hit_rate//100} tokens)...")
                prompts = build_prompts(tokenizer, prompt_len, hit_rate, args.num_prompts)
                t0 = time.time()
                rows = run_scenario(client, args.target, args.model, prompts, args.num_predict)
                dt = time.time() - t0
                all_results.append({
                    "scenario": scenario,
                    "prompt_length_target": prompt_len,
                    "hit_rate_pct": hit_rate,
                    "num_prompts": args.num_prompts,
                    "num_predict": args.num_predict,
                    "wall_total_s": dt,
                    "requests": rows,
                })
                med_prefill = sorted(r["prompt_eval_duration_ms"] for r in rows[1:])[len(rows)//2 - 1] if len(rows) > 1 else rows[0]["prompt_eval_duration_ms"]
                print(f"  done in {dt:.1f}s; median prompt_eval_duration (req 2+): {med_prefill:.1f} ms")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "model": args.model,
        "target": args.target,
        "scenarios": all_results,
    }, indent=2))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
