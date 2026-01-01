#!/bin/bash -euox pipefail

source .env

# external public services with pretty DNS (cloudflare tunnels): 
# creates cloudflare tunnels for ingresses with the right annotations
helm repo add strrl.dev https://helm.strrl.dev
helm repo update
helm upgrade --install --wait \
  -n cloudflare-tunnel-ingress-controller --create-namespace \
  cloudflare-tunnel-ingress-controller \
  strrl.dev/cloudflare-tunnel-ingress-controller \
  --set=cloudflare.apiToken="${CLOUDFLARE_API_TOKEN}",cloudflare.accountId="${CLOUDFLARE_ACCOUNT_ID}",cloudflare.tunnelName="k3s-tunnel"

# internal services (tailscale) with no pretty DNS:
# sets up tailscale networking for a particular service so the service is accessible via a static IP
helm repo add tailscale https://pkgs.tailscale.com/helmcharts
helm repo update
helm upgrade --install tailscale-operator tailscale/tailscale-operator \
  --namespace tailscale \
  --create-namespace \
  --set-string oauth.clientId="${TAILSCALE_CLIENT_ID}" \
  --set-string oauth.clientSecret="${TAILSCALE_CLIENT_SECRET}" \
  --wait

# internal services (tailscale) with pretty DNS (cloudflare A records):
# create cloudflare API token secret if it doesn't exist
kubectl create secret generic cloudflare-api-token \
  --from-literal=cloudflare_api_token="${CLOUDFLARE_API_TOKEN}" \
  --namespace kube-system \
  --dry-run=client -o yaml | kubectl apply -f -

helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/
helm upgrade --install external-dns external-dns/external-dns \
    --namespace kube-system \
    --set "provider=cloudflare" \
    --set "env[0].name=CF_API_TOKEN" \
    --set "env[0].valueFrom.secretKeyRef.name=cloudflare-api-token" \
    --set "env[0].valueFrom.secretKeyRef.key=cloudflare_api_token" \
    --set "cloudflare.zoneIdFilter=${CLOUDFLARE_ZONE_ID}" \
    --set "domainFilters[0]=mlops-club.org" \
    --set "sources[0]=service" \
    --set "sources[1]=ingress" \
    --set "serviceTypeFilter[0]=LoadBalancer" \
    --set "txtOwnerId=k3s-cluster" \
    --wait --timeout 5m

# traefik using cloudflare for tls
helm repo add traefik https://helm.traefik.io/traefik
# create a config map needed by traefik
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: traefik-config
  namespace: kube-system
data:
  traefik.yml: |
    entryPoints:
      web:
        address: ":80"
        http:
          redirections:
            entryPoint:
              to: websecure
              scheme: https
      websecure:
        address: ":443"
        http:
          tls:
            certificates:
              - certFile: /certs/tls.crt
                keyFile: /certs/tls.key
    
    providers:
      kubernetesIngress: {}
EOF
# create the TLS keypair secret needed by traefik
kubectl create secret tls cloudflare-origin-cert \
  --cert=tls-origin-cert.pem \
  --key=tls-private-key.pem \
  --namespace kube-system \
  --dry-run=client -o yaml | kubectl apply -f -
# install traefik
helm upgrade --install traefik traefik/traefik \
  --namespace kube-system \
  --set "ingressClass.enabled=true" \
  --set "ingressClass.isDefaultClass=true" \
  --set "additionalArguments={--configfile=/config/traefik.yml}" \
  --set "volumes[0].name=config" \
  --set "volumes[0].configMap.name=traefik-config" \
  --set "volumes[1].name=cloudflare-cert" \
  --set "volumes[1].secret.secretName=cloudflare-origin-cert" \
  --set "volumeMounts[0].name=config" \
  --set "volumeMounts[0].mountPath=/config" \
  --set "volumeMounts[1].name=cloudflare-cert" \
  --set "volumeMounts[1].mountPath=/certs" \
  --wait --timeout 5m
