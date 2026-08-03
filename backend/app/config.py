# Photo Sorter

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PHOTOS_DIR = Path(os.environ.get("PHOTOS_DIR", "/photos"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
BEST_DIR = Path(os.environ.get("BEST_DIR", "/export"))
PORT = int(os.environ.get("PORT", "8080"))

# Image pipeline
THUMB_SIZE = 256
JPEG_QUALITY = 82

# Sharpness (Laplacian variance on 256px thumbnail)
SHARPNESS_PERCENTILE = 10.0

# Grouping
TIME_WINDOW_SECONDS = 5 * 60
DHASH_DISTANCE = 8
TARGET_GROUP_SIZE = 4
MIN_GROUP_SIZE = 2

# Tournament
MAX_VIEWS = 4
ELO_K = 32
ELO_BASE = 1500
RATED_ELO = {1: 1000, 2: 1200, 3: 1400, 4: 1600, 5: 1800}
FAVORITE_BONUS = 100

# Scan concurrency
MAX_WORKERS = max(1, (os.cpu_count() or 2) - 1)

# Only these are indexable photo files; everything else is ignored.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".arw", ".tif", ".tiff"}
RAW_EXTENSIONS = {".arw", ".tif", ".tiff"}
THUMBNAILABLE = {".jpg", ".jpeg"}

# Create the data/thumbnail tree at import time so every stage can rely on it.
DATA_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAIL_DIR = DATA_DIR / "thumbnails"
THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
