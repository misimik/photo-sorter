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
    increment_processed(session, "tournament")
    return match


def _rated_photo(session: Session, exclude_ids: set[int]) -> Photo | None:
    photos = session.exec(
        select(Photo).where(
            Photo.rating >= 1,
            Photo.views < config.MAX_VIEWS,
        )
    ).all()
    remaining = [p for p in photos if p.id not in exclude_ids and not p.rejected]
    if not remaining:
        return None
    return random.choice(remaining)


def next_pair(session: Session) -> tuple[Photo, Photo] | None:
    """Pick two rated photos that haven't maxed out their views."""
    a = _rated_photo(session, set())
    if a is None:
        return None
    b = _rated_photo(session, {a.id})
    if b is None:
        return None
    return (a, b)


def start_tournament(session: Session) -> int:
    """Seed ELO for all rated photos; return the total number of votes."""
    photos = session.exec(select(Photo).where(Photo.rating >= 1)).all()
    for p in photos:
        p.elo = seed_elo(p)
        p.views = 0
        session.add(p)
    session.commit()
    total = len(photos) * config.MAX_VIEWS
    set_running(session, "tournament", total)
    return total


def tournament_state(session: Session) -> dict:
    rated = session.exec(select(Photo).where(Photo.rating >= 1)).all()
    total_votes = len(rated) * config.MAX_VIEWS
    votes_done = sum(p.views for p in rated)
    return {
        "total_votes": total_votes,
        "votes_done": votes_done,
        "rated_count": len(rated),
        "max_views": config.MAX_VIEWS,
    }
