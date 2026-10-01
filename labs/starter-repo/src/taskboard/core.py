from dataclasses import dataclass, replace

STATUSES = frozenset({"open", "in_progress", "done"})


@dataclass(frozen=True)
class Task:
    task_id: int
    title: str
    status: str = "open"


def create_task(task_id: int, title: str) -> Task:
    if task_id < 1:
        raise ValueError("task_id must be positive")

    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("title must not be empty")

    return Task(task_id=task_id, title=normalized_title)


def set_status(task: Task, status: str) -> Task:
    normalized_status = status.strip().lower()
    if normalized_status not in STATUSES:
        raise ValueError(f"unsupported status: {status}")

    return replace(task, status=normalized_status)


def filter_tasks(tasks: list[Task], status: str | None = None) -> list[Task]:
    if status is None:
        return list(tasks)

    return [task for task in tasks if task.status == status]
