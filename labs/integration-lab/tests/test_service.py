from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import StaticPool

from integration_lab.config import Settings
from integration_lab.database import create_task, get_task, init_db
from integration_lab.service import app


async def _wait_for_task(
    ac: AsyncClient,
    task_id: str,
    timeout: float = 10.0,
    poll_interval: float = 0.1,
) -> dict[str, Any]:
    """Poll GET /tasks/{task_id} until status != 'queued' or timeout expires."""
    import asyncio

    deadline = time.monotonic() + timeout
    data: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = await ac.get(f"/tasks/{task_id}")
        data = response.json()
        if data["status"] not in {"queued", "running"}:
            return data
        await asyncio.sleep(poll_interval)
    return data


class IntegrationTestSettings(Settings):
    database_url: str = "sqlite+aiosqlite:///:memory:"
    github_token: str = "test-token"
    github_base_url: str = "https://api.github.com"
    model_provider: str = "ollama"
    model_name: str = "qwen3:8b"
    model_base_url: str = "http://localhost:11434/v1"
    model_api_key: str = ""
    runner_mode: str = "test"
    demo_owner: str = "demo-owner"
    demo_repo: str = "demo-repo"
    demo_approve_writes: bool = True
    default_max_retries: int = 3


@pytest.fixture(scope="session")
def test_settings():
    return IntegrationTestSettings()


@pytest.fixture(scope="session")
def mock_github_settings():
    """Settings for demo mode with mock GitHub API."""
    return IntegrationTestSettings(
        runner_mode="demo",
        github_base_url="",  # set after server starts
    )


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
    assert task.completed_at is None

    updated = await update_task_status(db_session, task.id, "running")
    await db_session.commit()
    assert updated is not None
    assert updated.status == "running"
    assert updated.started_at is not None
    assert updated.completed_at is None

    updated = await update_task_status(
        db_session, task.id, "completed",
        result={"status": "ok", "data": "result"}
    )
    await db_session.commit()
    assert updated is not None
    assert updated.status == "completed"
    assert updated.completed_at is not None
    assert updated.result == {"status": "ok", "data": "result"}

    task2 = await create_task(db_session, {"task": "Test 2"})
    await db_session.commit()
    updated = await update_task_status(db_session, task2.id, "failed", error="Something went wrong")
    await db_session.commit()
    assert updated is not None
    assert updated.status == "failed"
    assert updated.error == "Something went wrong"
    assert updated.completed_at is not None


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
    assert execution.completed_at is None

    updated = await update_execution(
        db_session, execution.id,
        status="completed",
        trace=[{"tool": "test", "status": "ok"}]
    )
    await db_session.commit()
    assert updated is not None
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
    # execution_id should be the run_id from trace (per Week 8 spec)
    if data["execution_id"] is not None:
        assert data["execution_id"].startswith("run-")


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
    """Task lifecycle: queued → running → completed."""
    create_response = await client.post("/tasks", json={"task": "Lifecycle test"})
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    from sqlalchemy import select

    from integration_lab.database import Task
    from integration_lab.service import get_async_session_maker

    session_maker = await get_async_session_maker()
    async with session_maker() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
        task = result.scalars().first()
        assert task is not None
        assert str(task.id) == task_id
        assert task.status in ("queued", "running", "completed", "failed", "needs_approval")


@pytest.fixture
def mock_github_api():
    """Start a local mock GitHub API server for integration tests."""
    from integration_lab.issue_api import IssueApi, Token
    from integration_lab.tools import READ_ONLY_SCOPES, WRITE_SCOPES

    api = IssueApi(
        database=":memory:",
        tokens=(
            Token(name="test-token", scopes=READ_ONLY_SCOPES | WRITE_SCOPES),
        ),
    )
    api.start(port=0)
    yield api
    api.close()


def _make_demo_client(mock_github_api, monkeypatch, db_engine, *, owner="course", repo="taskboard", approve=True):
    """Create a demo-mode client pointing to the mock GitHub API."""
    from integration_lab import service

    settings = IntegrationTestSettings(
        runner_mode="demo",
        github_base_url=mock_github_api.base_url,
        github_token="test-token",
        demo_owner=owner,
        demo_repo=repo,
        demo_approve_writes=approve,
    )
    monkeypatch.setattr(service, "settings", settings)
    monkeypatch.setattr(service, "engine", db_engine[0])
    monkeypatch.setattr(service, "async_session_maker", db_engine[1])

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_demo_toolcall_success(mock_github_api, monkeypatch, db_engine):
    """End-to-end: POST /tasks → ToolCall(create_issue) → mock GitHub → trace."""
    async with _make_demo_client(mock_github_api, monkeypatch, db_engine) as ac:
        create_response = await ac.post("/tasks", json={"task": "Create a demo issue"})
        assert create_response.status_code == 202
        task_id = create_response.json()["task_id"]

        data = await _wait_for_task(ac, task_id)
        assert data["task_id"] == task_id
        assert data["status"] == "completed"
        assert data["started_at"] is not None
        assert data["completed_at"] is not None
        assert data["execution_id"] is not None
        assert data["execution_id"].startswith("run-")
        assert data["result"] is not None
        assert data["result"]["status"] == "completed"
        trace = data["result"]["trace"]
        assert len(trace) > 0
        assert any(t["tool_name"] == "create_issue" and t["status"] == "complete" for t in trace)

        # Verify the issue was actually created in the mock API
        issues = mock_github_api.store.list_issues("course", "taskboard", state=None)
        assert any(i["title"] == "[Test] Capstone demo issue" for i in issues)


@pytest.mark.asyncio
async def test_service_serializes_list_valued_read_results(mock_github_api, monkeypatch, db_engine):
    from integration_lab import service
    from integration_lab.runtime import ScriptedPlanner, ToolCall

    async with _make_demo_client(mock_github_api, monkeypatch, db_engine) as ac:
        runtime = service.get_runtime()
        runtime.planner = ScriptedPlanner(
            [
                ToolCall(
                    tool="list_issues",
                    arguments={"owner": "course", "repository": "taskboard"},
                )
            ]
        )
        monkeypatch.setattr(service, "get_runtime", lambda: runtime)

        create_response = await ac.post("/tasks", json={"task": "List demo issues"})
        assert create_response.status_code == 202
        data = await _wait_for_task(ac, create_response.json()["task_id"])

        assert data["status"] == "completed"
        assert data["completed_at"] is not None
        assert data["execution_id"] is not None
        assert data["result"]["results"] == [[]]
        assert data["result"]["trace"][0]["tool_name"] == "list_issues"


@pytest.mark.asyncio
async def test_demo_toolcall_denied_by_policy(mock_github_api, monkeypatch, db_engine):
    """Policy deny: repository not in allowlist → blocked, handler not called, API not called."""
    from integration_lab import service
    from integration_lab.runtime import Policy
    from integration_lab.tools import READ_ONLY_SCOPES, WRITE_SCOPES

    # The policy allowlist is ("course", "taskboard"), but the planner will target
    # ("evil", "evil-repo") — this mismatch proves the security property.
    monkeypatch.setattr(service, "_build_policy", lambda: Policy(
        granted_scopes=READ_ONLY_SCOPES | WRITE_SCOPES,
        allowed_repositories=frozenset([("course", "taskboard")]),
    ))

    async with _make_demo_client(
        mock_github_api, monkeypatch, db_engine,
        owner="evil", repo="evil-repo", approve=True
    ) as ac:
        create_response = await ac.post("/tasks", json={"task": "Create an issue in evil repo"})
        task_id = create_response.json()["task_id"]

        data = await _wait_for_task(ac, task_id)
        assert data["task_id"] == task_id
        assert data["status"] == "blocked", (
            f"Expected 'blocked' for repository not in allowlist, got '{data['status']}'"
        )
        assert data["completed_at"] is not None
        assert data["execution_id"] is not None
        assert data["error"] is not None
        assert "repository is not allowlisted" in data["error"]
        # No issue should have been created — handler was never invoked
        assert len(mock_github_api.store.list_issues("evil", "evil-repo", state=None)) == 0

        from sqlalchemy import select

        from integration_lab.database import Execution
        from integration_lab.service import get_async_session_maker

        session_maker = await get_async_session_maker()
        async with session_maker() as session:
            execution_result = await session.execute(
                select(Execution).where(Execution.task_id == uuid.UUID(task_id))
            )
            execution = execution_result.scalars().one()
            assert execution.status == "blocked"
            assert execution.run_id == data["execution_id"]
            assert execution.completed_at is not None
            assert execution.trace[-1]["transition_reason"] == "repository_not_allowed"


@pytest.mark.asyncio
async def test_demo_toolcall_approval_rejected(mock_github_api, monkeypatch, db_engine):
    """Approval rejected: ToolCall → approval → rejected → no side effect."""
    async with _make_demo_client(
        mock_github_api, monkeypatch, db_engine,
        owner="course", repo="taskboard", approve=False
    ) as ac:
        create_response = await ac.post("/tasks", json={"task": "Create a demo issue"})
        task_id = create_response.json()["task_id"]

        data = await _wait_for_task(ac, task_id)
        assert data["task_id"] == task_id
        assert data["status"] == "blocked"
        assert data["error"] == "create_issue: human approval was rejected"
        # No issue should have been created
        assert len(mock_github_api.store.list_issues("course", "taskboard", state=None)) == 0


@pytest.mark.asyncio
async def test_service_persists_needs_approval_snapshot_without_resume(
    mock_github_api, monkeypatch, db_engine
):
    from integration_lab import service
    from integration_lab.runtime import Policy
    from integration_lab.tools import READ_ONLY_SCOPES, WRITE_SCOPES

    async with _make_demo_client(mock_github_api, monkeypatch, db_engine) as ac:
        runtime = service.get_runtime()
        runtime.policy = Policy(
            granted_scopes=READ_ONLY_SCOPES | WRITE_SCOPES,
            allowed_repositories=frozenset({("course", "taskboard")}),
            approver=None,
        )
        monkeypatch.setattr(service, "get_runtime", lambda: runtime)

        create_response = await ac.post("/tasks", json={"task": "Create a demo issue"})
        assert create_response.status_code == 202
        task_id = create_response.json()["task_id"]

        data = await _wait_for_task(ac, task_id)
        assert data["status"] == "needs_approval"
        assert data["started_at"] is not None
        assert data["completed_at"] is None
        assert data["execution_id"] is not None
        assert data["result"]["status"] == "needs_approval"
        assert data["result"]["pending_approval"]["tool"] == "create_issue"
        assert data["result"]["trace"][-1]["transition_reason"] == "needs_approval"
        assert mock_github_api.store.count() == 0

        from integration_lab.service import get_async_session_maker

        session_maker = await get_async_session_maker()
        async with session_maker() as session:
            from sqlalchemy import select

            from integration_lab.database import Execution, get_task

            task = await get_task(session, uuid.UUID(task_id))
            assert task is not None
            assert task.completed_at is None
            execution_result = await session.execute(
                select(Execution).where(Execution.task_id == uuid.UUID(task_id))
            )
            execution = execution_result.scalars().one()
            assert execution.status == "needs_approval"
            assert execution.run_id == data["execution_id"]
            assert execution.completed_at is None
            assert execution.trace[-1]["transition_reason"] == "needs_approval"


@pytest.mark.asyncio
async def test_demo_toolcall_invalid_arguments(mock_github_api, monkeypatch, db_engine, db_session):
    """Invalid arguments: ToolCall → validation error → no side effect."""
    from integration_lab.runtime import ScriptedPlanner, ToolCall
    from integration_lab.service import get_async_session_maker, get_runtime

    settings = IntegrationTestSettings(
        runner_mode="demo",
        github_base_url=mock_github_api.base_url,
        github_token="test-token",
        demo_owner="course",
        demo_repo="taskboard",
        demo_approve_writes=False,
    )

    from integration_lab import service

    monkeypatch.setattr(service, "settings", settings)
    monkeypatch.setattr(service, "engine", db_engine[0])
    monkeypatch.setattr(service, "async_session_maker", db_engine[1])

    session_maker = await get_async_session_maker()
    async with session_maker() as session:
        from integration_lab.database import create_execution, create_task, update_task_status

        task = await create_task(session, {"task": "invalid args test"}, task_id=uuid.uuid4())
        await session.commit()
        task_id = task.id

        await create_execution(session, task_id, "run-invalid")
        await session.commit()

        await update_task_status(session, task_id, "running")
        await session.commit()

        # Run runtime directly with invalid tool call
        runtime = get_runtime()
        runtime.run_id = "run-invalid"
        runtime.node_id = "issue_agent"

        call = ToolCall(
            tool="create_issue",
            arguments={
                "owner": "course",
                "repository": "taskboard",
                "title": "",  # empty title - invalid
            },
        )
        planner = ScriptedPlanner(calls=[call])
        runtime.planner = planner

        report = runtime.run("invalid args test")

        assert report.status == "blocked"
        assert report.reason is not None
        assert "invalid" in report.reason.lower() or "empty" in report.reason.lower()


@pytest.mark.asyncio
async def test_needs_approval_does_not_set_completed_at(client, db_session):
    """needs_approval is NOT a terminal state — completed_at must remain None."""
    from integration_lab.database import create_execution, create_task, update_task_status

    task = await create_task(db_session, {"task": "Approval test"})
    await db_session.commit()
    await create_execution(db_session, task.id, "run-approval")
    await db_session.commit()

    updated = await update_task_status(db_session, task.id, "needs_approval")
    await db_session.commit()
    assert updated is not None
    assert updated.status == "needs_approval"
    assert updated.completed_at is None, (
        "needs_approval must NOT set completed_at — it is not a terminal state"
    )


@pytest.mark.asyncio
async def test_request_id_header(client):
    """Every response must carry an X-Request-ID header."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) > 0


@pytest.mark.asyncio
async def test_async_execution_does_not_block_post(client):
    """POST /tasks must return 202 immediately, without waiting for runtime to finish."""
    start = time.monotonic()
    response = await client.post("/tasks", json={"task": "Async test"})
    elapsed = time.monotonic() - start
    assert response.status_code == 202
    # The POST must return well before any background execution completes
    assert elapsed < 1.0, f"POST /tasks took {elapsed:.2f}s — should return immediately"


@pytest.mark.asyncio
async def test_retry_backoff_config(client):
    """IssueApiClient must use exponential backoff with bounded jitter."""
    from integration_lab.client import IssueApiClient

    client_obj = IssueApiClient(
        base_url="http://example.com",
        token="test",
        max_attempts=3,
        backoff_base=0.1,
        backoff_max=0.5,
    )
    # Exponential growth: base * 2^(attempt-1), then jittered by uniform(0.5, 1.0).
    # backoff(1) base = 0.1, jittered range = [0.05, 0.10]
    # backoff(2) base = 0.2, jittered range = [0.10, 0.20]
    # backoff(3) base = 0.4, jittered range = [0.20, 0.40]
    cases = [
        (1, 0.1, 0.1),
        (2, 0.2, 0.2),
        (3, 0.4, 0.4),
    ]
    for attempt, expected_min, expected_max in cases:
        delay = client_obj._backoff(attempt)
        assert expected_min / 2 <= delay <= expected_max, (
            f"backoff({attempt})={delay} not in [{expected_min / 2}, {expected_max}]"
        )
    # capped at backoff_max
    assert client_obj._backoff(10) <= 0.5


@pytest.mark.asyncio
async def test_blocked_status_contract(client):
    """blocked is a distinct terminal state with completed_at set."""
    from integration_lab.database import create_execution, create_task, update_task_status
    from integration_lab.service import get_async_session_maker

    session_maker = await get_async_session_maker()
    async with session_maker() as session:
        task = await create_task(session, {"task": "Blocked test"})
        await session.commit()
        await create_execution(session, task.id, "run-blocked")
        await session.commit()

        updated = await update_task_status(session, task.id, "blocked")
        await session.commit()
        assert updated is not None
        assert updated.status == "blocked"
        assert updated.completed_at is not None, "blocked is terminal and must set completed_at"


@pytest.mark.asyncio
async def test_execution_blocked_has_completed_at(client, db_session):
    from integration_lab.database import create_execution, create_task, update_execution

    task = await create_task(db_session, {"task": "Blocked execution"})
    await db_session.commit()
    execution = await create_execution(db_session, task.id, "run-blocked")
    await db_session.commit()

    updated = await update_execution(db_session, execution.id, status="blocked")
    await db_session.commit()

    assert updated is not None
    assert updated.status == "blocked"
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_execution_failed_has_completed_at(client, db_session):
    from integration_lab.database import create_execution, create_task, update_execution

    task = await create_task(db_session, {"task": "Failed execution"})
    await db_session.commit()
    execution = await create_execution(db_session, task.id, "run-failed")
    await db_session.commit()

    updated = await update_execution(
        db_session,
        execution.id,
        status="failed",
        trace=[{"status": "failed", "transition_reason": "tool_failed"}],
    )
    await db_session.commit()

    assert updated is not None
    assert updated.status == "failed"
    assert updated.completed_at is not None
    assert updated.trace[-1]["transition_reason"] == "tool_failed"


@pytest.mark.asyncio
async def test_test_mode_works_without_github_token(monkeypatch, db_engine):
    """RUNNER_MODE=test must not require GITHUB_TOKEN.

    Regression: previously get_runtime() raised 503 before checking
    RUNNER_MODE, so test mode was unusable without a token.
    """
    from integration_lab import service
    from integration_lab.service import get_runtime

    settings = IntegrationTestSettings(
        runner_mode="test",
        github_token="",  # explicitly empty
        github_base_url="https://api.github.com",
    )
    monkeypatch.setattr(service, "settings", settings)
    monkeypatch.setattr(service, "engine", db_engine[0])
    monkeypatch.setattr(service, "async_session_maker", db_engine[1])

    # Must not raise — test mode does not build a real IssueApiClient.
    runtime = get_runtime()
    assert runtime.client is None
    assert runtime.planner.plan("anything", runtime.tools()) == []

    # End-to-end: POST /tasks in test mode with no token must succeed.
    settings2 = IntegrationTestSettings(
        runner_mode="test",
        github_token="",
        github_base_url="https://api.github.com",
    )
    monkeypatch.setattr(service, "settings", settings2)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/tasks", json={"task": "Test mode without token"})
        assert response.status_code == 202
        task_id = response.json()["task_id"]

        data = await _wait_for_task(ac, task_id)
        assert data["task_id"] == task_id
        assert data["status"] == "completed"
        assert data["result"] is not None
        assert data["result"]["status"] == "completed"
        assert data["result"]["results"] == []
        assert data["result"]["trace"] == []


@pytest.mark.asyncio
async def test_production_mode_requires_github_token(monkeypatch, db_engine):
    """Production mode (non-test, non-demo) must still reject missing GITHUB_TOKEN."""
    from integration_lab import service
    from integration_lab.service import get_runtime

    settings = IntegrationTestSettings(
        runner_mode="production",
        github_token="",  # missing
    )
    monkeypatch.setattr(service, "settings", settings)

    with pytest.raises(HTTPException) as exc_info:
        get_runtime()
    assert exc_info.value.status_code == 503
    assert "GitHub token not configured" in exc_info.value.detail


@pytest.mark.asyncio
async def test_demo_mode_requires_github_token(monkeypatch, db_engine):
    """Demo mode must still require GITHUB_TOKEN."""
    from integration_lab import service
    from integration_lab.service import get_runtime

    settings = IntegrationTestSettings(
        runner_mode="demo",
        github_token="",  # missing
    )
    monkeypatch.setattr(service, "settings", settings)

    with pytest.raises(HTTPException) as exc_info:
        get_runtime()
    assert exc_info.value.status_code == 503