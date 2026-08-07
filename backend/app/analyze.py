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


def analyze(session: Session, thumb_dir, folder: str | None = None) -> int:
    """Compute hashes + sharpness for non-raw photos missing them.

    When `folder` is given, only photos in that folder are analyzed.
    """
    query = select(Photo).where(Photo.is_raw == False, Photo.analyzed == False)  # noqa: E712
    if folder:
        query = query.where(Photo.folder == folder)
    photos = session.exec(query).all()
    set_running(session, "analyze", len(photos), folder=folder or "")

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
    row = get_progress(session, "analyze", folder=folder or "")
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
    """Group photos into series + single batches using a connected-components graph.

    For every pair within TIME_WINDOW_SECONDS, an edge is created if both
    subject (pHash) and a weighted combined score (subject + framing + time)
    cross their thresholds. Connected components are series; components of
    size 1 have no similar neighbors and are batched into groups of
    SINGLE_BATCH_SIZE for review context.
    """
    if not photos:
        return []
    ordered = sorted(photos, key=_time_key)
    n = len(ordered)

    # Build symmetric adjacency graph.
    adj: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        ti = _time_key(ordered[i])
        for j in range(i + 1, n):
            tj = _time_key(ordered[j])
            gap = (tj - ti).total_seconds()
            if gap > config.TIME_WINDOW_SECONDS:
                break  # photos are time-sorted; rest are farther

            subject_dist = hamming_distance(ordered[i].phash or "", ordered[j].phash or "")
            framing_dist = hamming_distance(ordered[i].dhash or "", ordered[j].dhash or "")
            subject_score = 1.0 - subject_dist / 64.0
            framing_score = 1.0 - framing_dist / 64.0
            time_score = 1.0 - gap / config.TIME_WINDOW_SECONDS
            combined = (
                subject_score * config.SUBJECT_WEIGHT
                + framing_score * config.FRAMING_WEIGHT
                + time_score * config.TIME_WEIGHT
            )
            if subject_score >= config.SUBJECT_THRESHOLD and combined >= config.COMBINED_THRESHOLD:
                adj[i].append(j)
                adj[j].append(i)

    # Find connected components via BFS.
    visited = [False] * n
    components: list[list[Photo]] = []
    for i in range(n):
        if visited[i]:
            continue
        queue = [i]
        visited[i] = True
        component: list[Photo] = []
        while queue:
            node = queue.pop(0)
            component.append(ordered[node])
            for neighbor in adj[node]:
                if not visited[neighbor]:
                    visited[neighbor] = True
                    queue.append(neighbor)
        components.append(component)

    # Split into series (size > 1) and singles (size 1).
    series: list[list[Photo]] = []
    singles: list[Photo] = []
    for comp in components:
        if len(comp) > 1:
            # Cap at MAX_SERIES_SIZE by splitting on time.
            sorted_comp = sorted(comp, key=_time_key)
            for k in range(0, len(sorted_comp), config.MAX_SERIES_SIZE):
                series.append(sorted_comp[k : k + config.MAX_SERIES_SIZE])
        else:
            singles.append(comp[0])

    # Batch singles by time into groups of SINGLE_BATCH_SIZE.
    single_batches: list[list[Photo]] = []
    for i in range(0, len(singles), config.SINGLE_BATCH_SIZE):
        single_batches.append(singles[i : i + config.SINGLE_BATCH_SIZE])

    return series + single_batches


def group(session: Session, folder: str | None = None) -> int:
    """Regroup analyzed photos into PhotoGroups (deterministic).

    When `folder` is given, only that folder's photos are regrouped and only
    that folder's previous groups are cleared — other folders are untouched.
    """
    # Clear previous groups for this folder (or all, when folder is None).
    # Null out group_id on ALL photos that reference the groups being removed
    # BEFORE deleting them — SQLite foreign_keys=ON forbids deleting a group
    # that photos still point at.
    photos = session.exec(select(Photo)).all()
    old_group_ids = {
        p.group_id for p in photos
        if p.group_id and (not folder or p.folder == folder)
    }
    for p in photos:
        if p.group_id in old_group_ids:
            p.group_id = None
            session.add(p)
    session.commit()
    for gid in old_group_ids:
        g = session.get(PhotoGroup, gid)
        if g:
            session.delete(g)
    session.commit()

    candidates = [p for p in photos if not p.is_raw and p.analyzed and (not folder or p.folder == folder)]
    clusters = cluster(candidates)
    set_running(session, "group", len(clusters), folder=folder or "")

    created = 0
    for cluster_list in clusters:
        pg = PhotoGroup(
            folder=folder or "",
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
        increment_processed(session, "group", folder=folder or "")
    session.commit()
    set_done(session, "group", folder=folder or "")
    return created
