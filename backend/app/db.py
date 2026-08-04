"""SQLModel ORM models and the SQLite (WAL) database layer."""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, event
from sqlmodel import Field, Session, SQLModel, create_engine

from .config import DATA_DIR


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _on_connect(dbapi_conn, _record):  # pragma: no cover - thin wrapper
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


class Catalogue(SQLModel, table=True):
    """One scanned root folder. Singleton in practice."""

    id: int | None = Field(default=None, primary_key=True)
    path: str = Field(index=True, unique=True)
    total_files: int = 0
    scanned_files: int = 0
    state: str = "pending"  # pending | scanning | analyzing | grouping | ready | error
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Catalogue {self.path} state={self.state}>"


class Photo(SQLModel, table=True):
    """One image file. ARW files are stored but never decoded."""

    id: int | None = Field(default=None, primary_key=True)
    catalogue_id: int = Field(foreign_key="catalogue.id", index=True)
    path: str = Field(index=True)
    folder: str = Field(index=True, default="")
    stem: str = Field(index=True)
    ext: str = Field(index=True)
    size: int = 0
    mtime: float = 0.0
    sha1: str | None = None

    is_raw: bool = False
    paired_id: int | None = Field(default=None, foreign_key="photo.id", index=True)

    exif_datetime: str | None = None  # EXIF DateTimeOriginal as ISO string
    orientation: int | None = None
    width: int | None = None
    height: int | None = None

    dhash: str | None = None
    phash: str | None = None
    sharpness: float | None = None
    is_blurry: bool | None = None

    rating: int = 0  # 0 = unrated, 1-5 stars
    favorite: bool = False
    rejected: bool = False

    elo: int = 1500
    views: int = 0

    group_id: int | None = Field(default=None, foreign_key="photogroup.id", index=True)
    analyzed: bool = False

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Photo {self.path} elo={self.elo}>"


class PhotoGroup(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    folder: str = Field(index=True, default="")
    start_time: datetime | None = None
    end_time: datetime | None = None


class TournamentMatch(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    left_id: int = Field(foreign_key="photo.id", index=True)
    right_id: int = Field(foreign_key="photo.id", index=True)
    winner_id: int = Field(foreign_key="photo.id", index=True)
    left_elo_before: int = 0
    right_elo_before: int = 0
    created_at: datetime = Field(default_factory=utcnow)


class ExportJob(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    fraction: float = 0.0
    status: str = "pending"  # pending | running | done | error
    copied: int = 0
    total: int = 0
    manifest_path: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Progress(SQLModel, table=True):
    """Persisted progress counters for each pipeline stage + folder.

    Acts as the source of truth so progress survives browser refreshes and
    container restarts. One row per (stage, folder) pair; folder "" = global.
    """

    id: int | None = Field(default=None, primary_key=True)
    stage: str = Field(index=True)  # scan | analyze | group | export
    folder: str = Field(index=True, default="")
    total: int = 0
    processed: int = 0
    status: str = "idle"  # idle | running | done | error
    error: str | None = None
    updated_at: datetime = Field(default_factory=utcnow)


class Database:
    def __init__(self, db_path: Path | str):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
        event.listen(self._engine, "connect", _on_connect)
        SQLModel.metadata.create_all(self._engine)

    @property
    def engine(self) -> Engine:
        return self._engine

    def session(self) -> Session:
        return Session(self._engine)


def _ensure_column(session: Session, table: str, column: str, ddl: str) -> None:
    """Add a column to an existing table if it's missing (idempotent)."""
    from sqlalchemy import text

    cols = session.exec(text(f"PRAGMA table_info({table})")).all()
    names = {c[1] for c in cols}
    if column not in names:
        session.exec(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
        session.commit()


def _progress_has_unique_stage(session: Session) -> bool:
    """True if the progress table still enforces UNIQUE on stage.

    Both forms are detected: SQLModel's named unique index (ix_progress_stage)
    and the old schema's table-level UNIQUE constraint (sqlite_autoindex).
    Either one blocks per-folder progress rows, so either triggers a rebuild.
    """
    from sqlalchemy import text

    idx = session.exec(text("PRAGMA index_list(progress)")).all()
    for row in idx:
        name = row[1]
        unique = row[2]
        if unique:
            cols = session.exec(text(f"PRAGMA index_info({name})")).all()
            if cols and cols[0][2] == "stage":
                return True
    return False


def _rebuild_progress_without_unique(session: Session, photos_dir: Path) -> None:
    """Rebuild the progress table without the UNIQUE(stage) constraint."""
    from sqlalchemy import text

    if not _progress_has_unique_stage(session):
        return  # already migrated (new schema or prior rebuild)

    session.exec(text(
        "CREATE TABLE progress_new ("
        "id INTEGER PRIMARY KEY,"
        "stage VARCHAR NOT NULL,"
        "folder VARCHAR DEFAULT '',"
        "total INTEGER NOT NULL DEFAULT 0,"
        "processed INTEGER NOT NULL DEFAULT 0,"
        "status VARCHAR NOT NULL DEFAULT 'idle',"
        "error VARCHAR,"
        "updated_at DATETIME NOT NULL)"
    ))
    session.exec(text(
        "INSERT INTO progress_new (id, stage, folder, total, processed, status, error, updated_at) "
        "SELECT id, stage, folder, total, processed, status, error, updated_at FROM progress"
    ))
    session.exec(text("DROP TABLE progress"))
    session.exec(text("ALTER TABLE progress_new RENAME TO progress"))
    session.commit()


def migrate_folder_columns(session: Session, photos_dir: Path) -> None:
    """Add the `folder` columns (if missing) and backfill them from paths.

    create_all() only creates missing tables — it never adds columns to an
    existing table — so the ALTER TABLEs here are required when upgrading a DB
    created before the per-folder rework. Idempotent: safe to run every boot.
    """
    from sqlmodel import select

    _ensure_column(session, "photo", "folder", "folder VARCHAR DEFAULT ''")
    _ensure_column(session, "photogroup", "folder", "folder VARCHAR DEFAULT ''")
    _ensure_column(session, "progress", "folder", "folder VARCHAR DEFAULT ''")
    _rebuild_progress_without_unique(session, photos_dir)
    session.commit()

    photos_dir = photos_dir.resolve()

    photos = session.exec(select(Photo).where(Photo.folder == "")).all()
    for p in photos:
        # Folder = the photo's immediate parent directory name. This is robust
        # across platforms and doesn't depend on the photos root matching.
        p.folder = Path(p.path).parent.name
        session.add(p)
    if photos:
        session.commit()

    groups = session.exec(select(PhotoGroup).where(PhotoGroup.folder == "")).all()
    for g in groups:
        member = session.exec(select(Photo).where(Photo.group_id == g.id)).first()
        g.folder = member.folder if member else ""
        session.add(g)
    if groups:
        session.commit()


# Module-level default database (overridden in tests).
DB_PATH = DATA_DIR / "photosorter.db"
db = Database(DB_PATH)


def get_db():
    with db.session() as session:
        yield session
