#!/usr/bin/env bash
# Purpose: Create or revoke the Grafana Cloud OTLP write token the Studio OTel POC's collector uses
# Usage: ./otlp-token.sh create | ./otlp-token.sh revoke | ./otlp-token.sh list
# Overview: Terraform's grafana_cloud_access_policy needs a Grafana Cloud (grafana.com) access-policy token with
#   accesspolicies:* scopes, which this repo doesn't hold. The stack's own "Cloud access policies" app
#   (grafana-auth-app) proxies the same grafana.com API for stack Admins at
#   /api/plugin-proxy/grafana-auth-app/auth/v1/*, so the homelab-terraform service-account token can do it.
#   create: access policy studio-otel-poc (traces:write, metrics:write, logs:write; realm = this stack only) and a
#   30-day token, appended to ~/credentials/homelab-otel.env (chmod 600) and never printed.
#   revoke: deletes the token and the policy named there.
# Related: ../../.ai/docs/MONITORING_ACCOUNTS.md, the POC teardown doc
set -euo pipefail
cd "$(dirname "$0")"
set -a; source "${HOMELAB_ENV:-../../.env}"; set +a
CREDS="$HOME/credentials/homelab-otel.env"
REGION=prod-us-west-0
P="$GRAFANA_URL/api/plugin-proxy/grafana-auth-app/auth/v1"
H=(-H "Authorization: Bearer $GRAFANA_SA_TOKEN" -H "Content-Type: application/json")
case "${1:-}" in
  list)
    curl -sf "${H[@]}" "$P/accesspolicies?region=$REGION" | python3 -c 'import json,sys; [print(p["id"], p["name"], p["scopes"]) for p in json.load(sys.stdin)["items"]]' ;;
  create)
    STACK=$(curl -sf "${H[@]}" "$GRAFANA_URL/api/plugins/grafana-auth-app/settings" | python3 -c 'import json,sys; print(json.load(sys.stdin)["jsonData"]["stack_id"])')
    PID=$(curl -sf -X POST "${H[@]}" "$P/accesspolicies?region=$REGION" -d "{\"name\":\"studio-otel-poc\",\"displayName\":\"Studio OTel POC (OTLP write)\",\"scopes\":[\"traces:write\",\"metrics:write\",\"logs:write\"],\"realms\":[{\"type\":\"stack\",\"identifier\":\"$STACK\",\"labelPolicies\":[]}]}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
    umask 077
    curl -sf -X POST "${H[@]}" "$P/tokens?region=$REGION" -d "{\"accessPolicyId\":\"$PID\",\"name\":\"studio-otel-collector\",\"expiresAt\":\"$(date -u -v+30d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)\"}" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(f"GRAFANA_OTLP_ENDPOINT=https://otlp-gateway-'"$REGION"'.grafana.net/otlp\nGRAFANA_OTLP_INSTANCE_ID='"$STACK"'\nGRAFANA_OTLP_TOKEN={d[\"token\"]}\nGRAFANA_OTLP_POLICY_ID='"$PID"'\nGRAFANA_OTLP_TOKEN_ID={d[\"id\"]}")' >> "$CREDS"
    chmod 600 "$CREDS"; echo "policy $PID and a token written to $CREDS" ;;
  revoke)
    set -a; source "$CREDS"; set +a
    curl -sf -o /dev/null -w 'token delete %{http_code}\n' -X DELETE "${H[@]}" "$P/tokens/$GRAFANA_OTLP_TOKEN_ID?region=$REGION" || true
    curl -sf -o /dev/null -w 'policy delete %{http_code}\n' -X DELETE "${H[@]}" "$P/accesspolicies/$GRAFANA_OTLP_POLICY_ID?region=$REGION" || true ;;
  *) echo "usage: $0 create|revoke|list" >&2; exit 2 ;;
esac
