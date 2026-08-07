"""FastAPI routes."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse
from sqlmodel import Session, select

from . import config, export, scanner
from .analyze import analyze, group
from .db import Catalogue, Photo, PhotoGroup, get_db
from .images import make_preview
from .paths import resolve_within
from .progress import get_progress
from .tournament import next_pair, resolve_match, start_tournament, tournament_state

router = APIRouter(prefix="/api")

STAGES = ("scan", "analyze", "group", "export")


def _resolve_folder(root: Path, folder: str | None) -> Path:
    """Return the scan root for a folder name (validated, traversal-safe)."""
    root = root.resolve()
    if not folder:
        return root
    target = (root / folder).resolve()
    try:
        if target != root and root not in target.parents:
            raise ValueError
    except ValueError:
        raise HTTPException(400, f"Invalid folder: {folder}")
    if not target.exists():
        raise HTTPException(404, f"Folder does not exist: {folder}")
    return target


@router.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------

@router.get("/folders")
def list_folders(session: Session = Depends(get_db)):
    """List top-level folders that have photos in the DB or exist on disk."""
    rows = session.exec(select(Photo.folder).distinct()).all()
    db_folders = {f for f in rows if f}
    on_disk: set[str] = set()
    if config.PHOTOS_DIR.exists():
        on_disk = {p.name for p in config.PHOTOS_DIR.iterdir() if p.is_dir()}
    return {"folders": sorted(db_folders | on_disk)}


@router.get("/stats")
def stats(folder: str | None = Query(None), session: Session = Depends(get_db)):
    """Counts for the Setup page summary."""
    q = select(Photo)
    if folder:
        q = q.where(Photo.folder == folder)
    photos = session.exec(q).all()
    groups = session.exec(
        select(PhotoGroup).where(PhotoGroup.folder == (folder or ""))
    ).all() if folder else session.exec(select(PhotoGroup)).all()
    return {
        "total_photos": len(photos),
        "total_groups": len(groups),
        "rated": sum(1 for p in photos if p.rating > 0),
        "rejected": sum(1 for p in photos if p.rejected),
        "favorites": sum(1 for p in photos if p.favorite),
    }


# ---------------------------------------------------------------------------
# Scan / progress
# ---------------------------------------------------------------------------

from concurrent.futures import ThreadPoolExecutor

# Persistent executor so background jobs are guaranteed to run even after the
# request handler returns (a per-call executor can be garbage-collected before
# its worker thread picks up the task, silently dropping the job).
_background_executor = ThreadPoolExecutor(max_workers=2)


def _run_in_background(fn):
    """Run a long job in its own thread so the API threadpool never blocks.

    The job opens its own DB session (each thread needs one). Errors are
    logged and recorded in progress so failures aren't silent.
    """
    import logging

    logger = logging.getLogger("photo_sorter.background")

    def wrapper():
        try:
            with next(get_db()) as session:
                fn(session)
        except Exception:
            logger.exception("Background job failed")

    _background_executor.submit(wrapper)
    return {"status": "started"}


@router.post("/scan")
def scan_photos(folder: str | None = Query(None), session: Session = Depends(get_db)):
    """Start an incremental scan (optionally of one folder) in the background."""
    root = _resolve_folder(config.PHOTOS_DIR, folder)

    def job(s):
        scanner.scan(s, root, config.THUMBNAIL_DIR, folder=folder or "")

    return _run_in_background(job)


@router.post("/analyze")
def run_analyze(folder: str | None = Query(None), session: Session = Depends(get_db)):
    def job(s):
        analyze(s, config.THUMBNAIL_DIR, folder=folder)

    return _run_in_background(job)


@router.post("/group")
def run_group(folder: str | None = Query(None), session: Session = Depends(get_db)):
    def job(s):
        group(s, folder=folder)

    return _run_in_background(job)


def _stage_payload(session: Session, stage: str, folder: str | None = None) -> dict:
    row = get_progress(session, stage, folder=folder or "")
    return {
        "total": row.total,
        "processed": row.processed,
        "status": row.status,
        "folder": folder or "",
        "error": row.error,
    }


@router.get("/progress")
def progress(session: Session = Depends(get_db)):
    return {"stages": {stage: _stage_payload(session, stage) for stage in STAGES}}


@router.get("/events", response_class=EventSourceResponse)
async def events(request: Request):
    """Stream progress events for all pipeline stages."""
    from fastapi.sse import ServerSentEvent

    from .db import Progress

    while True:
        if await request.is_disconnected():
            break
        with next(get_db()) as session:
            stages = {}
            for stage in STAGES:
                rows = session.exec(
                    select(Progress).where(Progress.stage == stage)
                ).all()
                if not rows:
                    stages[stage] = [{"total": 0, "processed": 0, "status": "idle", "folder": "", "error": None}]
                else:
                    stages[stage] = [
                        {
                            "total": r.total,
                            "processed": r.processed,
                            "status": r.status,
                            "folder": r.folder,
                            "error": r.error,
                        }
                        for r in rows
                    ]
        yield ServerSentEvent(data={"stages": stages}, event="progress")
        await asyncio.sleep(1.0)


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------

@router.get("/photos")
def list_photos(
    group_id: int | None = None,
    folder: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: Session = Depends(get_db),
):
    q = select(Photo)
    if group_id:
        q = q.where(Photo.group_id == group_id)
    if folder:
        q = q.where(Photo.folder == folder)
    q = q.order_by(Photo.id).offset(offset).limit(limit)
    return session.exec(q).all()


@router.get("/photo/{photo_id}")
def get_photo(photo_id: int, session: Session = Depends(get_db)):
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    return photo


def _photo_or_404(session: Session, photo_id: int) -> Photo:
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    return photo


@router.get("/photo/{photo_id}/thumb")
def photo_thumb(photo_id: int, session: Session = Depends(get_db)):
    photo = _photo_or_404(session, photo_id)
    if not photo.sha1:
        raise HTTPException(404, "No thumbnail for this photo (RAW only)")
    thumb = config.THUMBNAIL_DIR / f"{photo.sha1}.jpg"
    if not thumb.exists():
        raise HTTPException(404, "Thumbnail missing")
    return FileResponse(thumb, media_type="image/jpeg")


@router.get("/photo/{photo_id}/preview")
def photo_preview(photo_id: int, session: Session = Depends(get_db)):
    """1600px preview, generated on demand and cached in /data/previews."""
    photo = _photo_or_404(session, photo_id)
    try:
        target = resolve_within(config.PHOTOS_DIR, photo.path)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if target.suffix.lower() not in (".jpg", ".jpeg"):
        raise HTTPException(400, "Preview only available for JPGs")
    preview_dir = config.DATA_DIR / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / f"{photo.id}.jpg"
    if not preview_path.exists():
        try:
            preview_path.write_bytes(make_preview(target))
        except OSError:
            raise HTTPException(500, "Could not generate preview")
    return FileResponse(preview_path, media_type="image/jpeg")


@router.get("/photo/{photo_id}/full")
def photo_full(photo_id: int, session: Session = Depends(get_db)):
    """Stream the original file from the read-only mount. Never cached."""
    photo = _photo_or_404(session, photo_id)
    try:
        target = resolve_within(config.PHOTOS_DIR, photo.path)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    media_type = "image/jpeg" if target.suffix.lower() in (".jpg", ".jpeg") else "application/octet-stream"
    return FileResponse(target, media_type=media_type)


@router.post("/photo/{photo_id}/rate")
def rate_photo(photo_id: int, rating: int = Query(..., ge=0, le=5), session: Session = Depends(get_db)):
    photo = _photo_or_404(session, photo_id)
    photo.rating = rating
    session.add(photo)
    session.commit()
    return {"ok": True, "rating": rating}


@router.post("/photo/{photo_id}/favorite")
def favorite_photo(photo_id: int, favorite: bool = Query(True), session: Session = Depends(get_db)):
    photo = _photo_or_404(session, photo_id)
    photo.favorite = favorite
    session.add(photo)
    session.commit()
    return {"ok": True, "favorite": favorite}


@router.post("/photo/{photo_id}/reject")
def reject_photo(photo_id: int, rejected: bool = Query(True), session: Session = Depends(get_db)):
    photo = _photo_or_404(session, photo_id)
    photo.rejected = rejected
    session.add(photo)
    session.commit()
    return {"ok": True, "rejected": rejected}


@router.post("/photo/{photo_id}/skip")
def skip_photo(photo_id: int, skipped: bool = Query(True), session: Session = Depends(get_db)):
    photo = _photo_or_404(session, photo_id)
    photo.skipped = skipped
    session.add(photo)
    session.commit()
    return {"ok": True, "skipped": skipped}


# ---------------------------------------------------------------------------
# Groups (Stage 2)
# ---------------------------------------------------------------------------
@router.get("/groups")
def list_groups(folder: str | None = None, limit: int = 50, offset: int = 0, session: Session = Depends(get_db)):
    q = select(PhotoGroup).order_by(PhotoGroup.start_time)
    if folder:
        q = q.where(PhotoGroup.folder == folder)
    q = q.offset(offset).limit(limit)
    groups = session.exec(q).all()
    out = []
    for g in groups:
        members = session.exec(select(Photo).where(Photo.group_id == g.id)).all()
        out.append({
            "id": g.id,
            "folder": g.folder,
            "start_time": g.start_time.isoformat() if g.start_time else None,
            "count": len(members),
            "photos": [
                {
                    "id": p.id,
                    "path": p.path,
                    "rating": p.rating,
                    "favorite": p.favorite,
                    "rejected": p.rejected,
                    "is_blurry": p.is_blurry,
                    "has_thumb": bool(p.sha1),
                    "has_raw": p.paired_id is not None,
                }
                for p in members
            ],
        })
    return out


# ---------------------------------------------------------------------------
# Tournament (Stage 3)
# ---------------------------------------------------------------------------

@router.post("/tournament/start")
def start(folder: str | None = Query(None), min_stars: int = Query(1, ge=1, le=5), session: Session = Depends(get_db)):
    total = start_tournament(session, folder=folder, min_stars=min_stars)
    return {"status": "ok", "total_votes": total}


@router.get("/tournament/state")
def state(folder: str | None = Query(None), min_stars: int = Query(1, ge=1, le=5), session: Session = Depends(get_db)):
    return tournament_state(session, folder=folder, min_stars=min_stars)


@router.get("/tournament/pair")
def pair(folder: str | None = Query(None), min_stars: int = Query(1, ge=1, le=5), session: Session = Depends(get_db)):
    pair = next_pair(session, folder=folder, min_stars=min_stars)
    if pair is None:
        return {"done": True, "photos": []}
    return {
        "done": False,
        "photos": [
            {"id": p.id, "path": p.path, "elo": p.elo, "views": p.views, "has_thumb": bool(p.sha1)}
            for p in pair
        ],
    }


@router.post("/tournament/vote")
async def vote(winner_id: int = Query(...), loser_id: int = Query(...), session: Session = Depends(get_db)):
    winner = session.get(Photo, winner_id)
    loser = session.get(Photo, loser_id)
    if winner is None or loser is None:
        raise HTTPException(404, "Photo not found")
    resolve_match(session, winner, loser)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Rankings & Export (Stage 4)
# ---------------------------------------------------------------------------

@router.get("/rankings")
def rankings(folder: str | None = Query(None), session: Session = Depends(get_db)):
    """ELO standings for a folder (or all), each with its decile tranche 1-10.

    Only rated photos (rating > 0) are shown — these are the ones that
    participate in the tournament. Unrated photos with default ELO are excluded.
    """
    q = select(Photo).where(Photo.is_raw == False, Photo.rating > 0)  # noqa: E712
    if folder:
        q = q.where(Photo.folder == folder)
    photos = sorted(session.exec(q).all(), key=lambda p: p.elo, reverse=True)
    total = max(1, len(photos))
    out = []
    for i, p in enumerate(photos):
        out.append({
            "photo_id": p.id,
            "filename": Path(p.path).name,
            "folder": p.folder,
            "elo": p.elo,
            "stars": p.rating,
            "is_favorite": p.favorite,
            "skipped": p.skipped,
            "tranche": min(10, int((i / total) * 10) + 1),
        })
    return out


@router.get("/export/preview")
def export_preview(fraction: float = Query(0.3, gt=0, le=1), folder: str | None = Query(None), session: Session = Depends(get_db)):
    """Count photos that would be exported: all rated (not skipped) above the fraction cutoff."""
    q = select(Photo).where(
        Photo.is_raw == False,  # noqa: E712
        Photo.rating > 0,
        Photo.skipped == False,  # noqa: E712
    )
    if folder:
        q = q.where(Photo.folder == folder)
    all_photos = session.exec(q).all()
    ranked = sorted(all_photos, key=lambda p: p.elo, reverse=True)
    keep_count = max(1, int(len(ranked) * fraction))
    jpgs = ranked[:keep_count]
    raws = sum(1 for p in jpgs if p.paired_id and session.get(Photo, p.paired_id).is_raw)
    return {
        "jpg_count": len(jpgs),
        "raw_count": raws,
        "total": len(jpgs) + raws,
    }


@router.post("/export")
async def start_export(fraction: float = Query(0.3, gt=0, le=1), folder: str | None = Query(None), session: Session = Depends(get_db)):
    """Launch export in a background thread; progress via SSE.

    Uses the same tranche-based selection as the Rankings page: all rated
    (not skipped) photos in the top `fraction` are exported, with paired RAWs.
    """
    from .db import ExportJob, db

    # Convert fraction (0.3) to the matching tranche (e.g. fraction 0.3 → top 3 tranches).
    cutoff_tranche = max(1, round(fraction * 10))

    job = ExportJob(fraction=fraction, status="pending")
    session.add(job)
    session.commit()
    session.refresh(job)

    loop = asyncio.get_running_loop()

    def worker():
        with db.session() as s:
            job_obj = s.get(ExportJob, job.id)
            export.run_export(s, job_obj, cutoff_tranche, config.BEST_DIR, config.PHOTOS_DIR, folder=folder)

    loop.run_in_executor(None, worker)
    return {"status": "started", "job_id": job.id}
