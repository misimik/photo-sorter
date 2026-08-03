"""Stage 1 analysis: sharpness, hashing, and time-window clustering.

Runs on 256px thumbnails only. Deterministic: running it again after a partial
failure only re-does the photos that are missing analysis fields.
"""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from statistics import quantiles

from sqlmodel import Session, select

from . import config
from .db import Photo, PhotoGroup
from .images import hash_image, hamming_distance, sharpness_score
from .progress import increment_processed, set_done, set_running


def _thumb_path(sha1: str | None, thumb_dir) -> str:
    return str(thumb_dir / f"{sha1}.jpg") if sha1 else ""


def _analyze_one(photo_id: int, sha1: str | None, thumb_dir) -> dict:
    """Compute analysis fields for one photo. Thread-safe: no ORM objects."""
    path = _thumb_path(sha1, thumb_dir)
    result = {"dhash": None, "phash": None, "sharpness": None}
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return result
    hashes = hash_image(data)
    if hashes:
        result.update(hashes)
        result["sharpness"] = sharpness_score(data)
    return result


def analyze(session: Session, thumb_dir) -> int:
    """Compute hashes + sharpness for all non-raw photos missing them."""
    photos = session.exec(
        select(Photo).where(Photo.is_raw == False, Photo.analyzed == False)  # noqa: E712
    ).all()
    set_running(session, "analyze", len(photos))

    jobs = [(p.id, p.sha1) for p in photos]
    results: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
        futures = {pool.submit(_analyze_one, pid, sha1, thumb_dir): pid for pid, sha1 in jobs}
        for future in futures:
            pid = futures[future]
            try:
                results[pid] = future.result()
            except Exception:
                continue

    done = 0
    for p in photos:
        result = results.get(p.id)
        if result is None:
            continue
        p.dhash = result["dhash"]
        p.phash = result["phash"]
        p.sharpness = result["sharpness"]
        p.analyzed = True
        session.add(p)
        done += 1
    session.commit()

    from .progress import get_progress
    row = get_progress(session, "analyze")
    row.processed += done
    row.status = "done"
    session.add(row)
    session.commit()

    return len(photos)


def _flag_blurry(session: Session, photos: list[Photo]) -> None:
    """Flag the bottom SHARPNESS_PERCENTILE of photos as blurry."""
    scores = sorted(p.sharpness for p in photos if p.sharpness is not None)
    if len(scores) < 10:
        return  # not enough data to be meaningful
    idx = max(0, int(len(scores) * config.SHARPNESS_PERCENTILE / 100) - 1)
    threshold = scores[idx]
    for p in photos:
        if p.sharpness is not None and p.sharpness <= threshold:
            p.is_blurry = True
        elif p.sharpness is not None:
            p.is_blurry = False
        session.add(p)
    session.commit()


def _time_key(photo: Photo) -> datetime:
    if photo.exif_datetime:
        try:
            return datetime.fromisoformat(photo.exif_datetime).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(photo.mtime, tz=timezone.utc)


def cluster(photos: list[Photo]) -> list[list[Photo]]:
    """Sort chronologically, slice into time windows, cluster by dHash distance."""
    if not photos:
        return []
    ordered = sorted(photos, key=_time_key)
    windows: list[list[Photo]] = []
    window: list[Photo] = []
    window_start: datetime | None = None
    for p in ordered:
        t = _time_key(p)
        if window_start is None or (t - window_start).total_seconds() > config.TIME_WINDOW_SECONDS:
            if window:
                windows.append(window)
            window = [p]
            window_start = t
        else:
            window.append(p)
    if window:
        windows.append(window)

    # Within each window, chain photos whose dHash distance < threshold.
    groups: list[list[Photo]] = []
    for win in windows:
        if len(win) == 1:
            groups.append(win)
            continue
        remaining = list(win)
        while remaining:
            seed = remaining.pop(0)
            group = [seed]
            for other in list(remaining):
                if hamming_distance(seed.dhash or "", other.dhash or "") < config.DHASH_DISTANCE:
                    group.append(other)
                    remaining.remove(other)
            groups.append(group)
    return groups


def _attach_singletons(ordered: list[Photo], groups: list[list[Photo]]) -> list[list[Photo]]:
    """Merge groups of size 1 into the chronologically nearest group."""
    result = [g for g in groups if len(g) > 1]
    singles = [g[0] for g in groups if len(g) == 1]
    for s in singles:
        if not result:
            result.append([s])
            continue
        best = min(result, key=lambda g: abs(_time_key(g[0]).timestamp() - _time_key(s).timestamp()))
        best.append(s)
    return result


def group(session: Session) -> int:
    """Regroup all analyzed photos into PhotoGroups (deterministic)."""
    # Clear previous groups.
    photos = session.exec(select(Photo)).all()
    old_group_ids = {p.group_id for p in photos if p.group_id}
    for gid in old_group_ids:
        g = session.get(PhotoGroup, gid)
        if g:
            session.delete(g)
    for p in photos:
        p.group_id = None
    session.commit()

    candidates = [p for p in photos if not p.is_raw and p.analyzed]
    clusters = cluster(candidates)
    clusters = _attach_singletons(sorted(candidates, key=_time_key), clusters)
    set_running(session, "group", len(clusters))

    created = 0
    for cluster_list in clusters:
        pg = PhotoGroup(
            start_time=min(_time_key(p) for p in cluster_list),
            end_time=max(_time_key(p) for p in cluster_list),
        )
        session.add(pg)
        session.commit()
        session.refresh(pg)
        for p in cluster_list:
            p.group_id = pg.id
            session.add(p)
        created += 1
        increment_processed(session, "group")
    session.commit()
    set_done(session, "group")
    return created
