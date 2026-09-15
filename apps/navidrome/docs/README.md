# Navidrome — Self-Hosted Music Streaming

**Purpose**: Deployment documentation for Navidrome on the K3s homelab cluster

**Scope**: Architecture, storage decisions, deployment, and adding music to the library

**Overview**: Navidrome is a self-hosted, modern music streaming server compatible with
    Subsonic/Airsonic API clients. It indexes a music library from NFS-backed NAS storage,
    serves a web UI plus a Subsonic-compatible API for third-party mobile clients, and
    keeps its SQLite database on node-local SSD storage. Accessible privately via
    Tailscale at navidrome.priv.mlops-club.org.

**Related**: how-to-add-audiobooks-to-audiobookshelf.md (analogous transfer flow for music)

---

## Architecture

- **Music library**: NFS share `100.117.142.58:/volume1/k8s-homelab/media/music`, mounted
  read-write at `/music` in the pod. Colocated on the NAS next to `audiobooks/`, `podcasts/`,
  `ebooks/`, `photos/`, and `videos/`.
- **Data dir**: Local-path PVC (5 Gi) mounted at `/data`. Holds the SQLite DB, scan cache,
  and transcoded files. Must not live on NFS — SQLite needs POSIX file locking.
- **Ingress**: Traefik private (`traefik-private` ingress class), TLS via the private
  wildcard cert (`priv-wildcard-tls`), reachable only over Tailscale.

## Music Library Layout

Navidrome reads ID3 tags, so folder names are cosmetic. The standard
Beets/MusicBrainz Picard convention is used:

```
/volume1/k8s-homelab/media/music/
└── <Album Artist>/
    └── <Album> (<Year>)/
        ├── 01 - <Track>.mp3
        ├── 02 - <Track>.mp3
        └── cover.jpg
```

Multi-disc albums use `Disc 1/`, `Disc 2/` subfolders. Various-artists compilations live
under `Various Artists/`.

## Deployment

```bash
./apps/navidrome/deploy.sh
```

The script creates the NAS `music/` directory via a one-shot Job, then applies the full
manifest.

## Adding Music

Transfer music to the NAS using the same tar-over-SSH pattern documented for audiobooks:

```bash
tar cf - -C ~/Music "Imagine Dragons" \
  | ssh eric@100.117.142.58 "tar xf - -C /volume1/k8s-homelab/media/music/"
```

Navidrome rescans hourly (`ND_SCANSCHEDULE=@every 1h`) and on startup. Trigger an
immediate scan from the web UI: Settings → Rescan Library.

## Configuration

Environment variables set in the Deployment:

| Variable | Value | Purpose |
|----------|-------|---------|
| `ND_MUSICFOLDER` | `/music` | Path to the music library inside the container |
| `ND_DATAFOLDER` | `/data` | Path to the SQLite DB + cache |
| `ND_LOGLEVEL` | `info` | Log verbosity |
| `ND_SCANSCHEDULE` | `@every 1h` | Periodic library scan cron |
| `TZ` | `America/Denver` | Timezone for scheduled scans |

Full configuration reference: https://www.navidrome.org/docs/usage/configuration-options/

## Client Apps

Navidrome implements the Subsonic API, so any Subsonic-compatible client works:

- **iOS**: play:Sub, Substreamer, Amperfy
- **Android**: DSub, Substreamer, Symfonium
- **Web**: Built-in Navidrome web UI at https://navidrome.priv.mlops-club.org

Configure clients with the server URL `https://navidrome.priv.mlops-club.org` and the
user account created at first login.
