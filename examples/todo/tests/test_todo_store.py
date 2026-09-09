"""The sample's store keeps what it was given, where it was told to keep it."""

from pathlib import Path

import pytest
from pydantic import SecretStr

from todo_app.entry import TodoConfig, TodoStore, TodoStoreUnreadable


def test_a_todo_survives_a_new_store_over_the_same_path(tmp_path: Path) -> None:
    config = TodoConfig(db_path=tmp_path / "todo.json", db_key=SecretStr("k"))

    TodoStore(config.db_path, config.db_key).create("buy milk")

    assert [todo.title for todo in TodoStore(config.db_path, config.db_key).list_all()] == [
        "buy milk"
    ]


def test_a_file_stamped_under_another_key_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "todo.json"
    TodoStore(path, SecretStr("one")).create("buy milk")

    with pytest.raises(TodoStoreUnreadable):
        TodoStore(path, SecretStr("two")).list_all()
