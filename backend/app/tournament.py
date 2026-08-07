"""Tournament engine: ELO seeding, matchmaking, and match resolution."""

import random

from sqlmodel import Session, select

from . import config
from .db import Photo, TournamentMatch
from .progress import increment_processed, set_done, set_running


def seed_elo(photo: Photo) -> int:
    """Map review ratings to starting ELO."""
    if photo.rating <= 0:
        return config.ELO_BASE
    base = config.RATED_ELO.get(photo.rating, config.ELO_BASE)
    return base + (config.FAVORITE_BONUS if photo.favorite else 0)


def expected(elo_a: int, elo_b: int) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400))


def elo_change(winner: int, loser: int) -> int:
    e = expected(winner, loser)
    return round(config.ELO_K * (1.0 - e))


def resolve_match(session: Session, winner: Photo, loser: Photo) -> TournamentMatch:
    """Apply a win/loss between two photos; persist ELO + match row."""
    w_before = winner.elo
    l_before = loser.elo
    change = elo_change(w_before, l_before)
    winner.elo = w_before + change
    loser.elo = l_before - change
    winner.views += 1
    loser.views += 1
    match = TournamentMatch(
        left_id=winner.id,
        right_id=loser.id,
        winner_id=winner.id,
        left_elo_before=w_before,
        right_elo_before=l_before,
    )
    session.add_all([winner, loser, match])
    session.commit()
    folder = winner.folder or ""
    increment_processed(session, "tournament", folder=folder)
    return match


def _folder_filter(query, folder: str | None):
    return query if not folder else query.where(Photo.folder == folder)


def _rated_photo(session: Session, folder: str | None, exclude_ids: set[int], min_stars: int = 1) -> Photo | None:
    query = select(Photo).where(
        Photo.rating >= min_stars,
        Photo.views < config.MAX_VIEWS,
    )
    query = _folder_filter(query, folder)
    photos = session.exec(query).all()
    remaining = [p for p in photos if p.id not in exclude_ids and not p.rejected]
    if not remaining:
        return None
    return random.choice(remaining)


def next_pair(session: Session, folder: str | None = None, min_stars: int = 1) -> tuple[Photo, Photo] | None:
    """Pick two rated photos (in `folder`) that haven't maxed their views.

    Preference: same-group photos pair first so burst/duplicate shots are
    compared against each other before competing with different scenes.
    """
    a = _rated_photo(session, folder, set(), min_stars)
    if a is None:
        return None

    # Prefer a photo from the same review group (burst/duplicate matchup).
    if a.group_id:
        same_group_query = select(Photo).where(
            Photo.rating >= min_stars,
            Photo.views < config.MAX_VIEWS,
            Photo.group_id == a.group_id,
            Photo.id != a.id,
            Photo.rejected == False,  # noqa: E712
        )
        same_group_query = _folder_filter(same_group_query, folder)
        same = session.exec(same_group_query).all()
        if same:
            return (a, random.choice(same))

    # Fall back to random pairing.
    b = _rated_photo(session, folder, {a.id}, min_stars)
    if b is None:
        return None
    return (a, b)


def start_tournament(session: Session, folder: str | None = None, min_stars: int = 1) -> int:
    """Seed ELO for rated photos (in `folder`, >= `min_stars` stars); return total votes."""
    query = select(Photo).where(Photo.rating >= min_stars)
    query = _folder_filter(query, folder)
    photos = session.exec(query).all()
    for p in photos:
        p.elo = seed_elo(p)
        p.views = 0
        session.add(p)
    session.commit()
    total = len(photos) * config.MAX_VIEWS
    set_running(session, "tournament", total, folder=folder or "")
    return total


def tournament_state(session: Session, folder: str | None = None, min_stars: int = 1) -> dict:
    query = select(Photo).where(Photo.rating >= min_stars)
    query = _folder_filter(query, folder)
    rated = session.exec(query).all()
    total_votes = len(rated) * config.MAX_VIEWS
    votes_done = sum(p.views for p in rated)
    return {
        "total_votes": total_votes,
        "votes_done": votes_done,
        "rated_count": len(rated),
        "max_views": config.MAX_VIEWS,
    }
