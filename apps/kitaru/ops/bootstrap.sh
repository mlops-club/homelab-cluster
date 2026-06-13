#!/usr/bin/env bash
# One-time operator bootstrap for the Kitaru <-> loseit-agent integration.
#
# Run this ONCE from the repo root after `./apps/kitaru/deploy.sh` has come
# up green. Re-run any time you rotate the Lose It! JWT.
#
# What this script does (all against the Tailnet-only Kitaru at
# https://kitaru.priv.mlops-club.org):
#   1. Sanity-checks: server is reachable, ~/.config/loseit/token exists,
#      kubectl works.
#   2. Drives an interactive `kitaru login` so the operator authenticates in
#      a browser (OAUTH2_PASSWORD_BEARER device-style flow).
#   3. Stores the Lose It! JWT as a Kitaru secret named `loseit-token`
#      (key `token`). Per the homelab mandate, app secrets live in Kitaru's
#      secret store, NOT in plain K8s Secrets.
#   4. Creates a Kitaru service account `loseit-agent` and mints a one-time
#      API key for it.
#   5. Mirrors that one API key into the K8s cluster as
#      Secret `loseit-agent/kitaru-api-key` (key `key`) so the loseit-agent
#      Deployment can auth to Kitaru at startup and pull `loseit-token`.
#
# Idempotent where it can be:
#   - Re-running re-asserts the Kitaru `loseit-token` secret (latest JWT wins).
#   - If service-account `loseit-agent` already exists, we skip create.
#   - A new API key is minted each run; if the K8s Secret already exists you
#     are prompted before overwriting.
#
# This script never prints the Lose It! JWT or the Kitaru API key to stdout.

set -euo pipefail

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
KITARU_URL="${KITARU_URL:-https://kitaru.priv.mlops-club.org}"
LOSEIT_TOKEN_FILE="${LOSEIT_TOKEN_FILE:-${HOME}/.config/loseit/token}"
KITARU_SECRET_NAME="${KITARU_SECRET_NAME:-loseit-token}"
KITARU_SERVICE_ACCOUNT="${KITARU_SERVICE_ACCOUNT:-loseit-agent}"
KITARU_API_KEY_NAME="${KITARU_API_KEY_NAME:-loseit-agent-bootstrap}"
K8S_NAMESPACE="${K8S_NAMESPACE:-loseit-agent}"
K8S_SECRET_NAME="${K8S_SECRET_NAME:-kitaru-api-key}"

# Kitaru CLI is run on-demand via uvx so the host stays clean.
KITARU=(uvx --from "kitaru[local]" kitaru)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
log()  { printf '\033[1;36m[bootstrap]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

confirm() {
    # confirm "Prompt text" -> returns 0 on yes, 1 on no
    local prompt="${1}"
    local reply
    read -r -p "${prompt} [y/N]: " reply || return 1
    [[ "${reply}" =~ ^[Yy]$ ]]
}

# -----------------------------------------------------------------------------
# 1. Sanity checks
# -----------------------------------------------------------------------------
log "Step 1/5: sanity checks"

command -v uvx >/dev/null 2>&1 || die "uvx not found on PATH (install uv: https://docs.astral.sh/uv/)"
command -v kubectl >/dev/null 2>&1 || die "kubectl not found on PATH"
command -v curl >/dev/null 2>&1 || die "curl not found on PATH"

if ! curl -sSf -o /dev/null --max-time 10 "${KITARU_URL}/health"; then
    die "Cannot reach ${KITARU_URL}/health. Are you on the Tailnet, and is Kitaru deployed and ready?"
fi
ok "${KITARU_URL}/health reachable"

if [[ ! -s "${LOSEIT_TOKEN_FILE}" ]]; then
    die "Lose It! token not found (or empty) at ${LOSEIT_TOKEN_FILE}. Run \`lose-it auth login\` first."
fi
ok "Lose It! token present at ${LOSEIT_TOKEN_FILE} (contents not displayed)"

if ! kubectl version --output=yaml >/dev/null 2>&1; then
    die "kubectl can't talk to a cluster. Check your kubeconfig context."
fi
KUBE_CTX="$(kubectl config current-context 2>/dev/null || echo '<unknown>')"
ok "kubectl reachable (current-context: ${KUBE_CTX})"

if ! kubectl get namespace "${K8S_NAMESPACE}" >/dev/null 2>&1; then
    die "Namespace '${K8S_NAMESPACE}' does not exist. Deploy loseit-agent first (apps/loseit-agent/deploy.sh)."
fi
ok "namespace ${K8S_NAMESPACE} exists"

# -----------------------------------------------------------------------------
# 2. Interactive login
# -----------------------------------------------------------------------------
log "Step 2/5: log in to Kitaru at ${KITARU_URL}"
log "A browser tab should open for OAuth login. Complete it, then return here."
log "(If 'kitaru status' already shows you logged in to this server, you can"
log " safely re-confirm in the browser — login is idempotent.)"
echo

# `kitaru login` is interactive; let it write directly to the terminal.
"${KITARU[@]}" login "${KITARU_URL}" || die "kitaru login failed"

# Verify
if ! "${KITARU[@]}" status >/dev/null 2>&1; then
    die "\`kitaru status\` failed after login — bailing out."
fi
ok "logged in to Kitaru"

# -----------------------------------------------------------------------------
# 3. Set the loseit-token secret in Kitaru
# -----------------------------------------------------------------------------
log "Step 3/5: set Kitaru secret '${KITARU_SECRET_NAME}' (key: token)"

# Pass the JWT via an assignment of the form --token=<value>. We never echo
# the value; we redact any accidental leak in the kitaru CLI output too.
LOSEIT_JWT="$(tr -d '\n' < "${LOSEIT_TOKEN_FILE}")"
if [[ -z "${LOSEIT_JWT}" ]]; then
    die "${LOSEIT_TOKEN_FILE} is empty after stripping newlines"
fi

# `kitaru secrets set` upserts. Public secret (default) is fine — Kitaru
# scopes "public" to the active workspace, not the public internet.
if ! "${KITARU[@]}" secrets set "${KITARU_SECRET_NAME}" "--token=${LOSEIT_JWT}" >/dev/null 2>&1; then
    die "Failed to set Kitaru secret '${KITARU_SECRET_NAME}'."
fi
unset LOSEIT_JWT
ok "Kitaru secret '${KITARU_SECRET_NAME}' set (value not displayed)"

# -----------------------------------------------------------------------------
# 4. Ensure service account + mint API key
# -----------------------------------------------------------------------------
log "Step 4/5: ensure Kitaru service account '${KITARU_SERVICE_ACCOUNT}' + mint API key"

if "${KITARU[@]}" auth service-accounts show "${KITARU_SERVICE_ACCOUNT}" >/dev/null 2>&1; then
    ok "service account '${KITARU_SERVICE_ACCOUNT}' already exists"
else
    if ! "${KITARU[@]}" auth service-accounts create "${KITARU_SERVICE_ACCOUNT}" \
            --description "API access for the loseit-agent K8s Deployment" \
            >/dev/null; then
        die "Failed to create service account '${KITARU_SERVICE_ACCOUNT}'."
    fi
    ok "created service account '${KITARU_SERVICE_ACCOUNT}'"
fi

# Mint a new API key. The raw value is printed ONCE — capture it from JSON
# output so we don't have to scrape pretty-printed text. We never echo this.
log "minting API key '${KITARU_API_KEY_NAME}' (one-time value)"
API_KEY_JSON="$(
    "${KITARU[@]}" auth api-keys create "${KITARU_SERVICE_ACCOUNT}" \
        --name "${KITARU_API_KEY_NAME}" \
        --description "Bootstrap key for the loseit-agent Deployment" \
        --output json
)" || die "Failed to mint API key"

# Try common JSON shapes for the raw key. Kitaru's `create` returns the
# one-time value under one of: key / api_key / value / token.
KITARU_API_KEY="$(
    printf '%s' "${API_KEY_JSON}" | python3 -c '
import json, sys
d = json.load(sys.stdin)
# Kitaru `auth api-keys create -o json` returns:
#   {"command": "...", "item": {"key": "ZENKEY_...", ...}}
# Be defensive about other shapes too.
RAW_KEY_FIELDS = ("key", "api_key", "value", "token", "raw", "secret")
CONTAINER_FIELDS = ("item", "api_key", "data", "result")
candidates = [d]
if isinstance(d, dict):
    for c in CONTAINER_FIELDS:
        v = d.get(c)
        if isinstance(v, dict):
            candidates.append(v)
for c in candidates:
    if not isinstance(c, dict):
        continue
    for k in RAW_KEY_FIELDS:
        v = c.get(k)
        if isinstance(v, str) and v:
            print(v)
            sys.exit(0)
sys.exit(1)
'
)" || die "Could not extract API key from kitaru output. Re-run with --output text and copy it manually."
unset API_KEY_JSON
ok "minted API key '${KITARU_API_KEY_NAME}' (value not displayed)"

# -----------------------------------------------------------------------------
# 5. Mirror API key into K8s as a Secret in loseit-agent ns
# -----------------------------------------------------------------------------
log "Step 5/5: mirror API key into K8s as Secret ${K8S_NAMESPACE}/${K8S_SECRET_NAME}"

if kubectl -n "${K8S_NAMESPACE}" get secret "${K8S_SECRET_NAME}" >/dev/null 2>&1; then
    warn "K8s Secret ${K8S_NAMESPACE}/${K8S_SECRET_NAME} already exists."
    if ! confirm "Overwrite it with the newly minted API key?"; then
        unset KITARU_API_KEY
        die "Aborted by operator. The newly minted Kitaru API key has been DISCARDED (you can re-run this script to mint another)."
    fi
fi

# Apply via dry-run pipe so this is upsert-style. Keys match what the
# loseit-agent Deployment manifest references (see apps/loseit-agent/manifest.yaml).
if ! kubectl -n "${K8S_NAMESPACE}" create secret generic "${K8S_SECRET_NAME}" \
        --from-literal="api_key=${KITARU_API_KEY}" \
        --from-literal="server_url=${KITARU_URL}" \
        --dry-run=client -o yaml \
        | kubectl apply -f - >/dev/null; then
    unset KITARU_API_KEY
    die "Failed to write K8s Secret ${K8S_NAMESPACE}/${K8S_SECRET_NAME}."
fi
unset KITARU_API_KEY
ok "K8s Secret ${K8S_NAMESPACE}/${K8S_SECRET_NAME} written (keys: api_key, server_url)"

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
printf '\n\033[1;32mAll green.\033[0m\n\n'
cat <<EOF
Created / updated:
  - Kitaru secret  '${KITARU_SECRET_NAME}'          (key: token)
  - Kitaru SA      '${KITARU_SERVICE_ACCOUNT}'
  - Kitaru API key '${KITARU_API_KEY_NAME}'         (one-time value mirrored to K8s)
  - K8s Secret     ${K8S_NAMESPACE}/${K8S_SECRET_NAME} (keys: api_key, server_url)

Next steps:
  1. Restart the loseit-agent Deployment so it picks up the new API key:
       kubectl -n ${K8S_NAMESPACE} rollout restart deploy/loseit-agent
       kubectl -n ${K8S_NAMESPACE} rollout status  deploy/loseit-agent

  2. Verify from outside:
       uvx --from "kitaru[local]" kitaru secrets list   # should show ${KITARU_SECRET_NAME}
       kubectl -n ${K8S_NAMESPACE} get secret ${K8S_SECRET_NAME}

To rotate the Lose It! JWT later, just re-run this script — step 3 will
re-assert the Kitaru secret with the latest token from ${LOSEIT_TOKEN_FILE}.
EOF
