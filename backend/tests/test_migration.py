from pathlib import Path

from sqlmodel import select

from app.db import Photo, PhotoGroup, migrate_folder_columns
from app import scanner
from tests.conftest import make_jpg


def test_migration_backfills_folder_from_path(db, photos_dir, tmp_path):
    """Photos with empty folder get it derived from their path."""
    (photos_dir / "Trip A").mkdir()
    make_jpg(photos_dir / "Trip A" / "x.jpg")
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()

    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir)
        # Simulate a pre-migration DB: folder is empty on existing rows.
        for p in s.exec(select(Photo)).all():
            p.folder = ""
        s.commit()
        migrate_folder_columns(s, photos_dir)

    with db.session() as s:
        photo = s.exec(select(Photo)).one()
        assert photo.folder == "Trip A"


def test_migration_is_idempotent(db, photos_dir, tmp_path):
    (photos_dir / "Trip A").mkdir()
    make_jpg(photos_dir / "Trip A" / "x.jpg")
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()

    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir)
        migrate_folder_columns(s, photos_dir)
        migrate_folder_columns(s, photos_dir)  # second run is a no-op

    with db.session() as s:
        photo = s.exec(select(Photo)).one()
        assert photo.folder == "Trip A"
