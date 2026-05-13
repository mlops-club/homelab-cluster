# Immich - AI Context

**Purpose**: AI agent context document for deploying Immich (self-hosted Google Photos) to the homelab cluster

**Scope**: Immich deployment with NFS-backed photo storage, PostgreSQL on local SSD, private Tailscale access, and ML/transcoding on CPU

**Overview**: Context document for AI agents deploying Immich to the K3s homelab. Immich is a
    self-hosted photo and video management platform with mobile auto-upload, face recognition,
    smart search, and video transcoding. It runs as a microservices architecture requiring careful
    storage decisions (NFS for media, local SSD for PostgreSQL).

**Related**: MILESTONE_BREAKDOWN.md for implementation tasks, PROGRESS_TRACKER.md for current status

---

## Overview

Immich is a high-performance, self-hosted Google Photos replacement. It provides a web UI and native
iOS/Android mobile apps with features including: timeline browsing, albums, sharing, map view, face
recognition, natural-language search (CLIP), video transcoding, RAW format support, and background
auto-upload from mobile devices.

The user plans to use Immich for personal photo and video management, accessible privately via
Tailscale at `immich.priv.mlops-club.org` and `photos.priv.mlops-club.org`.

## Feature Vision

- Self-hosted photo/video management replacing Google Photos
- Private access via Tailscale (dual hostnames: `immich.priv.mlops-club.org` and `photos.priv.mlops-club.org`)
- NAS-backed media storage on UGOS NFS
- ML-powered features (face recognition, smart search) running on CPU with optional OpenVINO acceleration
- Mobile auto-upload from iOS/Android
- Video transcoding (software-based, with potential for Intel QSV/VAAPI hardware acceleration)

## Target Architecture

### Core Components

| Component | Image | Purpose | Storage |
|---|---|---|---|
| **immich-server** | `ghcr.io/immich-app/immich-server` | API server + web UI + async job processing | NFS (media library) |
| **immich-machine-learning** | `ghcr.io/immich-app/immich-machine-learning` | Face detection, CLIP embeddings, object recognition | local-path (model cache) |
| **PostgreSQL** | `ghcr.io/immich-app/postgres` (bundles VectorChord) | Metadata, vector embeddings for smart search | **local-path (CRITICAL: NOT NFS)** |
| **Valkey/Redis** | `valkey/valkey` | BullMQ job queue | none (ephemeral) |

### Storage Layout

```
NAS (100.117.142.58)
└── /volume1/k8s-homelab/media/photos/    # Photo/video library (NFS PV, ReadWriteMany)

K3s Node (local SSD via local-path-provisioner)
├── immich-postgres-data                   # PostgreSQL data (MUST be local, NOT NFS)
└── immich-ml-cache                        # ML model cache
```

### Networking

```
Tailscale VPN
  → External-DNS (Cloudflare) creates DNS for immich.priv.mlops-club.org + photos.priv.mlops-club.org
    → Traefik Private (traefik-private)
      → Immich server (port 2283)
```

**Traefik considerations**:
- WebSocket support needed for `/api/socket.io/` (real-time notifications)
- Increase responding timeouts to 600s+ (default 60s kills video streams)
- Allow large uploads (50GB+, no request buffering)

### Integration Points

- **NFS CSI driver** (`csi-driver-nfs`): Already deployed, provides NAS-backed storage
- **Traefik Private**: Already deployed, handles `*.priv.mlops-club.org` ingress
- **cert-manager + priv-wildcard-tls**: Already deployed, provides TLS for private services
- **external-dns**: Already deployed, creates DNS records pointing to Tailscale IP

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Deployment method | Raw manifests (not Helm chart) | Follow audiobookshelf pattern; Helm chart has deprecated Postgres subchart and adds complexity |
| PostgreSQL storage | local-path (K3s default) | NFS causes database corruption due to missing POSIX file locking |
| PostgreSQL image | `ghcr.io/immich-app/postgres` | Bundles VectorChord extension required for smart search vectors |
| Media storage | NFS static PV on NAS | Follow audiobookshelf pattern; human-readable path on NAS |
| ML acceleration | CPU (OpenVINO optional) | Intel NUCs have no discrete GPU; CPU is sufficient for personal use |
| Hardware transcoding | Software initially | Can add Intel QSV/VAAPI later if NUCs have integrated graphics |
| Access | Private only (Tailscale) | Personal photos should not be publicly accessible |
| Hostnames | Two: `immich.priv` + `photos.priv` | User requested both; photos.priv is a friendly alias |
| Redis/Valkey | Bundled in manifest | Lightweight, no persistence needed |

## AI Agent Guidance

### When Implementing

- Follow the audiobookshelf pattern: namespace, static NFS PV/PVC, Deployment, Service, Ingress in a single manifest.yaml
- PostgreSQL is the exception to NFS storage -- it MUST use local-path StorageClass
- Use Immich's official Postgres image (`ghcr.io/immich-app/postgres`) -- vanilla Postgres lacks VectorChord
- The deploy.sh must create NAS directories first (same pattern as audiobookshelf)
- Use environment variables to connect components (server, ML, postgres, redis all need to find each other)
- Set timezone to `America/Denver` (cluster standard)

### Common Patterns

- Namespace-per-app: all resources in `immich` namespace
- Static NFS PV with human-readable NAS path: `/volume1/k8s-homelab/media/photos`
- deploy.sh creates NAS directories via temporary PV/PVC + Job (same as audiobookshelf)
- Private ingress: `ingressClassName: traefik-private` with `priv-wildcard-tls` TLS secret

### Things to Avoid

- Do NOT put PostgreSQL on NFS -- database corruption will occur
- Do NOT use vanilla PostgreSQL image -- VectorChord extension is required
- Do NOT use the deprecated Helm chart Postgres subchart
- Do NOT set Traefik default timeouts -- video streaming needs 600s+
- Do NOT expose publicly -- this is private-only via Tailscale

## Success Metrics

- [ ] Immich web UI accessible at `immich.priv.mlops-club.org` and `photos.priv.mlops-club.org`
- [ ] Photo upload works via web UI
- [ ] Mobile app connects and auto-upload works
- [ ] Face recognition and smart search operational
- [ ] Video playback works without timeout errors
- [ ] Photos stored on NAS at `/volume1/k8s-homelab/media/photos/`
- [ ] PostgreSQL data on local SSD (not NFS)
