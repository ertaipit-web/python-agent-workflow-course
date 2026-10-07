import pytest
from taskboard import Task, create_task, filter_tasks, set_status


def test_create_task_trims_title_and_starts_open() -> None:
    assert create_task(1, "  Write tests  ") == Task(1, "Write tests")


@pytest.mark.parametrize("task_id", [0, -1])
def test_create_task_rejects_non_positive_id(task_id: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        create_task(task_id, "Write tests")


def test_create_task_rejects_blank_title() -> None:
    with pytest.raises(ValueError, match="empty"):
        create_task(1, " \t ")


def test_set_status_returns_updated_copy() -> None:
    original = create_task(1, "Write tests")

    updated = set_status(original, " IN_PROGRESS ")

    assert updated == Task(1, "Write tests", "in_progress")
    assert original.status == "open"


def test_set_status_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="unsupported status"):
        set_status(create_task(1, "Write tests"), "blocked")


def test_filter_tasks_returns_matching_tasks_in_input_order() -> None:
    tasks = [
        create_task(1, "First"),
        set_status(create_task(2, "Second"), "done"),
        create_task(3, "Third"),
    ]

    assert filter_tasks(tasks, "open") == [tasks[0], tasks[2]]


def test_filter_tasks_without_status_returns_a_copy() -> None:
    tasks = [create_task(1, "First")]

    result = filter_tasks(tasks)

    assert result == tasks
    assert result is not tasks
