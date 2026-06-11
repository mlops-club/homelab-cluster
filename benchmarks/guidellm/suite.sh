#!/bin/bash
# Suite of GuideLLM benchmark scenarios against the in-cluster Ollama service.
# Run inside the guidellm-bench pod via the configmap mount at /scripts/suite.sh.
#
# Each scenario writes a JSON result to /work/<scenario>.json. The driver
# script (run-suite.sh) kubectl-cp's /work out after the pod reports DONE.

set -euo pipefail

TARGET="http://ollama.ollama.svc.cluster.local:11434"
COMMON_ARGS=(
    --target "${TARGET}"
    --backend-kwargs '{"validate_backend": false}'
    --request-type chat_completions
    --processor Qwen/Qwen3-8B
    --profile synchronous
    --warmup 0
    --cooldown 0
    --disable-progress
)

run_scenario() {
    local name="$1"
    local model="$2"
    local prompt_tokens="$3"
    local output_tokens="$4"
    local max_requests="$5"
    local out="/work/${name}.json"

    echo "=== scenario: ${name} | model=${model} prompt=${prompt_tokens} output=${output_tokens} n=${max_requests} ==="
    guidellm benchmark run \
        "${COMMON_ARGS[@]}" \
        --model "${model}" \
        --data "prompt_tokens=${prompt_tokens},output_tokens=${output_tokens}" \
        --max-requests "${max_requests}" \
        --output-path "${out}" 2>&1 | tail -5
    echo "wrote ${out} ($(wc -c < "${out}") bytes)"
}

# Scenario matrix. Sized to finish in ~20 minutes total against qwen3:8b on
# a single RTX 5080 with NUM_PARALLEL=1. Sync profile because Ollama
# serializes requests anyway with that setting.
#
# Note: qwen3 has thinking mode ON by default, so actual output token
# counts will exceed `output_tokens` (the requested cap). The report
# explains this; the comparison is still useful for relative latency.

run_scenario short-chat       qwen3:8b      256   128  20
run_scenario medium-prompt    qwen3:8b     1024   256  15
run_scenario long-prompt-40k  qwen3:8b     4096   256  10
run_scenario long-prompt-128k qwen3:8b-128k 8192  256   8

echo "=== suite complete ==="
ls -la /work/*.json
