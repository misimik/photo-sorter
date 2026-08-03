# Photo Sorter — Implementation Plan v2

A local, Lightroom-style culling tool for 10k+ photo libraries on modest hardware (Intel i5-4000). Prioritizes **reliability, simplicity, and a single Docker container that runs identically on Windows and Linux.**

---

## 1. Architecture & Tech Stack

**One container, one service.** FastAPI serves both the API and the built SPA (static files mounted at `/`). No nginx, no separate frontend container — fewer moving parts, one port, one healthcheck. This is the single biggest simplification over v1.

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python 3.12 + FastAPI** (`python:3.12-slim` image) | Best image ecosystem; 3.12 is mature with full wheel coverage. |
| SSE | **Native `fastapi.sse.EventSourceResponse`** | FastAPI added built-in SSE — drop the `sse-starlette` dependency entirely. |
| Database | **SQLite + SQLModel** | Zero-setup, resumable state. Enable WAL mode (`journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`). |
| Frontend | **React 19 + Vite + TypeScript + Tailwind CSS v4** | Vite 7 + `@tailwindcss/vite` plugin: no `tailwind.config.js`, no PostCSS config. TS catches refactor bugs in the controller/grid code. |
| Image processing | **Pillow** (thumbnails, EXIF via `Image.getexif()`), **ImageHash** (dHash + pHash), **`opencv-python-headless`** (Laplacian) | Headless build needs no `libGL` → small image, no "missing libgl1" runtime failures. No RAW decoding — ever (see §5). |
| Deployment | **Docker + Compose**, multi-stage build | Node stage builds the SPA, Python stage runs it. |

No heavy ML/CV models. Everything in the hot path runs on 256px thumbnails, not full-res files.

---

## 2. Docker & Storage Strategy (Windows + Linux)

### The rule

**Never bind-mount a Windows network drive (SMB share) into a Docker container.** On Docker Desktop this crosses a file-system translation layer (9P) and is both slow and historically unstable. The same path mounted natively in Linux is fast and boring.

### Supported run modes (all use the *same* `docker-compose.yml`)

1. **Linux server (production target — primary):** Mount the NAS in `/etc/fstab` (CIFS, `nofail`, `rw`) → bind mount read-only into the container. This is the reference deployment.
2. **Windows dev (recommended):** Install WSL2 with Ubuntu, mount the NAS inside WSL2 via `cifs-utils` (`sudo mount -t cifs //nas/pool /mnt/nas -o username=...,vers=3.0`), and run `docker compose up` **from inside WSL2**. The bind mount is then a native Linux path — zero translation, no Docker Desktop file-sharing involvement.
3. **Windows fallback:** Run the backend natively in a `venv` (FastAPI + Vite dev server) without Docker. Keeps the SMB traffic 100% native NTFS/CIFS.

### Storage split

| Container path | Host source | Mode | Why |
|---|---|---|---|
| `/photos` | `${PHOTOS_DIR}` (NAS) | `ro` | Read-only at the Docker level AND validated in-app (§4). |
| `/data` | **named volume** (default) | `rw` | DB + thumbnails. Docker docs recommend non-code data live in the Linux VM — named volumes avoid 9P overhead on Windows and are much faster. Bind-mount only on Linux if you want to inspect thumbnails. |
| `/export` | `${BEST_DIR}` (NAS) | `rw` | Non-destructive export target. |

### `docker-compose.yml` (single file for both platforms)

```yaml
services:
  photo-sorter:
    build: .
    image: photo-sorter:local
    ports:
      - "${PORT:-8080}:8080"
    volumes:
      - ${PHOTOS_DIR}:/photos:ro
      - photo-data:/data
      - ${BEST_DIR}:/export
    environment:
      PHOTOS_DIR: /photos
      DATA_DIR: /data
      BEST_DIR: /export
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2)"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  photo-data:
```

### `.env` (Linux server example)

```env
PHOTOS_DIR=/mnt/nas/pool/photos/Unsorted
BEST_DIR=/mnt/nas/pool/photos/Best
PORT=8080
```

(Windows/WSL2 uses the same file with `PHOTOS_DIR=/mnt/nas/...` inside the distro.)

### Container hardening

- Multi-stage build; final image runs as **non-root** (`USER appuser`).
- `pip install --no-cache-dir` + pinned requirements (`pip-tools`/`uv` lockfile).
- `restart: unless-stopped` + `/api/health` healthcheck → crash recovery is automatic.

---

## 3. Implementation Phases

### Phase 1 — Data layer & incremental scanner

1. **Schema** (`sqlmodel`): `Catalogue` (folder, scan state), `Photo` (path, size, mtime, EXIF datetime/orientation, hashes, sharpness, rating, favorite, blurred, ELO, view count), `PhotoGroup`, `TournamentMatch`.
2. **Scanner** — one `os.scandir()` walk collecting `(path, size, mtime, stem)`; no `glob`. **Incremental & idempotent:** on each scan, only new/`mtime`-changed files are processed; `(path, size, mtime)` is the identity key, so re-scans are cheap and crash-safe.
3. **JPG/ARW pairing** by file stem (`.`-normalized). ARW files are *discovered and stored, never read* (§5).
4. **EXIF** via Pillow `Image.getexif()` — `DateTimeOriginal`, `Orientation`. Applied to the thumbnail and full-res preview, so orientation never needs to be baked into files.
5. **Thumbnail engine:** 256px JPEG → `/data/thumbnails/{sha1(path,size,mtime)}.jpg`. Content-addressed names make dedupe automatic and re-generation impossible to double.
6. **Concurrency:** `ThreadPoolExecutor(max_workers=cpu_count)` (4 on an i5-4000). No unbounded parallelism — the SMB filesystem is the bottleneck and thundering-herding it is what caused the instability in v1.
7. **Progress = committed DB counts.** The SSE progress stream reads `processed/total` from SQLite, so progress is *derived state*, not in-memory. Browser refresh or container restart resumes exactly where it stopped.

### Phase 2 — Automated analysis & grouping (Stage 1)

1. **Sharpness:** grayscale → `cv2.Laplacian(img, cv2.CV_64F).var()` on the 256px thumbnail. Threshold is **percentile-based** (e.g. bottom 10% flagged ⚠️), computed after the pass, not a magic constant. Stored per photo; re-runnable.
2. **Hashing:** **dHash (primary)** — fast and framing-sensitive, ideal for near-duplicate bursts. **pHash (secondary)** stored for optional subject grouping. Both are single-digit ms per thumbnail.
3. **Clustering:**
   - Sort by EXIF datetime (fallback: file mtime).
   - Slice into 5-minute time windows.
   - Within each window, cluster by Hamming distance `< N` (start `N=8` on 64-bit dHash, tune on real data).
   - **Cleanup pass:** singletons get attached to the chronologically nearest group (target context size ~4).
   - Groups are deterministic and stored in `PhotoGroup`; regrouping only recomputes affected windows.

### Phase 3 — Group review UI (Stage 2)

1. **Layout:** CSS Grid with a dynamic column count; aspect ratios come from actual thumbnail dimensions (no EXIF trust needed). Masonry-style packing so wide shots get maximum real estate.
2. **Controller class:** global keyboard map (`1-5`, `X` blur, `F` favorite, `R` reject, arrows, `Space` zoom, `Enter` next) + **Gamepad API** polled in a `requestAnimationFrame` loop (left stick → arrows, A/B/X/Y → actions).
3. **Full-res zoom:** `Space` hits `GET /api/photo/{id}/full` which streams the original JPG from the read-only `/photos` mount. **Never cached, never thumbnailed** — one image at a time over LAN is fine.
4. **Chrome:** `overflow: hidden`, fullscreen app feel; every action persisted to SQLite immediately.

### Phase 4 — Tournament engine (Stage 3)

1. **ELO seeding** from review ratings: `1★=1000`, `3★=1400`, `5★=1800`, favorite `+100`.
2. **Matchmaking:** random pair of rated photos (≥1★), neither exceeding `MAX_VIEWS` (4). *Optional tuning knob:* bias toward pairs within ~200 ELO for faster convergence — off by default.
3. **ELO math:** standard chess formula, `K=32`, `expected = 1/(1+10^((opp−player)/400))`.
4. **Progress:** total votes = `rated_count × MAX_VIEWS`; every vote writes `TournamentMatch` + ELO to SQLite and pushes an SSE event.
5. **Preload:** next pair silently loaded into hidden `<img>` tags during the animation frame after each vote — zero flicker.

### Phase 5 — Rankings & export (Stage 4)

1. **Ranking:** `ORDER BY elo DESC` → decile slicing.
2. **UI:** slider ("Top 30%") with live count preview *"Selecting 142 photos (142 JPGs + 142 ARWs)"*.
3. **Export worker (background, SSE progress):**
   - `shutil.copy2` (preserves timestamps) to `/export`, **idempotent** — existing files are skipped, so a failed export resumes cleanly.
   - `manifest.txt` written **atomically** (tmp file + `os.replace`): original paths, final ELO, export timestamp.
   - Copy worker uses a small thread pool; paths re-validated against `PHOTOS_DIR` at export time (§4).

---

## 4. Cross-cutting reliability & security

- **SQLite as source of truth, WAL mode on.** Every star, flag, and match is a single committed row. Recovery = restarting the app; there is no in-memory state to lose. WAL gives concurrent readers during writes; `busy_timeout` prevents lock errors under SSE load.
- **Path traversal defense everywhere.** `/api/photo/{id}/full`, thumbnail serving, and export all resolve paths and verify `os.path.commonpath([realpath(p), PHOTOS_DIR]) == PHOTOS_DIR`. Docker-level `:ro` is defense-in-depth, not the only line.
- **Resumable pipeline.** Scan, analysis, and export all key progress off persisted DB state, never RAM.
- **Bounded concurrency.** `max_workers = cpu_count` everywhere; no parallel full-res reads.
- **Non-root container, pinned deps, healthcheck, restart policy.** (Details in §2.)

---

## 5. Key decisions vs v1 (and why)

| v1 | v2 | Reason |
|---|---|---|
| `sse-starlette` | Native `fastapi.sse` | One fewer dependency; FastAPI supports it natively now. |
| `opencv-python` | `opencv-python-headless` | No `libGL` → slim image, no runtime missing-lib failures. |
| JS | TypeScript | Catches bugs in keyboard/gamepad/grid logic before they ship. |
| Tailwind v3 config | Tailwind v4 Vite plugin | Zero config, faster builds. |
| nginx + separate FE container | FastAPI serves built SPA | One container, one port, one healthcheck — simpler ops. |
| `/data` bind mount | named volume (default) | Docker-recommended for non-code data; avoids 9P overhead on Windows. |
| venv-first on Windows | **WSL2 + CIFS mount, Docker from inside WSL2** | Bind mounts become native Linux paths; identical workflow to production. |
| In-memory progress | Progress derived from DB counts | Crash/browser-refresh safe by construction. |
| — | WAL mode, `busy_timeout` | SQLite reliability under concurrent read/write + SSE. |
| — | Non-root USER, healthcheck, pinned deps | Container reliability for long-running NAS service. |
| — | Path validation on every file endpoint | The app sits on the LAN; don't expose traversal bugs. |
| — | Idempotent scan/export, atomic `manifest.txt` | Failures are cheap to recover from. |

---

## 6. Milestones & acceptance

- **M1 — Scanner + thumbnails + DB:** incremental scan of 10k photos over 1GbE NAS on the i5 completes; re-scan is near-instant; kill mid-scan → restart resumes.
- **M2 — Analysis + groups:** blur flags, hashes, and time-window clusters computed; grouping is deterministic.
- **M3 — Review UI:** keyboard + gamepad group review; full-res zoom streams from `/photos`; actions survive refresh.
- **M4 — Tournament:** ELO pairs, preloading, progress bar, restart-safe state.
- **M5 — Export:** slider → copy2 → manifest; interrupted export resumes; identical `docker compose up` behavior on Windows (WSL2) and Linux.
