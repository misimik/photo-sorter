from app import scanner
from app.db import Photo
from app.tournament import (
    elo_change,
    expected,
    next_pair,
    resolve_match,
    seed_elo,
    start_tournament,
)
from sqlmodel import select
from tests.conftest import make_jpg


def test_elo_formulas():
    # Equal ratings -> 0.5 expected, winner gains K/2.
    assert expected(1500, 1500) == 0.5
    assert elo_change(1500, 1500) == round(32 * 0.5)
    # Upset: much weaker player beating a much stronger one gains more.
    assert elo_change(1000, 1800) > elo_change(1800, 1000)


def test_seed_elo_mapping():
    p = Photo(path="x.jpg", stem="x", ext=".jpg", rating=5, favorite=True)
    assert seed_elo(p) == 1900
    p2 = Photo(path="y.jpg", stem="y", ext=".jpg", rating=3, favorite=False)
    assert seed_elo(p2) == 1400


def _rated_photos(db, photos_dir, n=3):
    thumb_dir = photos_dir.parent / "thumbs"
    thumb_dir.mkdir(exist_ok=True)
    for i in range(n):
        make_jpg(photos_dir / f"p{i}.jpg", color=(i * 40, 60, 60))
    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir)
        photos = s.exec(select(Photo)).all()
        for p in photos:
            p.rating = 3
        s.commit()
        return [p.id for p in photos]


def test_next_pair_and_resolve(db, photos_dir):
    ids = _rated_photos(db, photos_dir)
    with db.session() as s:
        start_tournament(s)
        pair = next_pair(s)
        assert pair is not None
        a, b = pair
        a_elo = a.elo
        resolve_match(s, a, b)
        assert a.views == 1
        assert a.elo > a_elo  # winner gained rating


def test_tournament_exhausts_views(db, photos_dir):
    ids = _rated_photos(db, photos_dir, n=3)
    with db.session() as s:
        start_tournament(s)
        # 3 photos * 4 views = 12 votes max; each match uses 2 views.
        votes = 0
        while True:
            pair = next_pair(s)
            if pair is None:
                break
            resolve_match(s, pair[0], pair[1])
            votes += 1
        assert votes >= 5  # at least enough to exhaust most photos
        photos = s.exec(select(Photo)).all()
        assert all(p.views <= 10 for p in photos)
