"""FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .db import db
from .routes import router

_APP_FILE = Path(__file__).resolve()


def _find_static_dir() -> Path | None:
    """Locate the built SPA. Layout differs between the repo and the container:
    - repo:      <project>/backend/app/main.py  -> <project>/frontend/dist
    - container: /app/app/main.py               -> /app/frontend/dist
    """
    candidates = [
        _APP_FILE.parent.parent.parent / "frontend" / "dist",
        _APP_FILE.parent.parent / "frontend" / "dist",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


STATIC_DIR = _find_static_dir()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Ensure the DB schema + WAL mode are initialized on boot.
    db.engine.connect().close()
    yield


app = FastAPI(title="Photo Sorter", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="spa")
