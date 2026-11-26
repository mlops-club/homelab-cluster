# syntax=docker/dockerfile:1.7
# Dockerfile
# Purpose: Build the k2-agents image (K2 daemon + Claude Code CLI + uv) for linux/amd64 and linux/arm64
# Scope: The image run by the k2 StatefulSet in namespace k2 (manifest.yaml)
# Overview: A fetch stage downloads the prebuilt binary of each tool for TARGETARCH and verifies it
#     against a pinned checksum: the k2-daemon GitHub release asset (sha256) and the Claude Code native
#     binary from its per-platform npm package (npm sha512 integrity). uv and uvx are the static musl
#     binaries from Astral's ghcr.io/astral-sh/uv image, pinned by index digest. The runtime stage is ubuntu:24.04 with ca-certificates, curl, git, libssl3 and tini,
#     a k2 user (uid 10000, gid 0) whose home /var/lib/k2 is the data volume, and the binaries in
#     /usr/bin and /usr/local/bin. tini is PID 1 and runs k2-daemon. The layer order, environment,
#     labels and runtime config reproduce the original buildah-built amd64 image exactly.
# Dependencies: docker buildx (BuildKit), network access to github.com, registry.npmjs.org and ghcr.io
# Exports: cr.priv.mlops-club.org/k2/k2-agents:<k2>-cc<claude>-uv<uv> (tag scheme in build.sh)
# Interfaces: Build args K2_VERSION, CLAUDE_CODE_VERSION, UV_VERSION, UV_IMAGE (ghcr.io/astral-sh/uv
#     tag@digest) and the per-arch checksums K2_DAEMON_SHA256_{AMD64,ARM64} and
#     CLAUDE_CODE_INTEGRITY_{AMD64,ARM64} (npm "sha512-<base64>")
# Implementation: Downloads run on BUILDPLATFORM (no emulation); only apt-get and useradd run
#     on the target platform. Every checksum is required, so a version bump without new
#     checksums fails the build instead of shipping an unverified binary.
# Related: build.sh, manifest.yaml, README.md

ARG UBUNTU_IMAGE=ubuntu:24.04@sha256:562111b88caa79c71391c0c4d3c2114a7d5c35915c20561fd893cb1e07929e6b
ARG UV_IMAGE

# ── uv: Astral's image holds static /uv and /uvx for each platform ───────────
FROM ${UV_IMAGE} AS uv

# ── fetch: prebuilt binaries for the target architecture, checksum-verified ──
FROM --platform=$BUILDPLATFORM ${UBUNTU_IMAGE} AS fetch
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*
ARG TARGETARCH
ARG K2_VERSION
ARG CLAUDE_CODE_VERSION
ARG K2_DAEMON_SHA256_AMD64
ARG K2_DAEMON_SHA256_ARM64
ARG CLAUDE_CODE_INTEGRITY_AMD64
ARG CLAUDE_CODE_INTEGRITY_ARM64
WORKDIR /fetch
RUN set -eux; \
    : "${K2_VERSION:?}" "${CLAUDE_CODE_VERSION:?}"; \
    case "$TARGETARCH" in \
      amd64) k2_arch=x86_64;  npm_arch=x64;   k2_sha="$K2_DAEMON_SHA256_AMD64"; cc_sha="$CLAUDE_CODE_INTEGRITY_AMD64" ;; \
      arm64) k2_arch=aarch64; npm_arch=arm64; k2_sha="$K2_DAEMON_SHA256_ARM64"; cc_sha="$CLAUDE_CODE_INTEGRITY_ARM64" ;; \
      *) echo "unsupported TARGETARCH: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    : "${k2_sha:?missing k2-daemon checksum for $TARGETARCH}" "${cc_sha:?missing claude checksum for $TARGETARCH}"; \
    # k2-daemon: GitHub release asset
    curl -fsSL -o k2-daemon "https://github.com/Alakazam-211/K2/releases/download/${K2_VERSION}/k2-daemon-linux-${k2_arch}"; \
    echo "${k2_sha}  k2-daemon" | sha256sum -c -; \
    install -D -m 0755 k2-daemon /out/k2/usr/bin/k2-daemon; \
    # claude: native binary inside the per-platform npm package, checked against npm's sha512 integrity
    curl -fsSL -o claude.tgz "https://registry.npmjs.org/@anthropic-ai/claude-code-linux-${npm_arch}/-/claude-code-linux-${npm_arch}-${CLAUDE_CODE_VERSION}.tgz"; \
    cc_hex="$(printf '%s' "${cc_sha#sha512-}" | base64 -d | od -An -v -tx1 | tr -d ' \n')"; \
    echo "${cc_hex}  claude.tgz" | sha512sum -c -; \
    tar xzf claude.tgz; \
    grep -q "\"version\": \"${CLAUDE_CODE_VERSION}\"" package/package.json; \
    install -D -m 0755 package/claude /out/claude/usr/local/bin/claude

# ── runtime ──────────────────────────────────────────────────────────────────
FROM ${UBUNTU_IMAGE}
ARG K2_VERSION
ARG CLAUDE_CODE_VERSION
ARG UV_VERSION
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git libssl3 tini \
 && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10000 --gid 0 --home-dir /var/lib/k2 --no-create-home --shell /usr/sbin/nologin k2 \
 && install -d -m 0770 -o 10000 -g 0 /var/lib/k2
COPY --from=fetch /out/k2/usr/bin/k2-daemon /usr/bin/k2-daemon
COPY --from=fetch /out/claude/ /
COPY --from=uv /uv /uvx /usr/local/bin/
# DISABLE_AUTOUPDATER: the image tag pins the Claude Code version; it never updates itself on the volume.
ENV HOME=/var/lib/k2 \
    K2_ROLE=all \
    K2_LISTEN=lan \
    K2_DAEMON_PORT=7420 \
    DISABLE_AUTOUPDATER=1 \
    UV_CACHE_DIR=/var/lib/k2/.cache/uv
LABEL dev.k2.version=${K2_VERSION} \
      dev.k2.claude-code.version=${CLAUDE_CODE_VERSION} \
      dev.k2.uv.version=${UV_VERSION}
VOLUME ["/var/lib/k2"]
WORKDIR /var/lib/k2
USER 10000:0
EXPOSE 7420
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/bin/k2-daemon"]
