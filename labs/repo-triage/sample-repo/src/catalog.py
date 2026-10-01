from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    item_id: int
    title: str
    status: str = "open"


def create_item(item_id: int, title: str) -> Item:
    if item_id < 1:
        raise ValueError("item_id must be positive")
    if not title.strip():
        raise ValueError("title must not be empty")
    return Item(item_id=item_id, title=title.strip())


def filter_by_status(items: list[Item], status: str | None = None) -> list[Item]:
    if status is None:
        return list(items)
    return [item for item in items if item.status == status]
