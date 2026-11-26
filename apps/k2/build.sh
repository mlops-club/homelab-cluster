#!/bin/bash
# build.sh
# Purpose: Build and push the multi-arch k2-agents image to Harbor
# Scope: cr.priv.mlops-club.org/k2/k2-agents, platforms linux/amd64 and linux/arm64
# Overview: Pins the K2, Claude Code and uv versions plus the checksum of every downloaded binary,
#     derives the tag <k2>-cc<claude>-uv<uv>, and runs one docker buildx build for both platforms
#     with --push, so the tag is a multi-arch index. Bumping a version means updating its checksums
#     here: the k2-daemon sha256 from the release's asset digests (gh release view --json assets),
#     the Claude Code npm integrity (npm view @anthropic-ai/claude-code-linux-<arch>@<v> dist.integrity),
#     and the ghcr.io/astral-sh/uv index digest (docker buildx imagetools inspect ghcr.io/astral-sh/uv:<v>).
# Dependencies: docker buildx with a builder that can build linux/amd64 and linux/arm64,
#     docker login to cr.priv.mlops-club.org
# Usage: ./apps/k2/build.sh
#     BUILDX_BUILDER=multi ./apps/k2/build.sh
# Related: Dockerfile, manifest.yaml, README.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IMAGE_REPO="cr.priv.mlops-club.org/k2/k2-agents"

K2_VERSION="v0.46.5"
CLAUDE_CODE_VERSION="2.1.308"
UV_VERSION="0.13.6"

# github.com/Alakazam-211/K2 release ${K2_VERSION}: k2-daemon-linux-{x86_64,aarch64}
K2_DAEMON_SHA256_AMD64="ea54a52e1e9874cd1452d2b92418468d4b0736d0f1b896168d7fb29806622769"
K2_DAEMON_SHA256_ARM64="bbdc527b7efad974358c31529e6411b400635e61213d5c7cd4a676ba0f7c40ff"
# npm @anthropic-ai/claude-code-linux-{x64,arm64}@${CLAUDE_CODE_VERSION} dist.integrity
CLAUDE_CODE_INTEGRITY_AMD64="sha512-ffUryevpH7POStPJ/xpUI5R1ozYbH9o/Dbh/xPSmyVJehELnRMZmRnejdQmq0TejOW/SbNnJFhCGMgwIsOqFTQ=="
CLAUDE_CODE_INTEGRITY_ARM64="sha512-xtT2Cd7n+yZN9PiWbWHaZf9w25YflV+7VOX5IBPB/IWErKZFhsst2/Ay1tSgq/Mzp1vp56xwFRqPa6UAI9BZIw=="
# ghcr.io/astral-sh/uv:${UV_VERSION} multi-arch index digest (static musl uv + uvx)
UV_IMAGE="ghcr.io/astral-sh/uv:${UV_VERSION}@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0"

TAG="${K2_VERSION#v}-cc${CLAUDE_CODE_VERSION}-uv${UV_VERSION}"

builder_args=()
if [[ -n "${BUILDX_BUILDER:-}" ]]; then
  builder_args=(--builder "${BUILDX_BUILDER}")
fi

docker buildx build "${builder_args[@]}" \
  --platform linux/amd64,linux/arm64 \
  --build-arg K2_VERSION="${K2_VERSION}" \
  --build-arg CLAUDE_CODE_VERSION="${CLAUDE_CODE_VERSION}" \
  --build-arg UV_VERSION="${UV_VERSION}" \
  --build-arg K2_DAEMON_SHA256_AMD64="${K2_DAEMON_SHA256_AMD64}" \
  --build-arg K2_DAEMON_SHA256_ARM64="${K2_DAEMON_SHA256_ARM64}" \
  --build-arg CLAUDE_CODE_INTEGRITY_AMD64="${CLAUDE_CODE_INTEGRITY_AMD64}" \
  --build-arg CLAUDE_CODE_INTEGRITY_ARM64="${CLAUDE_CODE_INTEGRITY_ARM64}" \
  --build-arg UV_IMAGE="${UV_IMAGE}" \
  --push \
  -t "${IMAGE_REPO}:${TAG}" \
  "${SCRIPT_DIR}"

echo "Pushed ${IMAGE_REPO}:${TAG}"
docker buildx imagetools inspect "${IMAGE_REPO}:${TAG}"
