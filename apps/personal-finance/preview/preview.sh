#!/bin/bash
# preview.sh
# Purpose: Create, update, list, and delete per-branch preview environments of the personal-finance app
# Scope: personal-finance-<slug> namespaces labelled app.kubernetes.io/part-of=personal-finance-preview, and
#     their images in Harbor (cr.priv.mlops-club.org/personal-finance/preview)
# Overview: A preview runs one feature branch at https://personal-finance-<slug>.mlops-club.org. <slug> is the
#     branch name lowercased with every run of other characters turned into "-" (feature/Tax_Projection ->
#     feature-tax-projection), cut to fit one 63-character DNS label; a cut name ends in a short hash of the
#     full branch name so two long branches never collide. The personal-finance repo builds and pushes the
#     image (`just deploy-preview`) and then calls `deploy` here; `delete` removes the namespace (and with it
#     the preview's NAS volume) and the branch's images in Harbor. Production is never touched.
# Dependencies: kubectl, envsubst, openssl, curl, jq, a .env at the repo root with HARBOR_ADMIN_PASSWORD
# Exports: slug | url | deploy | delete | list subcommands
# Usage:
#     ./apps/personal-finance/preview/preview.sh slug <branch>
#     ./apps/personal-finance/preview/preview.sh url <branch>
#     ./apps/personal-finance/preview/preview.sh deploy <branch> <image>
#     ./apps/personal-finance/preview/preview.sh delete <branch>
#     ./apps/personal-finance/preview/preview.sh list
# Related: manifest.yaml, README.md, ../deploy.sh (production)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
PREFIX="personal-finance"
DOMAIN="mlops-club.org"
LABEL="app.kubernetes.io/part-of=personal-finance-preview"
REGISTRY="cr.priv.mlops-club.org"
HARBOR_REPO="personal-finance/preview"

die() { echo "preview.sh: $*" >&2; exit 1; }

# The URL-safe form of a branch name. "personal-finance-" + slug must fit in one 63-character DNS label.
slug() {
  local branch="$1" s max=$((63 - ${#PREFIX} - 1))
  s=$(printf '%s' "$branch" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')
  [ -n "$s" ] || die "branch '${branch}' has no letters or digits to name a preview after"
  if [ "${#s}" -gt "$max" ]; then
    local hash
    hash=$(printf '%s' "$branch" | openssl sha1 | awk '{print $NF}' | cut -c1-6)
    s="$(printf '%s' "${s:0:$((max - 7))}" | sed -E 's/-+$//')-${hash}"
  fi
  echo "$s"
}

# bash 3.2 (macOS) runs $(...) without set -e, so a failed slug is passed up by hand
name_of() { local s; s=$(slug "$1") || exit 1; echo "${PREFIX}-${s}"; }

load_env() {
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env"
  : "${HARBOR_ADMIN_PASSWORD:?Set HARBOR_ADMIN_PASSWORD in .env}"
}

deploy() {
  local branch="$1" image="$2" name
  name=$(name_of "$branch")
  load_env

  kubectl create namespace "$name" --dry-run=client -o yaml | kubectl apply -f -
  kubectl label namespace "$name" "$LABEL" --overwrite >/dev/null
  kubectl create secret docker-registry harbor-creds \
    --docker-server="$REGISTRY" \
    --docker-username=admin \
    --docker-password="${HARBOR_ADMIN_PASSWORD}" \
    --namespace "$name" \
    --dry-run=client -o yaml | kubectl apply -f -
  # Its own session key, so a sign-in on one preview (or production) never works on another
  if ! kubectl get secret session-secret --namespace "$name" >/dev/null 2>&1; then
    kubectl create secret generic session-secret \
      --from-literal=session_secret="$(openssl rand -hex 32)" \
      --namespace "$name"
  fi

  # shellcheck disable=SC2016  # envsubst takes the variable names literally
  PREVIEW_NAME="$name" PREVIEW_BRANCH="$branch" PREVIEW_IMAGE="$image" \
    envsubst '${PREVIEW_NAME} ${PREVIEW_BRANCH} ${PREVIEW_IMAGE}' < "${SCRIPT_DIR}/manifest.yaml" | kubectl apply -f -
  kubectl rollout status deployment/personal-finance --namespace "$name" --timeout=180s

  local url="https://${name}.${DOMAIN}"
  for _ in $(seq 1 30); do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' "${url}/api/users")" = "200" ]; then
      echo "Preview of ${branch} is up: ${url}"
      return
    fi
    sleep 2
  done
  die "rolled out, but ${url}/api/users isn't answering 200 yet"
}

# The NFS CSI driver can't delete nas-nfs volumes itself: it mounts the share without `nolock` and fails, leaving them
# Released. So a preview removes its own: a Job mounts the share root like init-nas.yaml and deletes the volume's
# directory, and then the PersistentVolume goes.
purge_volume() {
  local name="$1" pv subdir
  pv=$(kubectl get pvc users --namespace "$name" -o jsonpath='{.spec.volumeName}' 2>/dev/null || true)
  [ -n "$pv" ] || return 0
  subdir=$(kubectl get pv "$pv" -o jsonpath='{.spec.csi.volumeAttributes.subdir}')
  [[ "$subdir" =~ ^pvc-[0-9a-f-]{36}$ ]] || die "volume ${pv} has an unexpected subdir '${subdir}'; not deleting it"
  kubectl patch pv "$pv" -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}' >/dev/null
  kubectl scale deployment/personal-finance --namespace "$name" --replicas=0 >/dev/null 2>&1 || true
  kubectl apply -f - <<YAML
apiVersion: v1
kind: PersistentVolume
metadata:
  name: ${name}-nas-root
spec:
  capacity: {storage: 1Gi}
  accessModes: [ReadWriteMany]
  storageClassName: ""
  csi:
    driver: nfs.csi.k8s.io
    volumeHandle: ${name}-nas-root
    volumeAttributes: {server: "100.117.142.58", share: "/volume1/k8s-homelab"}
  mountOptions: [nfsvers=3, nolock]
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: nas-root, namespace: ${name}}
spec:
  accessModes: [ReadWriteMany]
  storageClassName: ""
  volumeName: ${name}-nas-root
  resources: {requests: {storage: 1Gi}}
---
apiVersion: batch/v1
kind: Job
metadata: {name: purge-users, namespace: ${name}}
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: rm
        image: busybox
        command: ["sh", "-c", "rm -rf /mnt/${subdir}"]
        volumeMounts: [{name: nas, mountPath: /mnt}]
      volumes: [{name: nas, persistentVolumeClaim: {claimName: nas-root}}]
YAML
  kubectl wait --for=condition=complete job/purge-users --namespace "$name" --timeout=120s
  echo "Deleted the preview's plans (${subdir} on the NAS)"
  PURGED_PVS="${pv} ${name}-nas-root"
}

delete() {
  local branch="$1" name tag_re digests
  name=$(name_of "$branch")
  load_env
  PURGED_PVS=""
  if kubectl get namespace "$name" >/dev/null 2>&1; then purge_volume "$name"; fi
  kubectl delete namespace "$name" --ignore-not-found --wait=true
  # shellcheck disable=SC2086  # a list of names
  [ -z "$PURGED_PVS" ] || kubectl delete pv $PURGED_PVS --ignore-not-found

  # The branch's images are tagged <slug>-<commit>; match the whole tag so "tax" never takes "tax-projection"'s
  tag_re="^${name#"${PREFIX}-"}-[0-9a-f]{7,40}$"
  digests=$(curl -sf -u "admin:${HARBOR_ADMIN_PASSWORD}" \
    "https://${REGISTRY}/api/v2.0/projects/${HARBOR_REPO%%/*}/repositories/${HARBOR_REPO#*/}/artifacts?with_tag=true&page_size=100" \
    | jq -r --arg re "$tag_re" '.[] | select(any(.tags[]?; .name | test($re))) | .digest' || true)
  for digest in $digests; do
    curl -sf -u "admin:${HARBOR_ADMIN_PASSWORD}" -X DELETE \
      "https://${REGISTRY}/api/v2.0/projects/${HARBOR_REPO%%/*}/repositories/${HARBOR_REPO#*/}/artifacts/${digest}" \
      && echo "Deleted image ${digest}"
  done
  echo "Deleted the preview of ${branch}"
}

list() {
  kubectl get namespaces -l "$LABEL" \
    -o jsonpath='{range .items[*]}{.metadata.annotations.personal-finance/branch}{"\t"}https://{.metadata.name}.'"${DOMAIN}"'{"\n"}{end}'
}

cmd="${1:-}"
case "$cmd" in
  slug)   [ $# -eq 2 ] || die "usage: $0 slug <branch>"; slug "$2" ;;
  url)    [ $# -eq 2 ] || die "usage: $0 url <branch>"; name=$(name_of "$2"); echo "https://${name}.${DOMAIN}" ;;
  deploy) [ $# -eq 3 ] || die "usage: $0 deploy <branch> <image>"; deploy "$2" "$3" ;;
  delete) [ $# -eq 2 ] || die "usage: $0 delete <branch>"; delete "$2" ;;
  list)   list ;;
  *)      die "usage: $0 {slug|url|deploy|delete|list} ..." ;;
esac
