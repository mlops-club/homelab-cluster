#!/bin/bash
# Run the GuideLLM benchmark suite against the in-cluster Ollama service.
#   - Bundles benchmarks/guidellm/suite.sh into a ConfigMap.
#   - Launches the Job from benchmarks/guidellm/job.yaml.
#   - Waits for the suite to print DONE.
#   - kubectl cp's the per-scenario JSON outputs into ./out/.
#   - Cleans up the Job + ConfigMap.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NAMESPACE="default"
JOB_NAME="guidellm-bench"
CM_NAME="guidellm-suite-script"
OUT_DIR="${SCRIPT_DIR}/out"

cleanup() {
    kubectl -n "${NAMESPACE}" delete job "${JOB_NAME}" --ignore-not-found --wait=false >/dev/null 2>&1 || true
    kubectl -n "${NAMESPACE}" delete configmap "${CM_NAME}" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
mkdir -p "${OUT_DIR}"

echo "Creating ConfigMap with suite script..."
kubectl -n "${NAMESPACE}" create configmap "${CM_NAME}" \
    --from-file=suite.sh="${SCRIPT_DIR}/suite.sh"

echo "Launching benchmark Job..."
kubectl -n "${NAMESPACE}" apply -f "${SCRIPT_DIR}/job.yaml"

echo "Waiting for pod to be Running..."
until [ "$(kubectl -n "${NAMESPACE}" get pods -l job-name="${JOB_NAME}" -o jsonpath='{.items[0].status.phase}' 2>/dev/null)" = "Running" ]; do
    sleep 3
done
POD="$(kubectl -n "${NAMESPACE}" get pods -l job-name="${JOB_NAME}" -o jsonpath='{.items[0].metadata.name}')"
echo "Pod is ${POD}; streaming logs until 'DONE'..."

# Stream logs until we see DONE, then break (don't wait for the 30-min sleep).
kubectl -n "${NAMESPACE}" logs -f "${POD}" | while IFS= read -r line; do
    echo "  ${line}"
    case "${line}" in
        *"DONE -- sleeping for retrieval"*) pkill -P $$ kubectl 2>/dev/null; break ;;
    esac
done

echo "Copying /work out of pod..."
kubectl -n "${NAMESPACE}" cp "${POD}:/work" "${OUT_DIR}" 2>&1 | tail -5
ls -la "${OUT_DIR}"/*.json 2>/dev/null || { echo "ERROR: no JSON results retrieved"; exit 1; }

echo "Done. Run ./summarize.py ./out to generate a Markdown report."
