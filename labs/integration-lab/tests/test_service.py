from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import StaticPool

from integration_lab.service import app
from integration_lab.database import Task, create_task, get_task, init_db
from integration_lab.config import Settings


# Test settings with SQLite in-memory
class TestSettings(Settings):
    database_url: str = "sqlite+aiosqlite:///:memory:"
    github_token: str = "test-token"
    github_base_url: str = "https://api.github.com"
    model_provider: str = "ollama"
    model_name: str = "qwen3:8b"
    model_base_url: str = "http://localhost:11434/v1"
    model_api_key: str = ""


@pytest.fixture(scope="session")
def test_settings():
    return TestSettings()


@pytest.fixture(scope="session")
async def db_session(test_settings):
    async_session_maker = await init_db(str(test_settings.database_url), poolclass=StaticPool)
    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def client(test_settings, monkeypatch):
    # Override settings for testing
    from integration_lab import service
    monkeypatch.setattr(service, "settings", test_settings)
    # Reset the session maker
    monkeypatch.setattr(service, "async_session_maker", None)

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

    # Verify task_id is valid UUID
    import uuid
    uuid.UUID(data["task_id"])


@pytest.mark.asyncio
async def test_create_task_validation(client):
    # Empty task should fail
    response = await client.post("/tasks", json={"task": ""})
    assert response.status_code == 422

    # Missing task field
    response = await client.post("/tasks", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_task_not_found(client):
    import uuid
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

    # Update to running
    updated = await update_task_status(db_session, task.id, "running")
    await db_session.commit()
    assert updated.status == "running"
    assert updated.started_at is not None

    # Update to completed with result
    updated = await update_task_status(
        db_session, task.id, "completed",
        result={"status": "ok", "data": "result"}
    )
    await db_session.commit()
    assert updated.status == "completed"
    assert updated.completed_at is not None
    assert updated.result == {"status": "ok", "data": "result"}

    # Update to failed with error
    task2 = await create_task(db_session, {"task": "Test 2"})
    await db_session.commit()
    updated = await update_task_status(db_session, task2.id, "failed", error="Something went wrong")
    await db_session.commit()
    assert updated.status == "failed"
    assert updated.error == "Something went wrong"


@pytest.mark.asyncio
async def test_database_models_have_correct_schema(db_session: AsyncSession):
    from integration_lab.database import Execution, create_execution, update_execution
    from integration_lab.database import create_task

    task = await create_task(db_session, {"task": "Test"})
    await db_session.commit()

    execution = await create_execution(db_session, task.id, "run-test-1")
    await db_session.commit()

    assert execution.run_id == "run-test-1"
    assert execution.status == "running"
    assert execution.trace == []

    # Update execution
    updated = await update_execution(
        db_session, execution.id,
        status="completed",
        trace=[{"tool": "test", "status": "ok"}]
    )
    await db_session.commit()
    assert updated.status == "completed"
    assert updated.trace == [{"tool": "test", "status": "ok"}]
    assert updated.completed_at is not None