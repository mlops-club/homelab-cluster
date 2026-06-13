#!/usr/bin/env bash
# End-to-end smoke test for the loseit-agent platform.
# Run from the repo root after `deploy.sh` lands. Exits non-zero on any failure.
#
#   bash apps/loseit-agent/smoke-test.sh
#
# Covers:
#   - Kitaru server health + API + secret presence
#   - Ollama model endpoint reachable
#   - Agent healthz, bearer auth, end-to-end SSE round-trip via Pipe selftest
#
# Requires the operator's environment: `kubectl` configured for the homelab,
# Tailscale up, ~/.config/loseit/token populated, ~/credentials/homelab.env
# sourced for KITARU_API_KEY (used by the secret-presence check).
set -euo pipefail
ok() { printf "✅ %s\n" "$*"; }
fail() { printf "❌ %s\n" "$*"; exit 1; }

step() { printf "\n=== %s ===\n" "$*"; }

step "Kitaru server"
curl -sSf -o /dev/null -w "  /health %{http_code}\n" https://kitaru.priv.mlops-club.org/health \
  || fail "kitaru /health"
ok "kitaru /health 200"

if [[ -n "${KITARU_API_KEY:-}" ]]; then
  resp=$(curl -sSf -H "Authorization: Bearer $KITARU_API_KEY" \
    "https://kitaru.priv.mlops-club.org/api/v1/secrets?name=loseit-token")
  jq -e '.items | length > 0' <<<"$resp" >/dev/null || fail "loseit-token secret missing"
  ok "loseit-token present in Kitaru store"
else
  printf "  (skip secret check — KITARU_API_KEY not set; source ~/credentials/homelab.env)\n"
fi

step "Ollama"
curl -sSf -o /dev/null -w "  /v1/models %{http_code}\n" \
  https://ollama.priv.mlops-club.org/v1/models || fail "ollama /v1/models"
ok "ollama /v1/models 200"

step "Agent service"
curl -sSf https://loseit-agent.priv.mlops-club.org/healthz | jq -e '.status=="ok"' >/dev/null \
  || fail "agent /healthz"
ok "agent /healthz ok"

code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
  https://loseit-agent.priv.mlops-club.org/run \
  -H "Content-Type: application/json" -d '{"prompt":"hi"}')
[[ "$code" == "401" ]] || fail "expected 401 without bearer, got $code"
ok "agent /run rejects no-auth (401)"

step "End-to-end Pipe selftest"
TOKEN=$(kubectl -n loseit-agent get secret agent-token -o jsonpath='{.data.token}' | base64 -d)
AUTH_TOKEN=$TOKEN AGENT_URL=https://loseit-agent.priv.mlops-club.org \
  uv run --no-project --with httpx --with pydantic \
  apps/loseit-agent/pipe/selftest.py | tail -3

ok "all green — see kitaru.priv.mlops-club.org/executions for the run trace"
