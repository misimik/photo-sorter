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


def test_scan_with_folder_sets_folder_column(db, photos_dir, tmp_path):
    make_jpg(photos_dir / "a.jpg")
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()

    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir, folder="Trip 2023")

    with db.session() as s:
        photo = s.exec(scanner.select(Photo)).one()
        assert photo.folder == "Trip 2023"


def test_scan_folder_scoped_does_not_touch_other_folders(db, photos_dir, tmp_path):
    """Re-scanning one folder's catalogue must not delete another folder's photos."""
    sub_a = photos_dir / "A"
    sub_b = photos_dir / "B"
    sub_a.mkdir()
    sub_b.mkdir()
    make_jpg(sub_a / "a1.jpg")
    make_jpg(sub_b / "b1.jpg")
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()

    with db.session() as s:
        scanner.scan(s, sub_a, thumb_dir, folder="A")
        scanner.scan(s, sub_b, thumb_dir, folder="B")
        # Delete b1 so re-scanning A should not remove B's photo.
        (sub_b / "b1.jpg").unlink()
        scanner.scan(s, sub_a, thumb_dir, folder="A")

    with db.session() as s:
        photos = s.exec(scanner.select(Photo)).all()
        folders = {p.folder for p in photos}
        assert folders == {"A", "B"}  # B's photo survived
        assert len(photos) == 2


def test_folder_scan_reuses_parent_catalogue_no_duplicates(db, photos_dir, tmp_path):
    """Scanning a folder that's already in the full-tree catalogue must not
    insert duplicate rows for the same path."""
    sub = photos_dir / "Trip"
    sub.mkdir()
    make_jpg(sub / "x.jpg")
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()

    with db.session() as s:
        # Full-tree scan first (root catalogue).
        scanner.scan(s, photos_dir, thumb_dir)
        # Then a folder-scoped scan of the same folder.
        scanner.scan(s, sub, thumb_dir, folder="Trip")

    with db.session() as s:
        photos = s.exec(scanner.select(Photo)).all()
        assert len(photos) == 1  # no duplicates
        assert photos[0].folder == "Trip"




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
