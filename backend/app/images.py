"""Image helpers: EXIF, thumbnailing, hashing, sharpness."""

import hashlib
import io
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from . import config

# EXIF orientation tag
_EXIF_ORIENTATION = 274
_EXIF_DATETIME = 306  # "YYYY:MM:DD HH:MM:SS"
_EXIF_DATETIME_ORIGINAL = 36867


def _normalize_datetime(value) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if len(text) < 19:
        return None
    return text[:19].replace(":", "-", 2).replace(" ", "T")


def read_exif(path: Path) -> dict:
    """Return {datetime, orientation} from EXIF without decoding the pixel data."""
    result: dict = {"datetime": None, "orientation": None}
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            dt = exif.get(_EXIF_DATETIME_ORIGINAL) or exif.get(_EXIF_DATETIME)
            result["datetime"] = _normalize_datetime(dt)
            result["orientation"] = exif.get(_EXIF_ORIENTATION)
    except (UnidentifiedImageError, OSError, ValueError):
        pass
    return result


def _apply_orientation(im: Image.Image) -> Image.Image:
    """Apply EXIF orientation to an in-memory image (never rewrites the file)."""
    return ImageOps.exif_transpose(im)


def make_thumbnail(path: Path, size: int = config.THUMB_SIZE, quality: int = config.JPEG_QUALITY) -> bytes:
    """Create a square-ish JPEG thumbnail of the image at `path`."""
    with Image.open(path) as im:
        im = _apply_orientation(im)
        im.thumbnail((size, size), Image.LANCZOS)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        return buf.getvalue()


def make_preview(path: Path, size: int = 1600, quality: int = 88) -> bytes:
    """Create a preview-size JPEG (default 1600px long edge) for zooming."""
    with Image.open(path) as im:
        im = _apply_orientation(im)
        im.thumbnail((size, size), Image.LANCZOS)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        return buf.getvalue()


def thumbnail_sha1(path: Path, size: int, mtime: float, thumb_size: int = 0) -> str:
    """Content-addressed thumbnail key: (path, size, mtime, thumb_size).

    `thumb_size` is the generated thumbnail's long edge (config.THUMB_SIZE) so
    changing the thumbnail size produces a new key and regenerates thumbnails.
    """
    raw = f"{path}\0{size}\0{mtime}\0{thumb_size}".encode()
    return hashlib.sha1(raw).hexdigest()


def hash_image(data: bytes) -> dict:
    """Compute dHash and pHash from already-decoded JPEG bytes."""
    try:
        im = Image.open(io.BytesIO(data)).convert("L")
    except (UnidentifiedImageError, OSError):
        return {}
    return {
        "dhash": str(imagehash.dhash(im, hash_size=8)),
        "phash": str(imagehash.phash(im, hash_size=8)),
    }


def sharpness_score(data: bytes) -> float:
    """Laplacian variance as a sharpness score on a thumbnail-sized image."""
    try:
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return 0.0
        return float(cv2.Laplacian(img, cv2.CV_64F).var())
    except Exception:  # pragma: no cover - defensive
        return 0.0


def hamming_distance(a: str, b: str) -> int:
    """Hamming distance between two hex hash strings."""
    if not a or not b:
        return 10**9
    return sum(bin(x ^ y).count("1") for x, y in zip(bytes.fromhex(a), bytes.fromhex(b)))
