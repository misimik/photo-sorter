"""Non-destructive export worker: copy selected photos + manifest."""

import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from . import config
from .db import ExportJob, Photo
from .paths import resolve_within
from .progress import set_done, set_error, set_running


def _copy_one(src: Path, dst: Path) -> None:
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)  # preserves metadata


def _manifest_rows(session: Session, photos: list[Photo]) -> list[str]:
    lines = [
        "# Photo Sorter export manifest",
        f"# exported_at: {datetime.now(timezone.utc).isoformat()}",
        "# original_path\telo",
    ]
    for p in sorted(photos, key=lambda x: x.elo, reverse=True):
        lines.append(f"{p.path}\t{p.elo}")
    return lines


def run_export(session: Session, job: ExportJob, fraction: float, best_dir: Path, photos_dir: Path, folder: str | None = None) -> ExportJob:
    """Copy the top `fraction` of photos (in `folder`) to Best/<folder>/, with manifest.

    Output lands in `best_dir / folder` (or `best_dir` flat when folder is None),
    preserving relative subpaths, so exports from different folders never collide.
    """
    job.fraction = fraction
    job.status = "running"
    session.add(job)
    session.commit()

    query = select(Photo).where(Photo.is_raw == False, Photo.skipped == False)  # noqa: E712
    if folder:
        query = query.where(Photo.folder == folder)
    all_photos = session.exec(query).all()
    ranked = sorted(all_photos, key=lambda p: p.elo, reverse=True)
    keep_count = max(1, int(len(ranked) * fraction))
    keep = ranked[:keep_count]

    # Expand each kept JPG to include its paired RAW.
    to_copy: list[Photo] = []
    for p in keep:
        to_copy.append(p)
        if p.paired_id:
            raw = session.get(Photo, p.paired_id)
            if raw and raw.is_raw:
                to_copy.append(raw)

    # De-duplicate (same file can pair with multiple JPGs in theory).
    seen: set[str] = set()
    unique: list[Photo] = []
    for p in to_copy:
        if p.path not in seen:
            seen.add(p.path)
            unique.append(p)

    total = len(unique)
    set_running(session, "export", total, folder=folder or "")
    job.total = total
    session.add(job)
    session.commit()

    # Destination root: Best/<folder>/ preserving the relative layout.
    dest_root = (best_dir / folder) if folder else best_dir
    src_root = (photos_dir / folder) if folder else photos_dir

    errors: list[str] = []
    copied = 0

    def copy_photo(path: str) -> bool:
        try:
            src = resolve_within(photos_dir, path)
        except ValueError as exc:
            errors.append(str(exc))
            return False
        rel = src.relative_to(src_root)
        dst = dest_root / rel
        _copy_one(src, dst)
        return True

    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
        futures = {pool.submit(copy_photo, p.path): p for p in unique}
        for future in futures:
            try:
                if future.result():
                    copied += 1
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(str(exc))

    from .progress import get_progress
    row = get_progress(session, "export", folder=folder or "")
    row.processed += copied
    row.total = total
    session.add(row)
    session.commit()

    # Atomic manifest write.
    manifest = dest_root / "manifest.txt"
    tmp = dest_root / "manifest.txt.tmp"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("\n".join(_manifest_rows(session, keep)) + "\n")
    os.replace(tmp, manifest)

    job.copied = copied
    job.manifest_path = str(manifest)
    if errors:
        job.status = "error"
        job.error = "; ".join(errors[:5])
        set_error(session, "export", job.error, folder=folder or "")
    else:
        job.status = "done"
        set_done(session, "export", folder=folder or "")
    session.add(job)
    session.commit()
    return job
