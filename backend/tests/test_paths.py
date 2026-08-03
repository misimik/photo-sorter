import os
from pathlib import Path

import pytest

from app.paths import resolve_within


def test_resolve_within_allows_inside(tmp_path: Path):
    root = tmp_path / "photos"
    root.mkdir()
    f = root / "sub" / "a.jpg"
    f.parent.mkdir()
    f.write_bytes(b"x")
    assert resolve_within(root, f) == f.resolve()


def test_resolve_within_rejects_escape(tmp_path: Path):
    root = tmp_path / "photos"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"secret")
    with pytest.raises(ValueError):
        resolve_within(root, str(outside))


def test_resolve_within_rejects_dotdot(tmp_path: Path):
    root = tmp_path / "photos"
    root.mkdir()
    with pytest.raises(ValueError):
        resolve_within(root, "../secret.txt")


def test_resolve_within_rejects_missing(tmp_path: Path):
    root = tmp_path / "photos"
    root.mkdir()
    with pytest.raises(ValueError):
        resolve_within(root, "nope.jpg")
