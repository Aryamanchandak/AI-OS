from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from ..models import NewsBatch, RunStatus


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    batch_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    events: Mapped[list["EventRow"]] = relationship(cascade="all, delete-orphan")
    artifacts: Mapped[list["ArtifactRow"]] = relationship(cascade="all, delete-orphan")


class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="progress")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(60), index=True)
    artifact_key: Mapped[str] = mapped_column(String(120), default="default")
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("run_id", "kind", "artifact_key", "version"),)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    def convert(item: Any) -> Any:
        if isinstance(item, BaseModel): return item.model_dump(mode="json")
        if isinstance(item, list): return [convert(v) for v in item]
        if isinstance(item, tuple): return [convert(v) for v in item]
        if isinstance(item, dict): return {k: convert(v) for k, v in item.items()}
        return item
    return json.dumps(convert(value), default=str, ensure_ascii=False)


class Repository:
    """SQLite-backed append-oriented run and artifact repository."""

    def __init__(self, database_url: str):
        if database_url == "sqlite:///:memory:":
            from sqlalchemy.pool import StaticPool
            self.engine = create_engine("sqlite://", future=True, creator=lambda: sqlite3.connect(":memory:", check_same_thread=False), poolclass=StaticPool)
        elif database_url.startswith("sqlite:///"):
            path = Path(database_url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)
            # A literal '?' is valid in a macOS path but is parsed as a URL query
            # delimiter by SQLAlchemy. Supplying a DB-API creator preserves it.
            self.engine = create_engine("sqlite://", future=True, creator=lambda: sqlite3.connect(str(path), check_same_thread=False))
        else:
            self.engine = create_engine(database_url, future=True)
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine, "connect")
            def _sqlite_pragmas(dbapi_connection, _record):
                # Run workers write while browser requests read the same file.
                # On the default rollback journal a reader blocks the writer and
                # SQLite raises "database is locked" immediately rather than
                # waiting, which surfaced as a randomly failed run. WAL lets
                # readers and the single writer proceed together, and the busy
                # timeout absorbs the remaining short write contention.
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA busy_timeout=5000")
                    cursor.execute("PRAGMA journal_mode=WAL")
                finally:
                    cursor.close()
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def init_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        # Fresh application startup and Alembic CLI startup must agree. The
        # initial revision exactly matches this metadata, so stamp databases
        # bootstrapped by create_all; later revisions remain Alembic-owned.
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            current = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
            if current is None:
                connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0001')"))

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self.sessions() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def create_run(self, batch: NewsBatch, run_id: str | None = None) -> str:
        run_id = run_id or str(uuid.uuid4())
        now = _now()
        with self.session() as session:
            session.add(RunRow(id=run_id, status=RunStatus.QUEUED, batch_json=batch.model_dump_json(), created_at=now, updated_at=now, error=None, warning_count=0))
        self.add_event(run_id, "queued", "Run accepted and queued")
        return run_id

    def set_status(self, run_id: str, status: RunStatus | str, *, error: str | None = None) -> None:
        with self.session() as session:
            row = session.get(RunRow, run_id)
            if row is None:
                raise KeyError(run_id)
            row.status = str(status)
            row.error = error
            row.updated_at = _now()

    def add_event(self, run_id: str, stage: str, message: str, kind: str = "progress") -> int:
        with self.session() as session:
            last = session.scalar(select(EventRow.sequence).where(EventRow.run_id == run_id).order_by(EventRow.sequence.desc()).limit(1)) or 0
            sequence = last + 1
            session.add(EventRow(run_id=run_id, sequence=sequence, stage=stage, message=message, kind=kind, created_at=_now()))
        return sequence

    def save_artifact(self, run_id: str, kind: str, payload: Any, *, key: str = "default", version: int | None = None) -> int:
        with self.session() as session:
            if version is None:
                last = session.scalar(select(ArtifactRow.version).where(ArtifactRow.run_id == run_id, ArtifactRow.kind == kind, ArtifactRow.artifact_key == key).order_by(ArtifactRow.version.desc()).limit(1)) or 0
                version = last + 1
            session.add(ArtifactRow(run_id=run_id, kind=kind, artifact_key=key, version=version, payload_json=_json(payload), created_at=_now()))
        return version

    def artifact(self, run_id: str, kind: str, *, key: str = "default", version: int | None = None) -> Any | None:
        with self.session() as session:
            stmt = select(ArtifactRow).where(ArtifactRow.run_id == run_id, ArtifactRow.kind == kind, ArtifactRow.artifact_key == key)
            stmt = stmt.where(ArtifactRow.version == version) if version is not None else stmt.order_by(ArtifactRow.version.desc()).limit(1)
            row = session.scalar(stmt)
            return json.loads(row.payload_json) if row else None

    def artifacts(self, run_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        with self.session() as session:
            stmt = select(ArtifactRow).where(ArtifactRow.run_id == run_id)
            if kind:
                stmt = stmt.where(ArtifactRow.kind == kind)
            rows = list(session.scalars(stmt.order_by(ArtifactRow.id)))
            return [{"kind": r.kind, "key": r.artifact_key, "version": r.version, "payload": json.loads(r.payload_json), "created_at": r.created_at.isoformat()} for r in rows]

    def get_run(self, run_id: str, *, include_artifacts: bool = False) -> dict[str, Any] | None:
        with self.session() as session:
            row = session.get(RunRow, run_id)
            if row is None:
                return None
            result = {"id": row.id, "status": row.status, "batch": json.loads(row.batch_json), "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(), "error": row.error, "warning_count": row.warning_count}
        if include_artifacts:
            result["artifacts"] = self.artifacts(run_id)
        return result

    def events_since(self, run_id: str, sequence: int = 0) -> list[dict[str, Any]]:
        with self.session() as session:
            rows = list(session.scalars(select(EventRow).where(EventRow.run_id == run_id, EventRow.sequence > sequence).order_by(EventRow.sequence)))
            return [{"sequence": r.sequence, "stage": r.stage, "message": r.message, "kind": r.kind, "created_at": r.created_at.isoformat()} for r in rows]

    def list_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.session() as session:
            ids = [r.id for r in session.scalars(select(RunRow).order_by(RunRow.created_at.desc()).limit(limit))]
        return [r for i in ids if (r := self.get_run(i))]
