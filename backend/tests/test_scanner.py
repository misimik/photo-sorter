from app import scanner
from app.db import Catalogue, Photo
from app.images import thumbnail_sha1
from tests.conftest import make_arw, make_jpg


def test_scan_creates_photos_and_thumbnails(db, photos_dir, tmp_path):
    make_jpg(photos_dir / "IMG_0001.jpg")
    make_jpg(photos_dir / "IMG_0002.jpg")
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()

    with db.session() as s:
        stats = scanner.scan(s, photos_dir, thumb_dir)

    assert stats.total == 2
    assert stats.new == 2
    assert stats.pairs == 0

    with db.session() as s:
        photos = s.exec(scanner.select(Photo).where(Photo.catalogue_id != None)).all()  # noqa: E711
        assert len(photos) == 2
        cat = s.exec(scanner.select(Catalogue)).first()
        assert cat.state == "ready"
        assert cat.scanned_files == 2
        for p in photos:
            assert p.sha1
            assert (thumb_dir / f"{p.sha1}.jpg").exists()


def test_scan_idempotent_second_run(db, photos_dir, tmp_path):
    make_jpg(photos_dir / "a.jpg")
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()

    with db.session() as s:
        first = scanner.scan(s, photos_dir, thumb_dir)
    with db.session() as s:
        second = scanner.scan(s, photos_dir, thumb_dir)

    assert first.new == 1
    assert second.new == 0
    with db.session() as s:
        assert len(s.exec(scanner.select(Photo)).all()) == 1


def test_scan_detects_changed_and_stale(db, photos_dir, tmp_path):
    f = make_jpg(photos_dir / "a.jpg")
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()

    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir)

    # Change the file -> re-scan picks it up as new.
    f.write_bytes(b"CHANGED-CONTENT")
    with db.session() as s:
        stats = scanner.scan(s, photos_dir, thumb_dir)
    assert stats.new == 1

    # Delete it -> stale removal.
    f.unlink()
    with db.session() as s:
        stats = scanner.scan(s, photos_dir, thumb_dir)
        assert stats.new == 0
        assert len(s.exec(scanner.select(Photo)).all()) == 0


def test_scan_pairs_raw_with_jpg(db, photos_dir, tmp_path):
    make_jpg(photos_dir / "DSC1234.JPG")
    make_arw(photos_dir / "DSC1234.ARW")
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()

    with db.session() as s:
        stats = scanner.scan(s, photos_dir, thumb_dir)

    assert stats.pairs == 1
    with db.session() as s:
        jpg = s.exec(scanner.select(Photo).where(Photo.ext == ".jpg")).one()
        raw = s.exec(scanner.select(Photo).where(Photo.ext == ".arw")).one()
        assert raw.paired_id == jpg.id
        assert raw.is_raw is True
        # RAW is discovered but never decoded/thumbnailed.
        assert raw.sha1 is None
