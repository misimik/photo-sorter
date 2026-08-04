"""Persisted progress tracking shared by all pipeline stages.

One row per (stage, folder) pair. folder="" means the global/all-folders run.
"""

from datetime import datetime

from sqlmodel import Session, select

from .db import Progress


def get_progress(session: Session, stage: str, folder: str = "") -> Progress:
    row = session.exec(
        select(Progress).where(Progress.stage == stage, Progress.folder == folder)
    ).first()
    if row is None:
        row = Progress(stage=stage, folder=folder)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def reset_progress(session: Session, stage: str, folder: str = "") -> Progress:
    row = get_progress(session, stage, folder)
    row.total = 0
    row.processed = 0
    row.status = "idle"
    row.error = None
    row.updated_at = datetime.now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def set_running(session: Session, stage: str, total: int, folder: str = "") -> Progress:
    row = get_progress(session, stage, folder)
    row.total = total
    row.status = "running"
    row.error = None
    row.updated_at = datetime.now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def set_done(session: Session, stage: str, folder: str = "") -> Progress:
    row = get_progress(session, stage, folder)
    row.status = "done"
    row.updated_at = datetime.now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def set_error(session: Session, stage: str, message: str, folder: str = "") -> Progress:
    row = get_progress(session, stage, folder)
    row.status = "error"
    row.error = message
    row.updated_at = datetime.now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def increment_processed(session: Session, stage: str, amount: int = 1, folder: str = "") -> None:
    row = get_progress(session, stage, folder)
    row.processed += amount
    row.updated_at = datetime.now()
    session.add(row)
    session.commit()
