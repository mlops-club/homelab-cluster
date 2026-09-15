#!/bin/bash
# Run the prefix-cache probe against the in-cluster Ollama.
#   - Bundles probe.py into a ConfigMap.
#   - Applies job.yaml.
#   - Tails logs until 'DONE'.
#   - kubectl cp /work/results.json out into ./out/.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NAMESPACE="default"
JOB_NAME="prefix-cache-probe"
CM_NAME="prefix-cache-probe-script"
OUT_DIR="${SCRIPT_DIR}/out"

precleanup() {
    kubectl -n "${NAMESPACE}" delete job "${JOB_NAME}" --ignore-not-found --wait=false >/dev/null 2>&1 || true
    kubectl -n "${NAMESPACE}" delete configmap "${CM_NAME}" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
# postcleanup runs ONLY after we've successfully copied results out.
postcleanup() {
    kubectl -n "${NAMESPACE}" delete job "${JOB_NAME}" --ignore-not-found --wait=false >/dev/null 2>&1 || true
    kubectl -n "${NAMESPACE}" delete configmap "${CM_NAME}" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}

precleanup
mkdir -p "${OUT_DIR}"

echo "Creating ConfigMap with probe script..."
kubectl -n "${NAMESPACE}" create configmap "${CM_NAME}" \
    --from-file=probe.py="${SCRIPT_DIR}/probe.py"

echo "Launching probe Job..."
kubectl -n "${NAMESPACE}" apply -f "${SCRIPT_DIR}/job.yaml"

echo "Waiting for pod to be Running..."
until [ "$(kubectl -n "${NAMESPACE}" get pods -l job-name="${JOB_NAME}" -o jsonpath='{.items[0].status.phase}' 2>/dev/null)" = "Running" ]; do
    sleep 3
done
POD="$(kubectl -n "${NAMESPACE}" get pods -l job-name="${JOB_NAME}" -o jsonpath='{.items[0].metadata.name}')"
echo "Pod is ${POD}; streaming logs until 'DONE'..."

kubectl -n "${NAMESPACE}" logs -f "${POD}" | while IFS= read -r line; do
    echo "  ${line}"
    case "${line}" in
        *"DONE -- sleeping for retrieval"*) pkill -P $$ kubectl 2>/dev/null; break ;;
    esac
done

echo "Copying results out of pod..."
kubectl -n "${NAMESPACE}" cp "${POD}:/work/results.json" "${OUT_DIR}/results.json" 2>&1 | tail -3
ls -la "${OUT_DIR}/results.json"
postcleanup

echo "Done. Run ./plot.py out/results.json to generate figures."
