#!/bin/bash -euo pipefail
# Complete idempotent cluster bootstrap and deployment script

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_EXAMPLES="${DEPLOY_EXAMPLES:-false}"

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

main() {
  check_prerequisites
  bootstrap_cluster
  configure_kubeconfig
  seed_secrets
  install_private_network
  install_public_network
  
  if [[ "${DEPLOY_EXAMPLES}" == "true" ]]; then
    deploy_examples
  else
    echo "Skipping example application deployment (set DEPLOY_EXAMPLES=true to enable)"
  fi
  
  verify_deployment
  
  echo ""
  echo "=== Bootstrap Complete ==="
}

main "$@"

