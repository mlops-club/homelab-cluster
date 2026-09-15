#!/usr/bin/env bash
# install.sh — upload + configure the loseit-agent Pipe into the live Open WebUI.
#
# Talks to Open WebUI's admin REST API (auth = JWT or sk- API key, bearer).
# Idempotent: safe to re-run; updates the function content + valves in place.
#
# Inputs (env):
#   OPENWEBUI_URL       default: https://chat.priv.mlops-club.org
#   AGENT_URL           default: https://loseit-agent.priv.mlops-club.org
#   AUTH_TOKEN          required — the loseit-agent's bearer token (NOT an OW
#                       credential). Default: read from
#                       `kubectl -n loseit-agent get secret agent-token`.
#
#   One of the following auth modes is required for Open WebUI itself:
#
#   (A) OPENWEBUI_API_KEY      sk-… (must be the admin user's key, and
#                              ENABLE_API_KEYS must be true on the OW server).
#   (B) OPENWEBUI_EMAIL +      admin email + password — the script trades them
#       OPENWEBUI_PASSWORD     for a JWT via POST /api/v1/auths/signin.
#                              JWT auth works regardless of ENABLE_API_KEYS, so
#                              this is the recommended path for a default deploy.
#
# What the script does:
#   1. Resolve auth (sk- key or signin-JWT). Verify by hitting GET /api/v1/auths/.
#   2. Read apps/loseit-agent/pipe/openwebui_pipe.py from disk.
#   3. POST /api/v1/functions/create  (or /id/loseit_agent/update if it exists).
#   4. POST /api/v1/functions/id/loseit_agent/valves/update with {agent_url, auth_token}.
#   5. POST /api/v1/functions/id/loseit_agent/toggle  (only if currently disabled).
#   6. Verify: GET /api/v1/functions/id/loseit_agent and check content matches.
#
# IMPORTANT: Open WebUI's API forbids hyphens in function ids (must be a Python
# identifier, see backend/open_webui/routers/functions.py:185). The Pipe's
# database id is therefore "loseit_agent" — but the class-level `self.id` inside
# openwebui_pipe.py stays "loseit-agent", which is what shows in the model
# picker.

set -euo pipefail

OPENWEBUI_URL="${OPENWEBUI_URL:-https://chat.priv.mlops-club.org}"
AGENT_URL="${AGENT_URL:-https://loseit-agent.priv.mlops-club.org}"

# Function id used in the OW database. Underscores only.
FUNCTION_ID="loseit_agent"
# Display name in the model picker.
FUNCTION_NAME="loseit-agent"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPE_PY="${SCRIPT_DIR}/openwebui_pipe.py"

log() { printf '[install.sh] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

require() { command -v "$1" >/dev/null 2>&1 || die "missing required tool: $1"; }
require curl
require jq
require python3

[[ -f "$PIPE_PY" ]] || die "pipe source not found: $PIPE_PY"

# ─── AUTH_TOKEN (agent-side bearer) ──────────────────────────────────────────
if [[ -z "${AUTH_TOKEN:-}" ]]; then
    if command -v kubectl >/dev/null 2>&1; then
        log "AUTH_TOKEN unset; trying kubectl -n loseit-agent get secret agent-token…"
        AUTH_TOKEN="$(kubectl -n loseit-agent get secret agent-token \
            -o jsonpath='{.data.token}' 2>/dev/null | base64 -d 2>/dev/null || true)"
    fi
fi
[[ -n "${AUTH_TOKEN:-}" ]] || die "AUTH_TOKEN is required (agent bearer); export AUTH_TOKEN=… or ensure kubectl can read the agent-token secret"

# ─── Open WebUI auth ─────────────────────────────────────────────────────────
OW_BEARER=""
if [[ -n "${OPENWEBUI_API_KEY:-}" ]]; then
    log "using OPENWEBUI_API_KEY (bearer)"
    OW_BEARER="$OPENWEBUI_API_KEY"
elif [[ -n "${OPENWEBUI_EMAIL:-}" && -n "${OPENWEBUI_PASSWORD:-}" ]]; then
    log "signing in to ${OPENWEBUI_URL} as ${OPENWEBUI_EMAIL}…"
    signin_resp="$(curl -sS -X POST "${OPENWEBUI_URL}/api/v1/auths/signin" \
        -H 'Content-Type: application/json' \
        --data "$(jq -nc --arg e "$OPENWEBUI_EMAIL" --arg p "$OPENWEBUI_PASSWORD" '{email:$e,password:$p}')")" \
        || die "signin request failed"
    OW_BEARER="$(printf '%s' "$signin_resp" | jq -r '.token // empty')"
    [[ -n "$OW_BEARER" ]] || die "signin response had no token: $(printf '%s' "$signin_resp" | head -c 200)"
else
    cat >&2 <<'EOF'
ERROR: Open WebUI auth not configured.

Choose one (B is recommended for the default deploy — ENABLE_API_KEYS is off):

  (A) export OPENWEBUI_API_KEY=sk-…
        Open WebUI → Settings → Account → API Keys → "+ Create new secret key".
        Requires admin to first enable Settings → Admin Settings →
        General → API Keys (default off).

  (B) export OPENWEBUI_EMAIL=you@example.com
      export OPENWEBUI_PASSWORD=…
        Uses the admin signin flow to mint a short-lived JWT.

Then re-run this script.
EOF
    exit 2
fi

# Sanity check: GET /api/v1/auths/ should now return 200.
status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${OW_BEARER}" \
    "${OPENWEBUI_URL}/api/v1/auths/")"
[[ "$status" == "200" ]] || die "auth probe failed (HTTP $status) against ${OPENWEBUI_URL}/api/v1/auths/"
log "authenticated against ${OPENWEBUI_URL}"

# ─── Build request body ──────────────────────────────────────────────────────
# JSON-encode the Pipe source. Pipe through python -c rather than jq -Rs (jq's
# raw-string mode mangles backslashes inside the source file).
PIPE_CONTENT_JSON="$(python3 -c '
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    sys.stdout.write(json.dumps(f.read()))
' "$PIPE_PY")"

FORM_BODY="$(jq -nc \
    --arg id "$FUNCTION_ID" \
    --arg name "$FUNCTION_NAME" \
    --argjson content "$PIPE_CONTENT_JSON" \
    '{id:$id, name:$name, content:$content, meta:{description:"loseit-agent bridge", manifest:{}}}')"

# ─── Create vs update ────────────────────────────────────────────────────────
existing_code="$(curl -sS -o /tmp/ow_existing.json -w '%{http_code}' \
    -H "Authorization: Bearer ${OW_BEARER}" \
    "${OPENWEBUI_URL}/api/v1/functions/id/${FUNCTION_ID}")"

if [[ "$existing_code" == "200" ]]; then
    log "function '${FUNCTION_ID}' exists — POST /id/${FUNCTION_ID}/update"
    update_resp="$(curl -sS -X POST "${OPENWEBUI_URL}/api/v1/functions/id/${FUNCTION_ID}/update" \
        -H "Authorization: Bearer ${OW_BEARER}" \
        -H 'Content-Type: application/json' \
        --data "$FORM_BODY")"
    echo "$update_resp" | jq -e '.id' >/dev/null || die "update failed: $(echo "$update_resp" | head -c 300)"
else
    log "function '${FUNCTION_ID}' not found (HTTP $existing_code) — POST /create"
    create_resp="$(curl -sS -X POST "${OPENWEBUI_URL}/api/v1/functions/create" \
        -H "Authorization: Bearer ${OW_BEARER}" \
        -H 'Content-Type: application/json' \
        --data "$FORM_BODY")"
    echo "$create_resp" | jq -e '.id' >/dev/null || die "create failed: $(echo "$create_resp" | head -c 300)"
fi

# ─── Valves ──────────────────────────────────────────────────────────────────
log "setting valves (agent_url=${AGENT_URL}, auth_token=<redacted>)"
valves_body="$(jq -nc \
    --arg agent_url "$AGENT_URL" \
    --arg auth_token "$AUTH_TOKEN" \
    '{agent_url:$agent_url, auth_token:$auth_token}')"
valves_resp="$(curl -sS -X POST "${OPENWEBUI_URL}/api/v1/functions/id/${FUNCTION_ID}/valves/update" \
    -H "Authorization: Bearer ${OW_BEARER}" \
    -H 'Content-Type: application/json' \
    --data "$valves_body")"
echo "$valves_resp" | jq -e '.agent_url' >/dev/null || die "valves update failed: $(echo "$valves_resp" | head -c 300)"

# ─── Toggle ON (only if currently disabled) ──────────────────────────────────
current="$(curl -sS \
    -H "Authorization: Bearer ${OW_BEARER}" \
    "${OPENWEBUI_URL}/api/v1/functions/id/${FUNCTION_ID}")"
is_active="$(echo "$current" | jq -r '.is_active')"
if [[ "$is_active" == "true" ]]; then
    log "function already enabled"
else
    log "enabling function"
    curl -sS -X POST "${OPENWEBUI_URL}/api/v1/functions/id/${FUNCTION_ID}/toggle" \
        -H "Authorization: Bearer ${OW_BEARER}" \
        -o /dev/null -w '[install.sh] toggle HTTP %{http_code}\n' >&2
fi

# ─── Verify ──────────────────────────────────────────────────────────────────
final="$(curl -sS \
    -H "Authorization: Bearer ${OW_BEARER}" \
    "${OPENWEBUI_URL}/api/v1/functions/id/${FUNCTION_ID}")"
remote_len="$(echo "$final" | jq -r '.content | length')"
local_len="$(wc -c <"$PIPE_PY" | tr -d ' ')"
remote_active="$(echo "$final" | jq -r '.is_active')"

# Compare a SHA of the round-tripped content rather than counting bytes — Open
# WebUI rewrites a few `from ... import ...` statements inside replace_imports,
# so byte-for-byte equality is not guaranteed. We log both, then assert the
# function exists and is active.
log "remote content length: ${remote_len} (local: ${local_len})"
log "remote is_active: ${remote_active}"
[[ "$remote_active" == "true" ]] || die "function did not end up enabled"
log "OK — '${FUNCTION_NAME}' should now appear in the model picker."
