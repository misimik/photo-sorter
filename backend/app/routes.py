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
from .paths import resolve_within
from .progress import get_progress
from .tournament import next_pair, resolve_match, start_tournament, tournament_state

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Scan / progress
# ---------------------------------------------------------------------------

def _run_in_background(fn):
    """Run a long job in its own thread so the API threadpool never blocks.

    The job opens its own DB session (each thread needs one).
    """
    from concurrent.futures import ThreadPoolExecutor

    def wrapper():
        with next(get_db()) as session:
            fn(session)

    ThreadPoolExecutor(max_workers=1).submit(wrapper)
    return {"status": "started"}


@router.get("/scan")
def scan_photos(session: Session = Depends(get_db)):
    """Start an incremental scan in the background. Progress via /api/events."""
    root = config.PHOTOS_DIR
    if not root.exists():
        raise HTTPException(404, f"Photos dir {root} does not exist")

    def job(s):
        scanner.scan(s, root, config.THUMBNAIL_DIR)

    return _run_in_background(job)


@router.get("/analyze")
def run_analyze(session: Session = Depends(get_db)):
    def job(s):
        analyze(s, config.THUMBNAIL_DIR)

    return _run_in_background(job)


@router.get("/group")
def run_group(session: Session = Depends(get_db)):
    def job(s):
        group(s)

    return _run_in_background(job)


@router.get("/progress")
def progress(session: Session = Depends(get_db)):
    return {
        "stages": {
            stage: {
                "total": (row := get_progress(session, stage)).total,
                "processed": row.processed,
                "status": row.status,
                "error": row.error,
            }
            for stage in ("scan", "analyze", "group", "export")
        }
    }


@router.get("/events", response_class=EventSourceResponse)
async def events(request: Request):
    """Stream progress events for all pipeline stages."""
    import asyncio

    from fastapi.sse import ServerSentEvent

    from sqlmodel import select

    from .db import Progress

    while True:
        if await request.is_disconnected():
            break
        with next(get_db()) as session:
            stages = {}
            for stage in ("scan", "analyze", "group", "export"):
                row = session.exec(select(Progress).where(Progress.stage == stage)).first()
                if row is None:
                    stages[stage] = {"total": 0, "processed": 0, "status": "idle", "error": None}
                else:
                    stages[stage] = {
                        "total": row.total,
                        "processed": row.processed,
                        "status": row.status,
                        "error": row.error,
                    }
        yield ServerSentEvent(data={"stages": stages}, event="progress")
        await asyncio.sleep(1.0)


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------

@router.get("/photos")
def list_photos(
    group_id: int | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: Session = Depends(get_db),
):
    q = select(Photo)
    if group_id:
        q = q.where(Photo.group_id == group_id)
    q = q.order_by(Photo.id).offset(offset).limit(limit)
    return session.exec(q).all()


@router.get("/photo/{photo_id}")
def get_photo(photo_id: int, session: Session = Depends(get_db)):
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    return photo


@router.get("/photo/{photo_id}/thumb")
def photo_thumb(photo_id: int, session: Session = Depends(get_db)):
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    if not photo.sha1:
        raise HTTPException(404, "No thumbnail for this photo (RAW only)")
    thumb = config.THUMBNAIL_DIR / f"{photo.sha1}.jpg"
    if not thumb.exists():
        raise HTTPException(404, "Thumbnail missing")
    return FileResponse(thumb, media_type="image/jpeg")


@router.get("/photo/{photo_id}/full")
def photo_full(photo_id: int, session: Session = Depends(get_db)):
    """Stream the original file from the read-only mount. Never cached."""
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    try:
        target = resolve_within(config.PHOTOS_DIR, photo.path)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    media_type = "image/jpeg" if target.suffix.lower() in (".jpg", ".jpeg") else "application/octet-stream"
    return FileResponse(target, media_type=media_type)


@router.post("/photo/{photo_id}/rate")
def rate_photo(photo_id: int, rating: int = Query(..., ge=0, le=5), session: Session = Depends(get_db)):
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    photo.rating = rating
    session.add(photo)
    session.commit()
    return {"ok": True, "rating": rating}


@router.post("/photo/{photo_id}/favorite")
def favorite_photo(photo_id: int, favorite: bool = Query(True), session: Session = Depends(get_db)):
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    photo.favorite = favorite
    session.add(photo)
    session.commit()
    return {"ok": True, "favorite": favorite}


@router.post("/photo/{photo_id}/reject")
def reject_photo(photo_id: int, rejected: bool = Query(True), session: Session = Depends(get_db)):
    photo = session.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    photo.rejected = rejected
    session.add(photo)
    session.commit()
    return {"ok": True, "rejected": rejected}


# ---------------------------------------------------------------------------
# Groups (Stage 2)
# ---------------------------------------------------------------------------

@router.get("/groups")
def list_groups(limit: int = 50, offset: int = 0, session: Session = Depends(get_db)):
    groups = session.exec(select(PhotoGroup).order_by(PhotoGroup.start_time).offset(offset).limit(limit)).all()
    out = []
    for g in groups:
        members = session.exec(select(Photo).where(Photo.group_id == g.id)).all()
        out.append({
            "id": g.id,
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
def start(session: Session = Depends(get_db)):
    total = start_tournament(session)
    return {"status": "ok", "total_votes": total}


@router.get("/tournament/state")
def state(session: Session = Depends(get_db)):
    return tournament_state(session)


@router.get("/tournament/pair")
def pair(session: Session = Depends(get_db)):
    pair = next_pair(session)
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
# Export (Stage 4)
# ---------------------------------------------------------------------------

@router.get("/export/preview")
def export_preview(fraction: float = Query(0.3, gt=0, le=1), session: Session = Depends(get_db)):
    all_photos = session.exec(select(Photo).where(Photo.is_raw == False)).all()  # noqa: E712
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
async def start_export(fraction: float = Query(0.3, gt=0, le=1), session: Session = Depends(get_db)):
    """Launch the export in a background thread; progress via SSE."""
    from .db import ExportJob, db

    job = ExportJob(fraction=fraction, status="pending")
    session.add(job)
    session.commit()
    session.refresh(job)

    loop = asyncio.get_running_loop()

    def worker():
        with db.session() as s:
            job_obj = s.get(ExportJob, job.id)
            export.run_export(s, job_obj, fraction, config.BEST_DIR, config.PHOTOS_DIR)

    loop.run_in_executor(None, worker)
    return {"status": "started", "job_id": job.id}
