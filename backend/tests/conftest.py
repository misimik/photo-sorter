"""Shared fixtures: a temp photos dir with generated test images."""

import io
from pathlib import Path

import pytest
from PIL import Image

from app.db import Database


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def db(db_path: Path) -> Database:
    return Database(db_path)


def make_jpg(path: Path, color: tuple[int, int, int] = (200, 120, 40), size: tuple[int, int] = (640, 480)) -> Path:
    """Create a deterministic small JPEG (used for thumbnails and analysis)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    img.save(path, "JPEG", quality=90)
    return path


def make_gradient(path: Path, start: tuple[int, int, int], end: tuple[int, int, int], size: tuple[int, int] = (640, 480)) -> Path:
    """Create a JPEG with a linear gradient — has texture for dHash separation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size)
    w, h = size
    for y in range(h):
        t = y / max(1, h - 1)
        row = tuple(int(s + (e - s) * t) for s, e in zip(start, end))
        for x in range(0, w, 16):
            img.paste(row, (x, y, min(x + 16, w), y + 1))
    img.save(path, "JPEG", quality=90)
    return path


def make_checkerboard(path: Path, cell: int = 40, size: tuple[int, int] = (640, 480)) -> Path:
    """High-frequency checkerboard — very different dHash from smooth gradients."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("L", size)
    w, h = size
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = 0 if ((x // cell) + (y // cell)) % 2 == 0 else 255
    img.save(path, "JPEG", quality=90)
    return path


def make_arw(path: Path, content: bytes = b"FAKE-ARW-BINARY") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture()
def photos_dir(tmp_path: Path) -> Path:
    d = tmp_path / "photos"
    d.mkdir()
    return d


def make_catalogue(tmp_path: Path) -> tuple[Path, Path]:
    """Return (photos_dir, thumb_dir) with a ready-to-scan tree."""
    photos = tmp_path / "photos"
    photos.mkdir()
    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    return photos, thumbs
