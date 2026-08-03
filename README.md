# Photo Sorter

A local, Lightroom-style culling tool for large photo libraries on modest hardware. Scans a folder of photos, groups near-duplicates into bursts, lets you rate/favorite/reject them with keyboard or gamepad, runs a quick ELO tournament to rank the keepers, and exports the top fraction non-destructively.

Designed to run as **one Docker container** on Linux (production) or Windows/WSL2 (dev), against a NAS photo library.

## Pipeline

1. **Scan** — incremental `os.scandir()` walk, EXIF read, 256px JPEG thumbnails cached in `/data`. Idempotent: re-scanning only processes new/changed files. ARW (Sony RAW) files are discovered and paired with their JPGs but never decoded.
2. **Analyze** — dHash + pHash and a Laplacian sharpness score per thumbnail (no heavy ML).
3. **Group** — photos are sorted chronologically, sliced into 5-minute windows, then clustered by dHash distance; singletons attach to the nearest group.
4. **Review** — fullscreen group grid with keyboard (`1-5`, `F`, `X`, `R`, arrows, `Space` for full-res zoom) and gamepad support.
5. **Tournament** — ELO seeding from ratings, random matchmaking with `MAX_VIEWS` cap, live progress.
6. **Export** — slider picks a top fraction; JPGs + paired ARWs are copied to `/export` with an atomic `manifest.txt`. Idempotent and crash-resumable.

All state lives in SQLite (WAL mode) under `/data` — every action is committed immediately, so progress and ratings survive browser refreshes and container restarts.

## Quick start (Docker)

```bash
cp .env.example .env   # edit PHOTOS_DIR / BEST_DIR to your NAS mounts
docker compose up --build
# open http://localhost:8420
```

`PHOTOS_DIR` is mounted **read-only** into the container. Thumbnails and the DB live in a named Docker volume (fast, avoids bind-mount overhead). Exports go to `BEST_DIR`.

### Windows / WSL2

Do **not** mount a Windows mapped network drive into Docker Desktop — bind-mounting SMB shares across the Docker Desktop translation layer is slow and unstable. Instead:

1. Install WSL2 + Ubuntu, then `sudo apt install cifs-utils`.
2. Mount the NAS inside WSL2:
   ```bash
   sudo mkdir -p /mnt/nas && sudo mount -t cifs //nas/pool /mnt/nas -o username=YOUR_USER,vers=3.0
   ```
3. From inside WSL2, set `.env` with the `/mnt/nas/...` paths and `docker compose up --build`.

This makes the bind mount a native Linux path — the exact same workflow as a Linux server.

### Linux server

Mount the NAS in `/etc/fstab` (CIFS, `nofail`, `rw`), set `PHOTOS_DIR`/`BEST_DIR` in `.env`, then `docker compose up -d`.

## Local development (no Docker)

Backend (Windows fallback mode — keeps SMB traffic native):

```bash
cd backend
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
set "PHOTOS_DIR=X:\path\to\photos"
set "DATA_DIR=%cd%\devdata"
set "BEST_DIR=%cd%\export"
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8080
```

Frontend (Vite dev server proxies `/api` → `:8080`):

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
cd backend
.venv\Scripts\python -m pytest
```

## Project layout

```
backend/
  app/
    config.py      # env-driven settings, directory creation
    db.py          # SQLModel models + SQLite WAL engine
    images.py      # EXIF, thumbnails, hashing, sharpness
    scanner.py     # incremental scan + JPG/RAW pairing
    analyze.py     # analysis pass + time-window clustering
    tournament.py  # ELO seeding, matchmaking, match resolution
    export.py      # non-destructive copy + atomic manifest
    paths.py       # path-traversal-safe resolution
    routes.py      # API + SSE progress stream
    main.py        # FastAPI app, SPA static serving
  tests/           # pytest suite (22 tests)
frontend/
  src/
    App.tsx                    # stage routing
    apiClient.ts               # REST + SSE client
    stages/StageOne.tsx        # scan/analyze/group + progress bars
    stages/StageTwo.tsx        # group review + controller
    stages/StageThree.tsx      # ELO tournament + preload
    stages/StageFour.tsx       # export slider
Dockerfile         # multi-stage (Node build → Python runtime, non-root)
docker-compose.yml # one service, named volume, healthcheck
```
