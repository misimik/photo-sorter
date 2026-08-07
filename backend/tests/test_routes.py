"""API route tests for folder-scoped endpoints."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app import scanner
from app.analyze import analyze, group
from app.db import Database, Photo
from tests.conftest import make_gradient, make_jpg


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """A TestClient whose config points at a temp photos dir + temp DB."""
    photos = tmp_path / "photos"
    photos.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    best = tmp_path / "best"
    best.mkdir()

    monkeypatch.setattr("app.config.PHOTOS_DIR", photos)
    monkeypatch.setattr("app.config.DATA_DIR", data)
    monkeypatch.setattr("app.config.BEST_DIR", best)

    # Point the module-level DB at a temp file.
    import app.db as db_mod
    from app.main import app

    engine_db = db_mod.Database(tmp_path / "test.db")
    monkeypatch.setattr(db_mod, "db", engine_db)

    def override_get_db():
        with engine_db.session() as s:
            yield s

    from app.routes import get_db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c, photos, data, best, engine_db
    app.dependency_overrides.clear()


def _seed_two_folders(photos: Path, engine_db: Database) -> None:
    (photos / "A").mkdir()
    (photos / "B").mkdir()
    make_gradient(photos / "A" / "a1.jpg", (10, 10, 10), (200, 200, 200))
    make_jpg(photos / "A" / "a2.jpg", color=(120, 40, 40))
    make_gradient(photos / "B" / "b1.jpg", (50, 50, 50), (240, 240, 240))
    thumbs = photos.parent / "data" / "thumbs"
    with engine_db.session() as s:
        scanner.scan(s, photos / "A", thumbs, folder="A")
        scanner.scan(s, photos / "B", thumbs, folder="B")
        # Give them ratings so they appear in rankings.
        for p in s.exec(select(Photo).where(Photo.folder == "A")):
            p.rating = 3
        for p in s.exec(select(Photo).where(Photo.folder == "B")):
            p.rating = 2
        s.commit()
        analyze(s, thumbs)
        group(s, folder="A")
        group(s, folder="B")


def test_folders_endpoint(client):
    c, photos, data, best, engine_db = client
    (photos / "A").mkdir()
    (photos / "B").mkdir()
    make_jpg(photos / "A" / "a.jpg")
    make_jpg(photos / "B" / "b.jpg")
    with engine_db.session() as s:
        scanner.scan(s, photos / "A", data / "thumbs", folder="A")
        scanner.scan(s, photos / "B", data / "thumbs", folder="B")

    r = c.get("/api/folders")
    assert r.status_code == 200
    assert r.json()["folders"] == ["A", "B"]


def test_groups_filtered_by_folder(client):
    c, photos, data, best, engine_db = client
    _seed_two_folders(photos, engine_db)

    r = c.get("/api/groups", params={"folder": "A"})
    assert r.status_code == 200
    groups = r.json()
    assert groups
    assert all(g["folder"] == "A" for g in groups)
    assert all(p["path"].startswith(str(photos / "A")) for g in groups for p in g["photos"])


def test_scan_requires_existing_folder(client):
    c, photos, data, best, engine_db = client
    r = c.post("/api/scan", params={"folder": "Nope"})
    assert r.status_code == 404


def test_rankings_folder_scoped(client):
    c, photos, data, best, engine_db = client
    _seed_two_folders(photos, engine_db)

    r = c.get("/api/rankings", params={"folder": "A"})
    assert r.status_code == 200
    rows = r.json()
    assert rows
    assert all(row["folder"] == "A" for row in rows)
    # ELO-descending
    elos = [row["elo"] for row in rows]
    assert elos == sorted(elos, reverse=True)
    # Tranches within 1..10
    assert all(1 <= row["tranche"] <= 10 for row in rows)

