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
THUMB_SIZE = 512  # 512px so review thumbnails are sharp enough to judge
JPEG_QUALITY = 85

# Sharpness (Laplacian variance on 256px thumbnail)
SHARPNESS_PERCENTILE = 10.0

# Grouping
# Connected-components graph algorithm using pHash (subject) + dHash (framing)
# + time proximity. Components of size > 1 are series (capped at MAX_SERIES_SIZE
# by splitting on time); size-1 components are batched into SINGLE_BATCH_SIZE.
TIME_WINDOW_SECONDS = 120          # pairwise time gap limit (seconds)
SUBJECT_WEIGHT = 0.50              # pHash contribution to combined score
FRAMING_WEIGHT = 0.30              # dHash contribution to combined score
TIME_WEIGHT = 0.20                 # time-proximity contribution
SUBJECT_THRESHOLD = 0.45           # minimum subject_score for an edge
COMBINED_THRESHOLD = 0.68          # minimum combined_score for an edge
MAX_SERIES_SIZE = 16               # cap per series (split larger components by time)
SINGLE_BATCH_SIZE = 4              # batch size for non-series photos

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
