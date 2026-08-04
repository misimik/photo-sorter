from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import select

from app.db import Database, Photo, PhotoGroup, Progress, migrate_folder_columns
from tests.conftest import make_jpg


def _make_old_schema_db(tmp_path: Path) -> Database:
    """Create a DB with the PRE-rework schema (no folder columns, unique stage)."""
    import sqlite3

    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE catalogue (
            id INTEGER PRIMARY KEY,
            path VARCHAR NOT NULL UNIQUE,
            total_files INTEGER NOT NULL DEFAULT 0,
            scanned_files INTEGER NOT NULL DEFAULT 0,
            state VARCHAR NOT NULL DEFAULT 'pending',
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
        CREATE TABLE photo (
            id INTEGER PRIMARY KEY,
            catalogue_id INTEGER NOT NULL,
            path VARCHAR NOT NULL,
            stem VARCHAR NOT NULL,
            ext VARCHAR NOT NULL,
            size INTEGER NOT NULL DEFAULT 0,
            mtime FLOAT NOT NULL DEFAULT 0,
            sha1 VARCHAR,
            is_raw BOOLEAN NOT NULL DEFAULT 0,
            paired_id INTEGER,
            exif_datetime VARCHAR,
            orientation INTEGER,
            width INTEGER,
            height INTEGER,
            dhash VARCHAR,
            phash VARCHAR,
            sharpness FLOAT,
            is_blurry BOOLEAN,
            rating INTEGER NOT NULL DEFAULT 0,
            favorite BOOLEAN NOT NULL DEFAULT 0,
            rejected BOOLEAN NOT NULL DEFAULT 0,
            elo INTEGER NOT NULL DEFAULT 1500,
            views INTEGER NOT NULL DEFAULT 0,
            group_id INTEGER,
            analyzed BOOLEAN NOT NULL DEFAULT 0
        );
        CREATE TABLE photogroup (
            id INTEGER PRIMARY KEY,
            start_time DATETIME,
            end_time DATETIME
        );
        CREATE TABLE progress (
            id INTEGER PRIMARY KEY,
            stage VARCHAR NOT NULL UNIQUE,
            total INTEGER NOT NULL DEFAULT 0,
            processed INTEGER NOT NULL DEFAULT 0,
            status VARCHAR NOT NULL DEFAULT 'idle',
            error VARCHAR,
            updated_at DATETIME NOT NULL
        );
        """
    )
    conn.close()
    return Database(db_path)


def test_migration_adds_columns_to_old_schema(tmp_path):
    """The deployed DB had no folder columns; migration must ALTER TABLE them in."""
    photos = tmp_path / "photos"
    (photos / "Trip A").mkdir(parents=True)
    make_jpg(photos / "Trip A" / "x.jpg")

    db = _make_old_schema_db(tmp_path)
    with db.session() as s:
        s.exec(text("INSERT INTO catalogue (path, state, created_at, updated_at) VALUES ('/photos', 'ready', '2026-01-01', '2026-01-01')"))
        s.exec(text("INSERT INTO photo (catalogue_id, path, stem, ext, size, mtime) VALUES (1, '/photos/Trip A/x.jpg', 'x', '.jpg', 10, 1000.0)"))
        s.exec(text("INSERT INTO progress (stage, status, updated_at) VALUES ('scan', 'done', '2026-01-01')"))
        s.commit()

        # The migration must succeed and backfill the folder column.
        migrate_folder_columns(s, photos)

        photo = s.exec(select(Photo)).one()
        assert photo.folder == "Trip A"
        prog_rows = s.exec(select(Progress)).all()
        assert len(prog_rows) == 1  # existing row preserved
