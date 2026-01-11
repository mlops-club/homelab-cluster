#!/bin/bash -euo pipefail
# Complete idempotent cluster bootstrap and deployment script

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source .env file
if [[ ! -f "${SCRIPT_DIR}/.env" ]]; then
  echo "Error: .env file not found. Please create it from env.example"
  exit 1
fi
source "${SCRIPT_DIR}/.env"

# Set CLOUDFLARE_DOMAIN from DOMAIN if not explicitly set
if [[ -z "${CLOUDFLARE_DOMAIN:-}" ]] && [[ -n "${DOMAIN:-}" ]]; then
  export CLOUDFLARE_DOMAIN="${DOMAIN}"
fi

# Required environment variables (CLOUDFLARE_DOMAIN can be derived from DOMAIN)
REQUIRED_VARS=(
  "CLOUDFLARE_API_TOKEN"
  "CLOUDFLARE_ACCOUNT_ID"
  "CLOUDFLARE_ZONE_ID"
  "TAILSCALE_CLIENT_ID"
  "TAILSCALE_CLIENT_SECRET"
  "ACME_EMAIL"
)

check_prerequisites() {
  echo "=== Checking Prerequisites ==="
  
  # Verify .env variables
  local missing_vars=()
  for var in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!var:-}" ]]; then
      missing_vars+=("${var}")
    fi
  done
  
  # Check CLOUDFLARE_DOMAIN (can be set directly or derived from DOMAIN)
  if [[ -z "${CLOUDFLARE_DOMAIN:-}" ]]; then
    if [[ -z "${DOMAIN:-}" ]]; then
      missing_vars+=("CLOUDFLARE_DOMAIN or DOMAIN")
    fi
  fi
  
  if [[ ${#missing_vars[@]} -gt 0 ]]; then
    echo "Error: The following required variables are not set in .env file:"
    printf '  - %s\n' "${missing_vars[@]}"
    exit 1
  fi
  
  # Verify inventory files
  if [[ ! -f "${SCRIPT_DIR}/k3s-ansible/inventory/cluster/hosts.ini" ]]; then
    echo "Error: Inventory file not found: ${SCRIPT_DIR}/k3s-ansible/inventory/cluster/hosts.ini"
    exit 1
  fi
  
  if [[ ! -f "${SCRIPT_DIR}/k3s-ansible/inventory/cluster/group_vars/all.yml" ]]; then
    echo "Error: Group vars file not found: ${SCRIPT_DIR}/k3s-ansible/inventory/cluster/group_vars/all.yml"
    exit 1
  fi
  
  # Verify SSH access (basic check - try to connect to first node)
  echo "Verifying SSH access to cluster nodes..."
  local first_node
  first_node=$(grep -E "^\[master\]" -A 10 "${SCRIPT_DIR}/k3s-ansible/inventory/cluster/hosts.ini" | grep -v "^\[" | head -1 | awk '{print $1}' || echo "")
  
  if [[ -n "${first_node}" ]]; then
    local ssh_user
    ssh_user=$(grep -E "^\[master\]" -A 10 "${SCRIPT_DIR}/k3s-ansible/inventory/cluster/hosts.ini" | grep "${first_node}" | grep -oE 'ansible_user=[^ ]+' | cut -d= -f2 || echo "main")
    
    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "${ssh_user}@${first_node}" "echo 'SSH connection successful'" &>/dev/null; then
      echo "Warning: Could not verify SSH access to ${ssh_user}@${first_node}"
      echo "  Continuing anyway - SSH will be required during cluster bootstrap"
    else
      echo "✓ SSH access verified to ${ssh_user}@${first_node}"
    fi
  fi
  
  echo "✓ Prerequisites check passed"
}

bootstrap_cluster() {
  echo "=== Bootstrapping k3s Cluster ==="
  cd "${SCRIPT_DIR}/k3s-ansible"
  ./run deploy
  cd "${SCRIPT_DIR}"
  echo "✓ Cluster bootstrap completed"
}

configure_kubeconfig() {
  echo "=== Configuring kubeconfig ==="
  "${SCRIPT_DIR}/refresh-kube-config.py"
  echo "✓ Kubeconfig configured"
}

seed_secrets() {
  echo "=== Seeding Kubernetes Secrets ==="
  
  # Create traefik-private namespace if it doesn't exist
  kubectl create namespace traefik-private --dry-run=client -o yaml | kubectl apply -f -
  
  # Create Cloudflare API token secret (idempotent)
  # This secret needs both keys for different components
  kubectl create secret generic cloudflare-api-token \
    --from-literal=api-token="${CLOUDFLARE_API_TOKEN}" \
    --from-literal=cloudflare_api_token="${CLOUDFLARE_API_TOKEN}" \
    --namespace traefik-private \
    --dry-run=client -o yaml | kubectl apply -f -
  
  echo "✓ Secrets seeded"
}

install_private_network() {
  echo "=== Installing Private Network Components ==="
  "${SCRIPT_DIR}/network/private/helm-install.sh"
  echo "✓ Private network components installed"
}

install_public_network() {
  echo "=== Installing Public Network Components ==="
  "${SCRIPT_DIR}/network/public/helm-install.sh"
  echo "✓ Public network components installed"
}

deploy_examples() {
  echo "=== Deploying Example Applications ==="
  
  # Deploy private network examples
  if [[ -d "${SCRIPT_DIR}/network/private/examples" ]]; then
    for manifest in "${SCRIPT_DIR}/network/private/examples"/*.yaml; do
      if [[ -f "$manifest" ]]; then
        echo "  Deploying $(basename "$manifest")..."
        kubectl apply -f "$manifest" || echo "    Warning: Failed to deploy $(basename "$manifest")"
      fi
    done
  fi
  
  # Deploy public network examples
  if [[ -d "${SCRIPT_DIR}/network/public/examples" ]]; then
    for manifest in "${SCRIPT_DIR}/network/public/examples"/*.yaml; do
      if [[ -f "$manifest" ]]; then
        echo "  Deploying $(basename "$manifest")..."
        kubectl apply -f "$manifest" || echo "    Warning: Failed to deploy $(basename "$manifest")"
      fi
    done
  fi
  
  echo "✓ Example applications deployed"
}

verify_deployment() {
  echo "=== Verifying Deployment ==="
  
  echo ""
  echo "Cluster nodes:"
  kubectl get nodes || echo "  Warning: Could not list nodes"
  
  echo ""
  echo "All pods status:"
  kubectl get pods --all-namespaces || echo "  Warning: Could not list pods"
  
  echo ""
  echo "✓ Deployment verification complete"
}

validate_example_services() {
  echo "=== Validating Example Services ==="
  
  local max_attempts=60
  local attempt=1
  local failed_services=()
  
  # Wait for example pods to be ready
  echo "Waiting for example application pods to be ready..."
  for namespace in whoami-public whoami-external whoami-internal; do
    if kubectl get namespace "$namespace" &>/dev/null; then
      echo "  Waiting for pods in namespace $namespace..."
      kubectl wait --for=condition=ready pod -l app=whoami -n "$namespace" --timeout=180s 2>/dev/null || true
    fi
  done
  
  # Wait a bit more for ingress and routing to be ready
  echo "  Waiting for ingress routing to be ready..."
  sleep 10
  
  # Test public services (via HTTPS)
  echo ""
  echo "Testing public services via HTTPS..."
  
  # Test whoami.mlops-club.org
  echo "  Testing whoami.mlops-club.org..."
  attempt=1
  while [[ $attempt -le $max_attempts ]]; do
    local http_code
    local curl_output
    curl_output=$(curl -sf -m 15 -o /dev/null -w "%{http_code}" "https://whoami.mlops-club.org" 2>&1)
    http_code="${curl_output##*$'\n'}"
    if [[ -z "$http_code" ]] || [[ "$http_code" == "000" ]]; then
      http_code="ERR"
    fi
    if [[ "$http_code" =~ ^[23][0-9]{2}$ ]]; then
      echo "    ✓ whoami.mlops-club.org is responding (HTTP $http_code)"
      break
    fi
    if [[ $attempt -eq $max_attempts ]]; then
      echo "    ✗ whoami.mlops-club.org failed to respond after $max_attempts attempts (last code: $http_code)"
      failed_services+=("whoami.mlops-club.org")
    elif [[ $((attempt % 10)) -eq 0 ]]; then
      echo "    Attempt $attempt/$max_attempts: HTTP $http_code (waiting...)"
    fi
    sleep 3
    ((attempt++))
  done
  
  # Test private services (via Tailscale)
  echo ""
  echo "Testing private services via Tailscale..."
  
  # Get Traefik Private LoadBalancer IP or hostname
  local traefik_private_endpoint
  traefik_private_endpoint=$(kubectl get svc traefik-private -n traefik-private -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
  if [[ -z "$traefik_private_endpoint" ]]; then
    traefik_private_endpoint=$(kubectl get svc traefik-private -n traefik-private -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null)
  fi
  if [[ -z "$traefik_private_endpoint" ]]; then
    # Try alternative JSON path
    traefik_private_endpoint=$(kubectl get svc traefik-private -n traefik-private -o json 2>/dev/null | grep -oE '"ip":\s*"[^"]+"' | head -1 | cut -d'"' -f4)
  fi
  
  if [[ -n "$traefik_private_endpoint" ]]; then
    # Test whoami.priv.mlops-club.org
    echo "  Testing whoami.priv.mlops-club.org via $traefik_private_endpoint..."
    attempt=1
    while [[ $attempt -le $max_attempts ]]; do
      local http_code
      local curl_output
      curl_output=$(curl -sf -m 15 -o /dev/null -w "%{http_code}" -H "Host: whoami.priv.mlops-club.org" "http://${traefik_private_endpoint}" 2>&1)
      http_code="${curl_output##*$'\n'}"
      if [[ -z "$http_code" ]] || [[ "$http_code" == "000" ]]; then
        http_code="ERR"
      fi
      if [[ "$http_code" =~ ^[23][0-9]{2}$ ]]; then
        echo "    ✓ whoami.priv.mlops-club.org is responding (HTTP $http_code)"
        break
      fi
      if [[ $attempt -eq $max_attempts ]]; then
        echo "    ✗ whoami.priv.mlops-club.org failed to respond after $max_attempts attempts (last code: $http_code)"
        failed_services+=("whoami.priv.mlops-club.org")
      elif [[ $((attempt % 10)) -eq 0 ]]; then
        echo "    Attempt $attempt/$max_attempts: HTTP $http_code (waiting...)"
      fi
      sleep 3
      ((attempt++))
    done
  else
    echo "  Warning: Could not determine Traefik Private LoadBalancer endpoint"
    failed_services+=("whoami.priv.mlops-club.org (no LB endpoint)")
  fi
  
  echo ""
  # Check if certificates are ready (they may take several minutes)
  local cert_ready=true
  if ! kubectl get secret mlops-wildcard-tls -n traefik-public &>/dev/null; then
    echo "  ⚠ Certificate mlops-wildcard-tls not ready yet (this is normal, can take 2-5 minutes)"
    cert_ready=false
  fi
  if ! kubectl get secret priv-wildcard-tls -n traefik-private &>/dev/null; then
    echo "  ⚠ Certificate priv-wildcard-tls not ready yet (this is normal, can take 2-5 minutes)"
    cert_ready=false
  fi
  
  if [[ ${#failed_services[@]} -eq 0 ]]; then
    echo "✓ All example services validated successfully"
  else
    echo "⚠ Some services failed validation (this may be expected if certificates are still being issued):"
    printf '  - %s\n' "${failed_services[@]}"
    echo ""
    if [[ "$cert_ready" == "false" ]]; then
      echo "  Note: TLS certificates are still being issued by cert-manager."
      echo "  Services will become available once certificates are ready (typically 2-5 minutes)."
      echo "  You can check certificate status with:"
      echo "    kubectl get certificate -A"
    else
      echo "  Note: Services may take a few minutes to become fully available."
      echo "  DNS propagation and routing updates can cause delays."
    fi
  fi
}

main() {
  check_prerequisites
  bootstrap_cluster
  configure_kubeconfig
  seed_secrets
  install_private_network
  install_public_network
  deploy_examples
  verify_deployment
  validate_example_services
  
  echo ""
  echo "=== Bootstrap Complete ==="
}

main "$@"

