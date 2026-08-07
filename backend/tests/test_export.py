import os
from pathlib import Path

from app import scanner
from app.db import ExportJob, Photo
from app.export import run_export
from sqlmodel import select
from tests.conftest import make_arw, make_jpg


def _scan_rated(db, photos_dir, n=4, with_raw=False):
    thumb_dir = photos_dir.parent / "thumbs"
    thumb_dir.mkdir(exist_ok=True)
    for i in range(n):
        make_jpg(photos_dir / f"IMG{i}.jpg", color=(i * 30, 90, 90))
        if with_raw:
            make_arw(photos_dir / f"IMG{i}.ARW")
    with db.session() as s:
        scanner.scan(s, photos_dir, thumb_dir)
        photos = s.exec(select(Photo).where(Photo.is_raw == False)).all()  # noqa: E712
        for j, p in enumerate(photos):
            p.elo = 1600 - j * 100  # descending, deterministic ranking
            p.rating = 3  # so they're "rated" (export filters rating > 0)
        s.commit()
        return photos


def test_export_top_fraction(db, photos_dir, tmp_path):
    _scan_rated(db, photos_dir, n=4)
    best = tmp_path / "best"
    best.mkdir()

    with db.session() as s:
        job = ExportJob(fraction=0.5, status="pending")
        s.add(job)
        s.commit()
        s.refresh(job)
        job = run_export(s, job, 5, best, photos_dir)  # tranche 5 = top 50%
        assert job.status == "done"

    files = list(best.glob("*.jpg"))
    assert len(files) == 2  # top 50% of 4
    assert (best / "manifest.txt").exists()
    manifest = (best / "manifest.txt").read_text()
    assert "IMG0" in manifest  # highest ELO exported first


def test_export_skips_existing_idempotent(db, photos_dir, tmp_path):
    _scan_rated(db, photos_dir, n=3)
    best = tmp_path / "best"
    best.mkdir()

    with db.session() as s:
        job = ExportJob(fraction=1.0, status="pending")
        s.add(job)
        s.commit()
        s.refresh(job)
        run_export(s, job, 10, best, photos_dir)  # all 10 tranches

    with db.session() as s:
        job = ExportJob(fraction=1.0, status="pending")
        s.add(job)
        s.commit()
        s.refresh(job)
        job = run_export(s, job, 10, best, photos_dir)
        assert job.status == "done"
    assert len(list(best.glob("*.jpg"))) == 3


def test_export_includes_paired_raw(db, photos_dir, tmp_path):
    _scan_rated(db, photos_dir, n=2, with_raw=True)
    best = tmp_path / "best"
    best.mkdir()

    with db.session() as s:
        job = ExportJob(fraction=1.0, status="pending")
        s.add(job)
        s.commit()
        s.refresh(job)
        run_export(s, job, 10, best, photos_dir)

    jpgs = list(best.glob("*.jpg"))
    raws = list(best.glob("*.ARW"))
    assert len(jpgs) == 2
    assert len(raws) == 2
