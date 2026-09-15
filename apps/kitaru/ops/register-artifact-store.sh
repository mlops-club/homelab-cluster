#!/usr/bin/env bash
# One-time operator script: register the MinIO-backed S3 artifact store in
# Kitaru/ZenML and switch the default stack to use it.
#
# Run this once after `apps/minio/deploy.sh` is green AND after the operator
# has done a `kitaru login`. Re-runs are safe: every step is upsert-style.
#
# What this script does (against the Tailnet-only Kitaru at
# https://kitaru.priv.mlops-club.org):
#   1. Reads the MinIO root credentials from the K8s `minio/minio-root` Secret.
#   2. Stores them as a ZenML secret named `minio-creds` in Kitaru so the
#      artifact store can reference them by name (avoids putting raw keys in
#      the artifact-store config and gives us a single rotation point).
#   3. Registers an S3 artifact store named `minio` with:
#        path        = s3://kitaru-artifacts
#        endpoint    = http://minio.minio.svc.cluster.local:9000
#        credentials = sourced from the `minio-creds` secret
#   4. Registers a new stack `default-s3` that pairs the existing local
#      orchestrator / deployer / log_store with the new `minio` artifact
#      store, and sets it active for the current user/workspace.
#
# We don't mutate the original `default` stack — leaving it in place means
# the old executions whose runs reference artifact-store ID
# 4cedd832-... still resolve a valid component (they still won't be
# log-fetchable, but they won't 404 either, and the operator can `kitaru
# stack use default` to roll back).
#
# After this script, the Kitaru UI's per-execution logs page works for any
# execution submitted with the `default-s3` stack active.

set -euo pipefail

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
KITARU_URL="${KITARU_URL:-https://kitaru.priv.mlops-club.org}"
ARTIFACT_STORE_NAME="${ARTIFACT_STORE_NAME:-minio}"
STACK_NAME="${STACK_NAME:-default-s3}"
KITARU_SECRET_NAME="${KITARU_SECRET_NAME:-minio-creds}"
BUCKET_NAME="${BUCKET_NAME:-kitaru-artifacts}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio.minio.svc.cluster.local:9000}"
MINIO_NAMESPACE="${MINIO_NAMESPACE:-minio}"

ZENML=(uvx --from "kitaru[local]" zenml)
KITARU=(uvx --from "kitaru[local]" kitaru)

log() { printf '\033[1;36m[register]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

# -----------------------------------------------------------------------------
# 1. Sanity
# -----------------------------------------------------------------------------
log "Step 1/5: sanity checks"
command -v uvx >/dev/null 2>&1 || die "uvx not found (install uv: https://docs.astral.sh/uv/)"
command -v kubectl >/dev/null 2>&1 || die "kubectl not found"

# Make sure we're logged in to Kitaru — we'll be writing secrets & stacks.
if ! "${KITARU[@]}" status >/dev/null 2>&1; then
    die "Kitaru CLI not logged in. Run: kitaru login ${KITARU_URL}"
fi
ok "kitaru CLI logged in to ${KITARU_URL}"

if ! kubectl -n "${MINIO_NAMESPACE}" get secret minio-root >/dev/null 2>&1; then
    die "K8s Secret ${MINIO_NAMESPACE}/minio-root not found. Run apps/minio/deploy.sh first."
fi
ok "K8s Secret ${MINIO_NAMESPACE}/minio-root present"

# -----------------------------------------------------------------------------
# 2. Pull MinIO creds out of K8s and plant them in Kitaru as a ZenML secret.
# -----------------------------------------------------------------------------
log "Step 2/5: mirror MinIO creds into ZenML secret '${KITARU_SECRET_NAME}'"

MINIO_ACCESS_KEY="$(
    kubectl -n "${MINIO_NAMESPACE}" get secret minio-root \
        -o jsonpath='{.data.rootUser}' | base64 -d
)"
MINIO_SECRET_KEY="$(
    kubectl -n "${MINIO_NAMESPACE}" get secret minio-root \
        -o jsonpath='{.data.rootPassword}' | base64 -d
)"

if [[ -z "${MINIO_ACCESS_KEY}" || -z "${MINIO_SECRET_KEY}" ]]; then
    die "Empty MinIO credentials in K8s Secret minio/minio-root."
fi

# ZenML's `secret create` errors on collision; `secret update` errors if
# missing. We try create first, fall back to update so re-runs work even
# when the secret already exists.
SECRET_VALUES=(
    "--aws_access_key_id=${MINIO_ACCESS_KEY}"
    "--aws_secret_access_key=${MINIO_SECRET_KEY}"
)
if "${ZENML[@]}" secret create "${KITARU_SECRET_NAME}" "${SECRET_VALUES[@]}" >/dev/null 2>&1; then
    ok "created ZenML secret '${KITARU_SECRET_NAME}'"
else
    "${ZENML[@]}" secret update "${KITARU_SECRET_NAME}" "${SECRET_VALUES[@]}" >/dev/null \
        || die "Failed to create or update ZenML secret '${KITARU_SECRET_NAME}'."
    ok "updated ZenML secret '${KITARU_SECRET_NAME}'"
fi

unset MINIO_ACCESS_KEY MINIO_SECRET_KEY SECRET_VALUES

# -----------------------------------------------------------------------------
# 3. Register the S3 artifact store (or update if it already exists).
# -----------------------------------------------------------------------------
log "Step 3/5: register S3 artifact store '${ARTIFACT_STORE_NAME}'"

CLIENT_KWARGS_JSON='{"endpoint_url": "'"${MINIO_ENDPOINT}"'"}'

# We point `key` and `secret` at the named ZenML secret using the
# `{{secret_name.key}}` reference syntax that ZenML expands at runtime.
# That way the artifact-store config itself never contains the raw key.
#
# IMPORTANT: the s3 flavor's config attribute is literally named `secret`,
# which collides with the `--secret` CLI option (which means "attach a named
# secret to the component"). Use `--` to terminate option parsing so the
# trailing `--secret=...` is treated as a positional config attribute.
ZENML_ARGS_COMMON=(
    "--path=s3://${BUCKET_NAME}"
    "--key={{${KITARU_SECRET_NAME}.aws_access_key_id}}"
    "--client_kwargs=${CLIENT_KWARGS_JSON}"
    "--"
    "--secret={{${KITARU_SECRET_NAME}.aws_secret_access_key}}"
)

if "${ZENML[@]}" artifact-store register "${ARTIFACT_STORE_NAME}" \
        --flavor=s3 \
        "${ZENML_ARGS_COMMON[@]}" >/dev/null 2>&1; then
    ok "registered artifact store '${ARTIFACT_STORE_NAME}'"
else
    # Already exists — update it so re-runs converge.
    "${ZENML[@]}" artifact-store update "${ARTIFACT_STORE_NAME}" \
        "${ZENML_ARGS_COMMON[@]}" >/dev/null \
        || die "Failed to register or update artifact store '${ARTIFACT_STORE_NAME}'."
    ok "updated artifact store '${ARTIFACT_STORE_NAME}'"
fi

# -----------------------------------------------------------------------------
# 4. Register a new stack that bundles the existing local orchestrator +
#    log_store + deployer with the new S3 artifact store, and activate it.
# -----------------------------------------------------------------------------
log "Step 4/5: register stack '${STACK_NAME}' and set active"

# The Kitaru `default` stack ships with a local orchestrator named `default`,
# a local deployer named `default`, and an implicit log_store (no explicit
# component — it falls through to the artifact-store path on the
# log_store=artifact-store back-end). We pair them with our new s3 store.
if "${ZENML[@]}" stack register "${STACK_NAME}" \
        --orchestrator=default \
        --artifact-store="${ARTIFACT_STORE_NAME}" \
        --deployer=default \
        --set >/dev/null 2>&1; then
    ok "created and activated stack '${STACK_NAME}'"
else
    # Already exists — just update component references and activate.
    "${ZENML[@]}" stack update "${STACK_NAME}" \
        --orchestrator=default \
        --artifact-store="${ARTIFACT_STORE_NAME}" \
        --deployer=default >/dev/null \
        || die "Failed to register or update stack '${STACK_NAME}'."
    "${ZENML[@]}" stack set "${STACK_NAME}" >/dev/null \
        || die "Failed to activate stack '${STACK_NAME}'."
    ok "updated and activated stack '${STACK_NAME}'"
fi

# -----------------------------------------------------------------------------
# 5. Tell the running Kitaru server to re-evaluate stacks. The new active
#    stack only kicks in for new executions; existing pods that cached a
#    `Stack` object need to be bounced.
# -----------------------------------------------------------------------------
log "Step 5/5: bounce kitaru-server and loseit-agent so they pick up the new stack"
kubectl -n kitaru rollout restart deploy/kitaru-server >/dev/null
kubectl -n kitaru rollout status  deploy/kitaru-server --timeout=2m >/dev/null
ok "kitaru-server restarted"

if kubectl -n loseit-agent get deploy/loseit-agent >/dev/null 2>&1; then
    kubectl -n loseit-agent rollout restart deploy/loseit-agent >/dev/null
    kubectl -n loseit-agent rollout status  deploy/loseit-agent --timeout=2m >/dev/null
    ok "loseit-agent restarted"
else
    log "loseit-agent deployment not found — skipping bounce (deploy it after this script if needed)."
fi

printf '\n\033[1;32mAll green.\033[0m\n\n'
cat <<EOF
Created / updated:
  - ZenML secret      '${KITARU_SECRET_NAME}'
  - S3 artifact store '${ARTIFACT_STORE_NAME}' -> s3://${BUCKET_NAME} via ${MINIO_ENDPOINT}
  - Stack             '${STACK_NAME}' (active)

Verify:
  uvx --from "kitaru[local]" kitaru stack current
  uvx --from "kitaru[local]" zenml artifact-store describe ${ARTIFACT_STORE_NAME}

Trigger a new flow execution from the agent and the Kitaru UI's "Logs"
panel should now load successfully (no more "Files in a local artifact
store cannot be accessed from the server.").
EOF
