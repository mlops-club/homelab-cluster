#!/bin/bash -euox pipefail

kubectl apply -f manifest-internal-tailscale.yaml
kubectl apply -f manifest-public-cloudflare.yaml
kubectl apply -f manifest-internal-tailscale-cloudflare.yaml
kubectl apply -f manifest-internal-https.yaml

sleep 15


# validate connection to manifest-internal-tailscale.yaml
TAILSCALE_IP=$(kubectl get svc nginx-tailscale -o json | jq -r '.status.loadBalancer.ingress[] | select(.ip) | .ip' | head -1)
curl -f -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://$TAILSCALE_IP || echo "Connection failed - ensure you're connected to Tailscale"

# validate connection to manifest-public-cloudflare.yaml
curl -f -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://nginx.mlops-club.org

# validate connection to manifest-internal-tailscale-cloudflare.yaml
## Takes some time to propogate
curl -f -s -o /dev/null -w "HTTP Status: %{http_code}\n" --max-time 30 http://nginx-internal.mlops-club.org

