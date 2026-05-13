# How-To: Add Videos to Jellyfin

**Purpose**: Guide through uploading workout videos to the NAS and organizing them in Jellyfin using box sets

**Scope**: End-to-end workflow from iPad/Mac source files to properly organized Jellyfin library with metadata

**Overview**: Covers transferring videos to the NAS, creating NFO sidecar files for metadata, and configuring
    the Jellyfin library to display videos grouped by program using box sets. Explains the tradeoffs
    between TV Shows, "Other", and Movies library types, and why Movies with `<set>` tags was chosen.

**Dependencies**: Jellyfin deployed on the cluster (see `apps/jellyfin/`), NAS accessible via SSH

**Exports**: Videos organized into box sets in Jellyfin, viewable and downloadable from web and mobile clients

**Related**: apps/jellyfin/docs/connecting-to-jellyfin.md, apps/jellyfin/manifest.yaml

**Implementation**: Manual file transfer + NFO sidecar files + Jellyfin library configuration

**Difficulty**: beginner

---

## Prerequisites

- **Jellyfin** is deployed and accessible (see `apps/jellyfin/docs/connecting-to-jellyfin.md`)
- **SSH access** to the NAS (`eric@nas`)
- **Videos** staged on your Mac (e.g., copied from iPad via Finder's file sharing)

---

## Step 1: Transfer Videos to the NAS

Use `scp -O` to copy files to the NAS. The `-O` flag is **required** — standard scp (SFTP protocol)
and rsync both fail with path/permission errors due to the NAS's daemon configuration.

```bash
# Copy an entire program folder to the NAS
scp -O -r ~/Desktop/ipad-videos/P90X/ eric@nas:/volume1/k8s-homelab/media/videos/fitness/P90X/
```

**Path mapping**: The NAS path `/volume1/k8s-homelab/media/videos/` is mounted as `/media/` inside
the Jellyfin container. So `videos/fitness/P90X/` on the NAS becomes `/media/fitness/P90X/` in Jellyfin.

---

## Step 2: Organize Videos into Folders

Each program gets its own subfolder under `fitness/`. Videos are named
`{Program} - {Number} - {Title}.{ext}`:

```
/volume1/k8s-homelab/media/videos/
  fitness/
    P90X/
      folder.jpg
      P90X - 00 - How to Bring It.avi
      P90X - 00 - How to Bring It.nfo
      P90X - 01 - Chest and Back.avi
      P90X - 01 - Chest and Back.nfo
      ...
    P90X2/
      P90X2 - 01 - How to Bring It AGAIN.avi
      P90X2 - 01 - How to Bring It AGAIN.nfo
      ...
    P90X3/
      P90X3 - 01 - Agility X.mp4
      P90X3 - 01 - Agility X.nfo
      ...
    Insanity/
      Insanity - 00 - Dig Deeper.m4v
      Insanity - 00 - Dig Deeper.nfo
      ...
    Insanity Max 30/
      Insanity Max 30 - 01 - Cardio Challenge.mp4
      Insanity Max 30 - 01 - Cardio Challenge.nfo
      ...
    Fitness FAQs - Back Bridge/
      Fitness FAQs - Back Bridge - 101 - Dislocate.mp4
      Fitness FAQs - Back Bridge - 101 - Dislocate.nfo
      ...
```

---

## Step 3: Create NFO Sidecar Files

Every video needs a corresponding `.nfo` file with the same base name. These use the `<movie>` XML
format (not `<episodedetails>`) and drive how Jellyfin displays and groups the videos.

Example NFO for `P90X - 01 - Chest and Back.nfo`:

```xml
<movie>
  <title>Chest and Back</title>
  <sorttitle>P90X 01</sorttitle>
  <plot>Classic push-pull workout targeting chest and back muscles.</plot>
  <studio>Beachbody</studio>
  <genre>Fitness</genre>
  <set>
    <name>P90X</name>
  </set>
  <lockdata>true</lockdata>
</movie>
```

### Key fields

| Field | Purpose |
|-------|---------|
| `<title>` | Display name in Jellyfin |
| `<sorttitle>` | Controls sort order within the box set (e.g., `P90X 01`, `P90X 02`) |
| `<set><name>` | **Groups videos into a box set** — this is the grouping mechanism |
| `<lockdata>true</lockdata>` | **Prevents Jellyfin from scraping online metadata** (see gotchas below) |

You can generate NFOs in bulk with a script. The naming convention makes this straightforward — parse
the program name and number from the filename.

---

## Step 4: Create the Jellyfin Library

1. Open Jellyfin: `https://jellyfin.priv.mlops-club.org`
2. Go to **Dashboard** > **Libraries** > **Add Media Library**
3. Set:
   - **Content type**: **Movies** (not "Other", not "Shows" — see decision log below)
   - **Display name**: `Fitness` (or whatever you prefer)
   - **Folders**: `/media/fitness/`
4. Click **OK**

---

## Step 5: Refresh Metadata

A regular "Scan All Libraries" is **not enough** if you've added or changed NFO files after the
initial scan. Jellyfin caches metadata and won't re-read NFOs it has already processed.

To force a full re-read:

1. Go to **Dashboard** > **Libraries**
2. Click the **three-dot menu** on the library
3. Select **Refresh metadata**
4. Choose **Replace all metadata**

This forces Jellyfin to re-read every NFO file and update its database.

---

## How Box Sets Work

With the `<set><name>P90X</name></set>` tag in each NFO, Jellyfin automatically creates a
**box set** for each unique program name. On the Movies view, instead of showing 90 individual
videos, Jellyfin shows 6 box set cards with count badges. Click a box set to see its videos
sorted by `<sorttitle>`.

This gives a **2-click flow**: Library > Box Set > Play.

---

## Why This Approach (Decision Log)

Three approaches were tried before landing on Movies with box sets:

### Approach 1: TV Shows with Seasons (rejected)

Each program was a "show" with `Season 01/` subdirectories and `S01E01` episode naming.
Used `tvshow.nfo` and `<episodedetails>` NFOs.

**Problem**: The Season nesting created 3 clicks to reach a video (Show > Season > Episode).
There's only one "season" per program, and while Jellyfin can collapse single-season shows,
that's a library-wide display setting — it can't be scoped to just fitness content.

### Approach 2: "Other" Library Type (rejected)

The library was created with content type "Other".

**Problem**: "Other" doesn't support collections or box sets at all. Videos showed as a flat
unsorted list with no grouping.

### Approach 3: Movies with Box Sets via `<set>` Tag (chosen)

Each video is a standalone "movie". The `<set>` tag in each NFO groups them into box sets
that appear directly on the Movies tab. Box sets are file-driven (survive library
deletion/recreation), unlike Jellyfin's separate "Collections" feature which stores
groupings only in the database.

---

## Gotchas

### `<lockdata>true</lockdata>` is essential

Without it, Jellyfin scrapes online metadata databases (TMDB), matches your videos to random
movies/shows with similar names (e.g., "Insanity" matched to a TV drama), and **overwrites your
NFO files** — stripping out the `<set>` tags and custom metadata.

### Regular scans don't re-read NFOs

After modifying NFO files, you must use **Refresh metadata** > **Replace all metadata**. A
regular library scan only picks up new files, it doesn't re-read NFOs it has already processed.

### `scp -O` is required for this NAS

Standard scp (SFTP protocol) and rsync both fail with path errors due to the NAS's rsync/sftp
daemon configuration. Always use `scp -O` when transferring files.

### Container path mapping

The NAS path `/volume1/k8s-homelab/media/videos/` maps to `/media/` inside the Jellyfin
container. When configuring library paths in Jellyfin, use the container path (e.g.,
`/media/fitness/`), not the NAS path.

### Box Sets vs Collections

Jellyfin has a separate "Collections" feature (visible in the Collections tab), but those
are user-created groupings stored in the database. The `<set>` tag creates "Box Sets" which
appear directly on the Movies tab and are file-driven. Box sets are the right choice for
file-based organization.
