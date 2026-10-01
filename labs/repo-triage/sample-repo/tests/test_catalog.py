from catalog import Item, create_item, filter_by_status


def test_create_item_trims_title() -> None:
    assert create_item(1, "  Review report  ") == Item(1, "Review report")


def test_filter_by_status_preserves_input_order() -> None:
    items = [Item(1, "First"), Item(2, "Second", "done"), Item(3, "Third")]

    assert filter_by_status(items, "open") == [items[0], items[2]]
