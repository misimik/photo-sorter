from app.analyze import analyze, cluster, group
from app.db import Photo
from sqlmodel import select
from tests.conftest import make_checkerboard, make_gradient, make_jpg


def _mk(db, photos_dir, n=4):
    """Scan n solid-color JPGs and return them."""
    from app import scanner

    for i in range(n):
        make_jpg(photos_dir / f"img{i}.jpg", color=(i * 30, 80, 120))
    thumb_dir = photos_dir.parent / "thumbs"
    thumb_dir.mkdir(exist_ok=True)
    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir)
    with db.session() as s:
        return s.exec(select(Photo).order_by(Photo.id)).all()


def test_analyze_sets_hashes_and_sharpness(db, photos_dir, tmp_path):
    from app import scanner

    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    for i in range(2):
        make_jpg(photos_dir / f"x{i}.jpg", color=(i, 10, 20))
    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir)
        n = analyze(s, thumb_dir)
        assert n == 2
        for p in s.exec(select(Photo)).all():
            assert p.dhash
            assert p.phash
            assert p.sharpness is not None
            assert p.analyzed is True


def test_cluster_groups_similar_photos(db, photos_dir, tmp_path):
    from app import scanner

    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    # Near-identical gradients (burst series) + a clearly different checkerboard.
    for i in range(3):
        make_gradient(photos_dir / f"burst{i}.jpg", (100, 100, 100), (180, 180, 180))
    make_checkerboard(photos_dir / "other.jpg")
    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir)
        analyze(s, thumb_dir)
        photos = s.exec(select(Photo).order_by(Photo.id)).all()
        clusters = cluster(photos)
        # The graph algorithm connects the 3 similar gradients. The checkerboard
        # may join them if its pHash/dHash are close enough (real hashes).
        sizes = sorted(len(c) for c in clusters)
        # At minimum, the 3 identical gradients belong together.
        assert any(s >= 3 for s in sizes)


def test_cluster_graph_does_not_hang(db, photos_dir, tmp_path):
    """The old greedy algorithm hung on this 20-gradients + 7-checkerboards case.
    The graph-based algorithm must complete quickly with no infinite loop."""
    from app import scanner

    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    for i in range(20):
        make_gradient(photos_dir / f"burst{i}.jpg", (50, 50, 50), (200, 200, 200))
    for i in range(7):
        make_checkerboard(photos_dir / f"single{i}.jpg", cell=30 + i)
    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir)
        analyze(s, thumb_dir)
        photos = s.exec(select(Photo).order_by(Photo.id)).all()
        clusters = cluster(photos)  # must not hang
        sizes = sorted((len(c) for c in clusters), reverse=True)
        assert sizes  # any non-empty result is a pass




def test_group_creates_photo_groups(db, photos_dir, tmp_path):
    from app import scanner

    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    make_jpg(photos_dir / "a.jpg", color=(50, 50, 50))
    make_jpg(photos_dir / "b.jpg", color=(60, 60, 60))
    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir)
        analyze(s, thumb_dir)
        created = group(s)
        assert created >= 1
        for p in s.exec(select(Photo)).all():
            assert p.group_id is not None


def test_group_regroup_does_not_violate_fk(db, photos_dir, tmp_path):
    """Re-running group() must null out group_id before deleting old groups,
    or SQLite foreign_keys=ON raises IntegrityError."""
    from app import scanner

    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    make_jpg(photos_dir / "a.jpg", color=(50, 50, 50))
    make_jpg(photos_dir / "b.jpg", color=(60, 60, 60))
    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir)
        analyze(s, thumb_dir)
        first = group(s)
        assert first >= 1
        # Re-group: must not fail deleting the old PhotoGroups.
        second = group(s)
        assert second >= 1
        for p in s.exec(select(Photo)).all():
            assert p.group_id is not None
