"""Persisted progress tracking shared by all pipeline stages."""

from datetime import datetime

from sqlmodel import Session, select

from .db import Progress


def get_progress(session: Session, stage: str) -> Progress:
    row = session.exec(select(Progress).where(Progress.stage == stage)).first()
    if row is None:
        row = Progress(stage=stage)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def reset_progress(session: Session, stage: str) -> Progress:
    row = get_progress(session, stage)
    row.total = 0
    row.processed = 0
    row.status = "idle"
    row.error = None
    row.updated_at = datetime.now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def set_running(session: Session, stage: str, total: int) -> Progress:
    row = get_progress(session, stage)
    row.total = total
    row.status = "running"
    row.error = None
    row.updated_at = datetime.now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def set_done(session: Session, stage: str) -> Progress:
    row = get_progress(session, stage)
    row.status = "done"
    row.updated_at = datetime.now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def set_error(session: Session, stage: str, message: str) -> Progress:
    row = get_progress(session, stage)
    row.status = "error"
    row.error = message
    row.updated_at = datetime.now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def increment_processed(session: Session, stage: str, amount: int = 1) -> None:
    row = get_progress(session, stage)
    row.processed += amount
    row.updated_at = datetime.now()
    session.add(row)
    session.commit()
