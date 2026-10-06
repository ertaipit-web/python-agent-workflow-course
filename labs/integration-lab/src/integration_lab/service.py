from __future__ import annotations

import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from integration_lab.client import IssueApiClient
from integration_lab.config import get_settings
from integration_lab.database import (
    Execution,
    create_execution,
    create_task,
    get_task,
    init_db,
    update_execution,
    update_task_status,
)
from integration_lab.runtime import AgentRuntime, RunReport, ScriptedPlanner

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.WriteLoggerFactory(file=sys.stdout),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

settings = get_settings()
engine = None
async_session_maker = None


async def get_async_session_maker():
    """Get or create the async session maker. Initializes DB if not already done."""
    global async_session_maker, engine
    if async_session_maker is None:
        engine, async_session_maker = await init_db(str(settings.database_url))
    return async_session_maker


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, async_session_maker
    logger.info("starting_up", service=settings.service_name)
    engine, async_session_maker = await init_db(str(settings.database_url))
    yield
    logger.info("shutting_down", service=settings.service_name)
    if engine:
        await engine.dispose()


app = FastAPI(
    title="Agent Course Capstone Service",
    description="Production API for agent workflow execution",
    version="0.1.0",
    lifespan=lifespan,
)


class TaskCreate(BaseModel):
    task: str = Field(..., min_length=1, max_length=5000, description="Task description for the agent")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class TaskResponse(BaseModel):
    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    execution_id: str | None = None


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str
    timestamp: datetime


def get_runtime() -> AgentRuntime:
    if not settings.github_token:
        raise HTTPException(status_code=503, detail="GitHub token not configured")

    client = IssueApiClient(
        base_url=settings.github_base_url,
        token=settings.github_token,
        timeout=2.0,
        max_attempts=2,
    )

    from integration_lab.runtime import Policy
    policy = Policy(
        granted_scopes=frozenset(["repo"]),
        allowed_repositories=frozenset([("*", "*")]),
    )

    planner = ScriptedPlanner(calls=[])
    return AgentRuntime(client=client, policy=policy, planner=planner)


async def execute_agent_task(
    task_id: uuid.UUID,
    task_description: str,
    run_id: str,
) -> None:
    session_maker = await get_async_session_maker()
    async with session_maker() as session:
        execution = await create_execution(session, task_id, run_id)
        await session.commit()
        execution_id = execution.id

    start_time = time.time()
    trace_events = []

    try:
        runtime = get_runtime()
        runtime.run_id = run_id
        runtime.node_id = "issue_agent"

        report: RunReport = runtime.run(task_description)

        trace_events = [
            {
                "run_id": e.run_id,
                "node_id": e.node_id,
                "tool_name": e.tool_name,
                "arguments": e.arguments,
                "status": e.status,
                "detail": e.detail,
                "error_type": e.error_type,
                "transition_reason": e.transition_reason,
            }
            for e in report.trace
        ]

        if report.status == "completed":
            result_data = {
                "status": "completed",
                "results": [dict(r) for r in report.results],
                "trace": trace_events,
            }
            await update_task_status(
                await get_session(),
                task_id,
                "completed",
                result=result_data,
            )
        elif report.status == "needs_approval":
            result_data = {
                "status": "needs_approval",
                "pending_approval": {
                    "tool": report.pending_approval.tool if report.pending_approval else None,
                    "arguments": dict(report.pending_approval.arguments) if report.pending_approval else None,
                },
                "trace": trace_events,
            }
            await update_task_status(
                await get_session(),
                task_id,
                "needs_approval",
                result=result_data,
            )
        else:
            error_msg = report.reason or "Agent execution failed"
            await update_task_status(
                await get_session(),
                task_id,
                "failed",
                error=error_msg,
            )

        session_maker = await get_async_session_maker()
        async with session_maker() as session:
            await update_execution(session, execution_id, status=report.status, trace=trace_events)
            await session.commit()

    except Exception as e:
        logger.exception("task_execution_failed", task_id=str(task_id), error=str(e))
        trace_events.append({
            "run_id": run_id,
            "node_id": "system",
            "tool_name": None,
            "arguments": {},
            "status": "failed",
            "detail": str(e),
            "error_type": type(e).__name__,
            "transition_reason": "system_error",
        })
        session_maker = await get_async_session_maker()
        async with session_maker() as session:
            await update_execution(session, execution_id, status="failed", trace=trace_events)
            await update_task_status(session, task_id, "failed", error=str(e))
            await session.commit()
    finally:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "task_execution_completed",
            task_id=str(task_id),
            run_id=run_id,
            latency_ms=latency_ms,
            status=report.status if 'report' in locals() else "failed",
        )


async def get_session() -> AsyncSession:
    session_maker = await get_async_session_maker()
    return session_maker()


@app.post("/tasks", response_model=TaskResponse, status_code=202)
async def create_task_endpoint(task_create: TaskCreate, background_tasks: BackgroundTasks):
    task_id = uuid.uuid4()
    run_id = f"run-{uuid.uuid4().hex[:8]}"

    session_maker = await get_async_session_maker()
    async with session_maker() as session:
        await create_task(
            session,
            payload={"task": task_create.task, "metadata": task_create.metadata},
        )
        await session.commit()

    background_tasks.add_task(execute_agent_task, task_id, task_create.task, run_id)

    logger.info("task_queued", task_id=str(task_id), run_id=run_id)
    return TaskResponse(task_id=str(task_id), status="queued")


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_endpoint(task_id: str):
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid task_id format")

    session_maker = await get_async_session_maker()
    async with session_maker() as session:
        task = await get_task(session, task_uuid)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    execution_id = None
    session_maker = await get_async_session_maker()
    async with session_maker() as session:
        from sqlalchemy import select
        result = await session.execute(select(Execution).where(Execution.task_id == task_uuid))
        execution = result.scalars().first()
        if execution:
            execution_id = str(execution.id)

    return TaskStatusResponse(
        task_id=str(task.id),
        status=task.status,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result=task.result,
        error=task.error,
        execution_id=execution_id,
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(service=settings.service_name, timestamp=datetime.now(UTC))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning("http_error", status_code=exc.status_code, detail=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_error", path=request.url.path, error=str(exc))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def main():
    import uvicorn
    uvicorn.run(
        "integration_lab.service:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()