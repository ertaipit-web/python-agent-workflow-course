from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, select
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import CHAR, TypeDecorator


class Base(AsyncAttrs, DeclarativeBase):
    pass


class GUID(TypeDecorator):
    """Platform-independent GUID type. Uses PostgreSQL's UUID, otherwise CHAR(32)."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID())
        else:
            return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        else:
            if isinstance(value, UUID):
                return value.hex
            return str(value).replace("-", "")

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, UUID):
            return value
        if dialect.name == "postgresql":
            return UUID(value)
        return UUID(hex=value)


class JSON(TypeDecorator):
    """Platform-independent JSON type. Uses PostgreSQL's JSONB, otherwise TEXT."""
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        else:
            return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON(), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    executions: Mapped[list[Execution]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        primaryjoin="Task.id == Execution.task_id"
    )


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("tasks.id"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSON(), nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[Task] = relationship(
        back_populates="executions",
        primaryjoin="Execution.task_id == Task.id"
    )


async def init_db(database_url: str, poolclass=None) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    connect_args = {"check_same_thread": False} if "sqlite" in database_url else {}
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        poolclass=poolclass,
        connect_args=connect_args,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_task(
    session: AsyncSession,
    payload: dict[str, Any],
    task_id: UUID | None = None,
) -> Task:
    task = Task(id=task_id, payload=payload)
    session.add(task)
    await session.flush()
    return task


async def get_task(session: AsyncSession, task_id: UUID) -> Task | None:
    return await session.get(Task, task_id)


async def update_task_status(
    session: AsyncSession,
    task_id: UUID,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> Task | None:
    task = await session.get(Task, task_id)
    if not task:
        return None
    task.status = status
    if status == "running" and not task.started_at:
        task.started_at = datetime.now(UTC)
    if status in ("completed", "failed", "blocked"):
        task.completed_at = datetime.now(UTC)
    if result is not None:
        task.result = result
    if error is not None:
        task.error = error
    await session.flush()
    return task


async def create_execution(
    session: AsyncSession,
    task_id: UUID,
    run_id: str,
) -> Execution:
    execution = Execution(task_id=task_id, run_id=run_id)
    session.add(execution)
    await session.flush()
    return execution


async def update_execution(
    session: AsyncSession,
    execution_id: UUID,
    *,
    status: str | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> Execution | None:
    execution = await session.get(Execution, execution_id)
    if not execution:
        return None
    if status:
        execution.status = status
    if trace is not None:
        execution.trace = trace
    if status in ("completed", "failed", "blocked"):
        execution.completed_at = datetime.now(UTC)
    await session.flush()
    return execution


async def list_tasks(session: AsyncSession, limit: int = 50, offset: int = 0) -> list[Task]:
    result = await session.execute(
        select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())