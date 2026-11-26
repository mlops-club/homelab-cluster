# k2

**Purpose**: Build the multi-arch k2-agents image and record the K2 deployment on the homelab cluster

**Scope**: `apps/k2/`: the k2-agents image (Dockerfile, build.sh) and the Kubernetes objects in
    namespace `k2` (manifest.yaml)

**Overview**: K2 runs as one `k2-daemon` replica (StatefulSet `k2`) with the Claude Code CLI and uv
    on its PATH, served at https://k2.priv.mlops-club.org through `traefik-private`. The image
    `cr.priv.mlops-club.org/k2/k2-agents` is ubuntu:24.04 plus three prebuilt binaries, each chosen
    by `TARGETARCH` and checksum-pinned, so one buildx build produces a `linux/amd64` + `linux/arm64`
    index as the cluster's Container Image Rules require.

**Dependencies**: Harbor (`cr.priv.mlops-club.org`, project `k2`), `traefik-private`, the
    `local-path` storage class on cluster-node-2, Secret `harbor-creds` in namespace `k2`

**Exports**: `k2` namespace, `cr.priv.mlops-club.org/k2/k2-agents:<k2>-cc<claude>-uv<uv>`

**Related**: `Dockerfile`, `build.sh`, `manifest.yaml`, `.ai/ai-rules.md` (Container Image Rules)

---

## Image contents

| Path | Source | Verified by |
|------|--------|-------------|
| `/usr/bin/k2-daemon` | GitHub release asset `k2-daemon-linux-{x86_64,aarch64}` of [Alakazam-211/K2](https://github.com/Alakazam-211/K2) | sha256 in `build.sh` |
| `/usr/local/bin/claude` | npm package `@anthropic-ai/claude-code-linux-{x64,arm64}` (native binary) | npm sha512 integrity in `build.sh` |
| `/usr/local/bin/uv`, `uvx` | `ghcr.io/astral-sh/uv:<version>` (static musl build) | image index digest in `build.sh` |

Runtime: user `10000:0`, home and volume `/var/lib/k2`, port 7420, `tini` as PID 1 running
`/usr/bin/k2-daemon`. `DISABLE_AUTOUPDATER=1` keeps Claude Code at the version in the tag. The
labels `dev.k2.version`, `dev.k2.claude-code.version` and `dev.k2.uv.version` record the versions.

## Build and push

Versions and checksums live at the top of `build.sh`. The tag is
`${K2_VERSION#v}-cc${CLAUDE_CODE_VERSION}-uv${UV_VERSION}`, for example `0.46.5-cc2.1.308-uv0.13.6`.

```bash
docker login cr.priv.mlops-club.org
BUILDX_BUILDER=multi ./apps/k2/build.sh   # any builder that targets linux/amd64 and linux/arm64
```

To bump a version, update it and its checksums in `build.sh`:

```bash
gh release view <k2-tag> -R Alakazam-211/K2 --json assets \
  --jq '.assets[] | select(.name | test("^k2-daemon-linux-(x86_64|aarch64)$")) | "\(.name) \(.digest)"'
npm view @anthropic-ai/claude-code-linux-x64@<version> dist.integrity
npm view @anthropic-ai/claude-code-linux-arm64@<version> dist.integrity
docker buildx imagetools inspect ghcr.io/astral-sh/uv:<version>   # index Digest
```

A missing or wrong checksum fails the build.

## Deploy

```bash
kubectl apply -f apps/k2/manifest.yaml
```

`harbor-creds` (image pull secret) is created out of band and never committed. The namespace also
holds the Opaque Secrets `k2-owner`, `golden-rules-studio-api-key` and
`golden-rules-studio-api-key-previous`, which no object in `manifest.yaml` mounts.

The StatefulSet is pinned to cluster-node-2 because its `local-path` volume lives on that node's
disk; the pin is about data locality, not CPU architecture.
