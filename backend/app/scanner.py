"""Incremental file scanner.

Scans a root folder with os.scandir() (avoids the stat() of glob), discovers
JPG/RAW pairs, extracts EXIF, and generates thumbnails. Idempotent: files whose
(path, size, mtime) identity is unchanged are skipped on re-scan.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, delete, select

from . import config
from .db import Catalogue, Photo, PhotoGroup
from .images import make_thumbnail, read_exif, thumbnail_sha1
from .progress import get_progress, set_done, set_running


def _is_photo(entry: os.DirEntry) -> bool:
    try:
        return entry.is_file() and entry.name.lower().endswith(tuple(config.IMAGE_EXTENSIONS))
    except OSError:
        return False


def _stem(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else name


def _walk(root: Path, on_found=None):
    """Yield DirEntry objects for every photo file under root, depth-first.

    `on_found` is called with the running count as files are discovered so the
    caller can update progress during the enumeration (which can be slow on a
    large or networked pool).
    """
    stack = [root]
    count = 0
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif _is_photo(entry):
                    count += 1
                    if on_found:
                        on_found(count)
                    yield entry
            except OSError:
                continue


class ScanStats:
    def __init__(self):
        self.total = 0
        self.new = 0
        self.pairs = 0


def _process_entry(entry: os.DirEntry, thumb_dir: Path) -> tuple[dict | None, int]:
    """Analyze one file entry. Returns (dict, processed_count)."""
    path = Path(entry.path)
    ext = path.suffix.lower()
    is_raw = ext in config.RAW_EXTENSIONS
    try:
        stat = entry.stat(follow_symlinks=False)
        size = stat.st_size
        mtime = stat.st_mtime
    except OSError:
        return None, 0

    rec = {
        "path": str(path),
        "stem": _stem(path.name),
        "ext": ext,
        "size": size,
        "mtime": mtime,
        "is_raw": is_raw,
    }

    processed = 1
    if is_raw:
        # ARW files are discovered but never decoded (no rawpy).
        rec["orientation"] = None
        rec["exif_datetime"] = None
        return rec, processed

    # Only JPGs get EXIF + thumbnails at scan time.
    if ext in config.THUMBNAILABLE:
        exif = read_exif(path)
        rec["exif_datetime"] = exif.get("datetime")
        rec["orientation"] = exif.get("orientation")
        sha1 = thumbnail_sha1(path, size, mtime)
        thumb_path = thumb_dir / f"{sha1}.jpg"
        if not thumb_path.exists():
            try:
                thumb_path.write_bytes(make_thumbnail(path))
            except OSError:
                thumb_path = None  # thumbnail unavailable; keep the photo
        rec["sha1"] = sha1

    return rec, processed


def _insert_photo(session: Session, catalogue: Catalogue, rec: dict) -> Photo:
    photo = Photo(catalogue_id=catalogue.id, **rec)
    session.add(photo)
    return photo


def scan(session: Session, root: Path, thumb_dir: Path | None = None, folder: str = "") -> ScanStats:
    """Run an incremental scan of `root`. Returns aggregate stats.

    When `folder` is given (a top-level folder name), the scan is scoped to
    `root` (typically PHOTOS_DIR / folder) and all photos are tagged with it.
    """
    root = root.resolve()
    thumb_dir = thumb_dir or config.THUMBNAIL_DIR
    thumb_dir.mkdir(parents=True, exist_ok=True)

    catalogue = session.exec(select(Catalogue).where(Catalogue.path == str(root))).first()
    if catalogue is None and folder:
        # Folder-scoped scan: reuse the parent catalogue (e.g. the full-tree
        # scan rooted at /photos) so the same paths aren't inserted twice.
        parent = session.exec(
            select(Catalogue).where(
                Catalogue.path != str(root),
                Catalogue.path.startswith(str(root.parent)),
            )
        ).first()
        catalogue = parent
    if catalogue is None:
        catalogue = Catalogue(path=str(root), state="scanning")
        session.add(catalogue)
        session.commit()
        session.refresh(catalogue)

    catalogue.state = "scanning"
    catalogue.updated_at = datetime.now(timezone.utc)
    session.add(catalogue)
    session.commit()

    # Report progress during the enumeration itself (can be slow on big pools).
    set_running(session, "scan", 1_000_000, folder=folder)  # unknown total; show processed count
    walked = 0

    def on_found(count: int):
        nonlocal walked
        walked = count
        if count % 50 == 0:
            row = get_progress(session, "scan", folder=folder)
            row.processed = count
            session.add(row)
            session.commit()

    entries = list(_walk(root, on_found))
    total = len(entries)
    stats = ScanStats()
    stats.total = total

    # Fix the running total now that the walk is done.
    row = get_progress(session, "scan", folder=folder)
    row.total = total
    row.processed = 0
    session.add(row)
    session.commit()

    # Load existing photos keyed by (path, size, mtime) to detect changes.
    existing: dict[tuple[str, int, float], Photo] = {}
    for photo in session.exec(select(Photo).where(Photo.catalogue_id == catalogue.id)):
        existing[(photo.path, photo.size, photo.mtime)] = photo

    # Stale photos: present in DB but no longer on disk → delete. Scoped to the
    # scanned folder so re-scanning one folder never touches others.
    disk_paths = {e.path for e in entries}
    stale = [
        p for p in existing.values()
        if p.path not in disk_paths and (not folder or p.folder == folder)
    ]
    for photo in stale:
        session.delete(photo)
    if stale:
        session.commit()

    new_recs: list[dict] = []
    existing_keys = set(existing.keys())
    for entry in entries:
        rec, processed = _process_entry(entry, thumb_dir)
        if rec is None:
            continue
        key = (rec["path"], rec["size"], rec["mtime"])
        if key not in existing_keys:
            if folder:
                rec["folder"] = folder
            new_recs.append(rec)
        else:
            stats.total -= 1  # unchanged; not part of "total to process"
            if folder:
                # Backfill the folder tag on photos already in the catalogue
                # (e.g. scanned by an earlier full-tree run with folder="").
                existing_photo = existing.get(key)
                if existing_photo and existing_photo.folder != folder:
                    existing_photo.folder = folder
                    session.add(existing_photo)
    session.commit()

    # Save new photos in batches.
    set_running(session, "scan", total, folder=folder)
    for i, rec in enumerate(new_recs, start=1):
        _insert_photo(session, catalogue, rec)
        if i % 100 == 0:
            session.commit()
    session.commit()
    stats.new = len(new_recs)

    # Pair JPG/RAW by stem (within this catalogue only).
    photos = session.exec(select(Photo).where(Photo.catalogue_id == catalogue.id)).all()
    by_stem: dict[str, list[Photo]] = {}
    for p in photos:
        by_stem.setdefault(p.stem, []).append(p)
    paired = 0
    for group in by_stem.values():
        jpgs = [p for p in group if not p.is_raw]
        raws = [p for p in group if p.is_raw]
        if jpgs and raws:
            # Link both directions: the thumbnail lives on the JPG side, and
            # export needs to find the RAW from the JPG.
            jpgs[0].paired_id = raws[0].id
            for raw in raws:
                raw.paired_id = jpgs[0].id
                paired += 1
    session.commit()
    stats.pairs = paired

    catalogue.scanned_files = len(photos)
    catalogue.state = "ready"
    catalogue.updated_at = datetime.now(timezone.utc)
    session.add(catalogue)
    session.commit()

    set_done(session, "scan", folder=folder)
    return stats
