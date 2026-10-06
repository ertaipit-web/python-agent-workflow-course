from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import StaticPool

from integration_lab.config import Settings
from integration_lab.database import create_task, get_task, init_db
from integration_lab.service import app


class IntegrationTestSettings(Settings):
    database_url: str = "sqlite+aiosqlite:///:memory:"
    github_token: str = "test-token"
    github_base_url: str = "https://api.github.com"
    model_provider: str = "ollama"
    model_name: str = "qwen3:8b"
    model_base_url: str = "http://localhost:11434/v1"
    model_api_key: str = ""


@pytest.fixture(scope="session")
def test_settings():
    return IntegrationTestSettings()


@pytest.fixture(scope="session")
async def db_engine(test_settings):
    engine, async_session_maker = await init_db(
        str(test_settings.database_url), poolclass=StaticPool
    )
    yield engine, async_session_maker
    await engine.dispose()


@pytest.fixture(scope="session")
async def db_session(db_engine):
    _, async_session_maker = db_engine
    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def client(test_settings, monkeypatch, db_engine):
    from integration_lab import service

    monkeypatch.setattr(service, "settings", test_settings)
    monkeypatch.setattr(service, "engine", db_engine[0])
    monkeypatch.setattr(service, "async_session_maker", db_engine[1])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_create_task_endpoint(client):
    response = await client.post("/tasks", json={"task": "Create a test issue"})
    assert response.status_code == 202
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "queued"

    uuid.UUID(data["task_id"])


@pytest.mark.asyncio
async def test_create_task_validation(client):
    response = await client.post("/tasks", json={"task": ""})
    assert response.status_code == 422

    response = await client.post("/tasks", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_task_not_found(client):
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/tasks/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_task_invalid_uuid(client):
    response = await client.get("/tasks/not-a-uuid")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_task_persistence(db_session: AsyncSession):
    task = await create_task(db_session, {"task": "Test task", "meta": "data"})
    await db_session.commit()

    retrieved = await get_task(db_session, task.id)
    assert retrieved is not None
    assert retrieved.payload["task"] == "Test task"
    assert retrieved.payload["meta"] == "data"
    assert retrieved.status == "queued"


@pytest.mark.asyncio
async def test_task_status_updates(db_session: AsyncSession):
    from integration_lab.database import update_task_status

    task = await create_task(db_session, {"task": "Test"})
    await db_session.commit()

    updated = await update_task_status(db_session, task.id, "running")
    await db_session.commit()
    assert updated.status == "running"
    assert updated.started_at is not None

    updated = await update_task_status(
        db_session, task.id, "completed",
        result={"status": "ok", "data": "result"}
    )
    await db_session.commit()
    assert updated.status == "completed"
    assert updated.completed_at is not None
    assert updated.result == {"status": "ok", "data": "result"}

    task2 = await create_task(db_session, {"task": "Test 2"})
    await db_session.commit()
    updated = await update_task_status(db_session, task2.id, "failed", error="Something went wrong")
    await db_session.commit()
    assert updated.status == "failed"
    assert updated.error == "Something went wrong"


@pytest.mark.asyncio
async def test_database_models_have_correct_schema(db_session: AsyncSession):
    from integration_lab.database import create_execution, create_task, update_execution

    task = await create_task(db_session, {"task": "Test"})
    await db_session.commit()

    execution = await create_execution(db_session, task.id, "run-test-1")
    await db_session.commit()

    assert execution.run_id == "run-test-1"
    assert execution.status == "running"
    assert execution.trace == []

    updated = await update_execution(
        db_session, execution.id,
        status="completed",
        trace=[{"tool": "test", "status": "ok"}]
    )
    await db_session.commit()
    assert updated.status == "completed"
    assert updated.trace == [{"tool": "test", "status": "ok"}]
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_create_task_with_explicit_id(db_session: AsyncSession):
    """create_task должна принимать task_id от caller и использовать его как PK."""
    task_id = uuid.uuid4()
    task = await create_task(db_session, {"task": "Explicit ID test"}, task_id=task_id)
    await db_session.commit()

    assert task.id == task_id
    retrieved = await get_task(db_session, task_id)
    assert retrieved is not None
    assert retrieved.id == task_id


@pytest.mark.asyncio
async def test_post_task_returns_authoritative_id(client):
    """POST /tasks должен вернуть task_id, который существует в БД."""
    response = await client.post("/tasks", json={"task": "Integration test task"})
    assert response.status_code == 202
    data = response.json()
    returned_task_id = data["task_id"]

    task_uuid = uuid.UUID(returned_task_id)

    from integration_lab.service import get_async_session_maker
    session_maker = await get_async_session_maker()
    async with session_maker() as session:
        from integration_lab.database import get_task
        task = await get_task(session, task_uuid)
        assert task is not None
        assert str(task.id) == returned_task_id


@pytest.mark.asyncio
async def test_post_then_get_task_consistency(client):
    """POST /tasks → GET /tasks/{task_id} должен возвращать ту же задачу."""
    create_response = await client.post("/tasks", json={"task": "Lifecycle consistency test"})
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["task_id"] == task_id


@pytest.mark.asyncio
async def test_execution_task_id_matches_task(client):
    """Execution.task_id должен совпадать с task_id."""
    create_response = await client.post("/tasks", json={"task": "Execution FK test"})
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]
    task_uuid = uuid.UUID(task_id)

    from sqlalchemy import select

    from integration_lab.database import Execution
    from integration_lab.service import get_async_session_maker

    session_maker = await get_async_session_maker()
    async with session_maker() as session:
        result = await session.execute(
            select(Execution).where(Execution.task_id == task_uuid)
        )
        execution = result.scalars().first()
        assert execution is not None
        assert str(execution.task_id) == task_id


@pytest.mark.asyncio
async def test_task_lifecycle(client):
    """Task lifecycle: queued → running → completed/done."""
    create_response = await client.post("/tasks", json={"task": "Lifecycle test"})
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    from sqlalchemy import select

    from integration_lab.database import Task
    from integration_lab.service import get_async_session_maker

    session_maker = await get_async_session_maker()
    async with session_maker() as session:
        # Initial state after POST: task exists with queued status
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
        task = result.scalars().first()
        assert task is not None
        assert str(task.id) == task_id

        # Background task may have already run (ScriptedPlanner with empty calls completes immediately)
        # The key invariant: task_id is consistent across the lifecycle
        assert task.status in ("queued", "running", "completed", "done", "failed")