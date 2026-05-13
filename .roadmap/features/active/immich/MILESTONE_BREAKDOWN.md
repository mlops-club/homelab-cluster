# Immich - Milestone Breakdown

**Purpose**: Detailed implementation breakdown of Immich deployment into milestones

**Scope**: Complete feature implementation across 3 milestones

**Overview**: Breaks the Immich deployment into 3 manageable milestones. Each milestone is
    self-contained, testable, and incrementally builds toward the complete feature.

**Related**: AI_CONTEXT.md for feature overview, PROGRESS_TRACKER.md for status tracking

---

## Overview

This document breaks down the Immich deployment into 3 milestones:

1. **Create manifests and deploy script** -- all K8s resources and the deploy.sh
2. **Configure ingress and Traefik** -- private access with dual hostnames, WebSocket support, timeouts
3. **Documentation** -- docs and how-to guides

---

## Milestone 1: Create Manifests and Deploy Script

**Objective**: Create `apps/immich/manifest.yaml` and `apps/immich/deploy.sh` with all Kubernetes resources needed to run Immich

**Tasks**:
- [ ] Create `apps/immich/` directory
- [ ] Create `manifest.yaml` with all resources (see below)
- [ ] Create `deploy.sh` that creates NAS directories and applies manifest

### manifest.yaml resources

1. **Namespace**: `immich`

2. **NFS Static PV/PVC for media library**:
   - PV `immich-library` pointing to NAS `100.117.142.58:/volume1/k8s-homelab/media/photos`
   - PVC `library` in namespace `immich`, bound to PV, 500Gi, ReadWriteMany
   - NFS mount options: `nfsvers=3, nolock`

3. **Local-path PVCs**:
   - `postgres-data` -- 20Gi, ReadWriteOnce, storageClassName `local-path` (PostgreSQL data)
   - `ml-cache` -- 10Gi, ReadWriteOnce, storageClassName `local-path` (ML model cache)

4. **PostgreSQL Deployment**:
   - Image: `ghcr.io/immich-app/postgres:14-vectorchord0.4.2` (or latest tag with VectorChord)
   - Port: 5432
   - Environment: `POSTGRES_USER=immich`, `POSTGRES_PASSWORD=immich`, `POSTGRES_DB=immich`
   - Volume mount: `postgres-data` at `/var/lib/postgresql/data`
   - Resource requests: 256Mi RAM, 250m CPU

5. **PostgreSQL Service**: ClusterIP, port 5432

6. **Valkey (Redis) Deployment**:
   - Image: `valkey/valkey:8-alpine`
   - Port: 6379
   - No persistent storage needed

7. **Valkey Service**: ClusterIP, port 6379

8. **Immich Server Deployment**:
   - Image: `ghcr.io/immich-app/immich-server:release`
   - Port: 2283
   - Environment variables:
     - `DB_HOSTNAME=immich-postgres`
     - `DB_USERNAME=immich`, `DB_PASSWORD=immich`, `DB_DATABASE_NAME=immich`
     - `REDIS_HOSTNAME=immich-valkey`
     - `TZ=America/Denver`
   - Volume mount: `library` at `/usr/src/app/upload`
   - Resource requests: 512Mi RAM, 500m CPU

9. **Immich Server Service**: ClusterIP, port 2283

10. **Immich Machine Learning Deployment**:
    - Image: `ghcr.io/immich-app/immich-machine-learning:release`
    - Port: 3003
    - Environment: `TZ=America/Denver`
    - Volume mount: `ml-cache` at `/cache`
    - Resource requests: 1Gi RAM, 500m CPU

11. **Immich ML Service**: ClusterIP, port 3003

### deploy.sh tasks

- Create NAS directory `/volume1/k8s-homelab/media/photos` via temporary PV/PVC + Job (same pattern as audiobookshelf)
- Wait for job completion
- Clean up temporary PV/PVC/Job
- Apply manifest.yaml

**Success Criteria**:
- [ ] All pods running in `immich` namespace: postgres, valkey, server, machine-learning
- [ ] PostgreSQL is on local-path storage (not NFS)
- [ ] Media library PVC is bound to NFS PV
- [ ] `kubectl logs` shows no errors on any pod

**Files Changed**:
```
apps/immich/manifest.yaml   (new)
apps/immich/deploy.sh       (new)
```

---

## Milestone 2: Configure Ingress and Traefik

**Objective**: Make Immich accessible at `immich.priv.mlops-club.org` and `photos.priv.mlops-club.org` with proper WebSocket and timeout configuration

**Tasks**:
- [ ] Add Ingress resource to manifest.yaml for both hostnames
- [ ] Configure WebSocket support for `/api/socket.io/`
- [ ] Add Traefik middleware or annotations for extended timeouts (600s)
- [ ] Add Traefik middleware or annotations for large upload support
- [ ] Reference `priv-wildcard-tls` for TLS

### Ingress configuration

- `ingressClassName: traefik-private`
- Two host rules: `immich.priv.mlops-club.org` and `photos.priv.mlops-club.org`
- TLS using `priv-wildcard-tls` secret (replicated by Reflector from `traefik-private` namespace)
- Annotations for:
  - WebSocket upgrade headers
  - Response timeout 600s
  - Large request body (0 = unlimited)

**Success Criteria**:
- [ ] `https://immich.priv.mlops-club.org` loads the Immich web UI (via Tailscale)
- [ ] `https://photos.priv.mlops-club.org` loads the same Immich web UI
- [ ] WebSocket connection established (check browser dev tools)
- [ ] Video playback works without 499/timeout errors
- [ ] Large photo uploads succeed

**Files Changed**:
```
apps/immich/manifest.yaml   (modified -- add Ingress + middleware)
```

---

## Milestone 3: Documentation

**Objective**: Create documentation for Immich deployment

**Tasks**:
- [ ] Create `apps/immich/docs/` directory
- [ ] Write deployment docs covering architecture, storage decisions, and access
- [ ] Document mobile app setup (iOS/Android auto-upload configuration)
- [ ] Document NAS directory structure
- [ ] Document how to import existing photos (immich-go CLI, web upload)

**Success Criteria**:
- [ ] Documentation exists at `apps/immich/docs/`
- [ ] A user can follow the docs to understand the deployment
- [ ] Mobile app connection instructions are clear

**Files Changed**:
```
apps/immich/docs/            (new directory)
apps/immich/docs/README.md   (new)
```

---

## Implementation Guidelines

### Code Standards
- Follow audiobookshelf manifest pattern (namespace, PV, PVC, Deployment, Service, Ingress in one file)
- Use kebab-case for resource names prefixed with `immich-` where needed for uniqueness
- Comment sections in manifest.yaml for readability

### Testing Requirements
- Each milestone: all pods healthy, no CrashLoopBackOff
- Milestone 2: browser test via Tailscale
- End-to-end: upload a photo, verify it appears in timeline, verify face detection runs

### Progress Tracking
After completing each milestone:
1. Record commit hash in PROGRESS_TRACKER.md
2. Update milestone status
3. Verify all success criteria met

## Success Metrics

- [ ] All 3 milestones completed successfully
- [ ] Immich fully functional with web UI and mobile access
- [ ] Documentation complete and accurate
- [ ] Feature meets stated objectives from AI_CONTEXT.md
