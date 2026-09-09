"""What the sample Apps guarantee to anyone who copies one.

A sample is read as a pattern, so what it demonstrates is a contract of this
repository even though no framework code imports it. These live here rather than
beside the sample: the samples are not products with test suites of their own,
and every other test that reaches for one is here too.
"""

from pathlib import Path

import pytest
from pydantic import SecretStr

from todo_app.entry import TodoConfig, TodoStore, TodoStoreUnreadable
from vibepy_core.app.package import discover_apps


def test_the_todo_distribution_declares_its_app() -> None:
    declared = {ref.app_name: ref for ref in discover_apps()}
    assert "todo-app" in declared, "an App's declared name need not be its folder's"
    ref = declared["todo-app"]
    assert ref.distribution == "vibepy-todo"
    assert (ref.module, ref.attr) == ("todo_app.entry", "APP")


def test_the_notes_distribution_declares_an_app_without_pages() -> None:
    declared = {ref.app_name for ref in discover_apps()}
    assert "notes" in declared


def test_a_todo_survives_a_new_store_over_the_same_path(tmp_path: Path) -> None:
    """The sample keeps what it is given, where it was told to keep it.

    An App whose store lived in memory would teach that a Page and an agent may
    disagree the moment either restarts, which is the opposite of what
    `docs/architecture/app-model.md` asks of an App with two channels.
    """
    config = TodoConfig(db_path=tmp_path / "todo.json", db_key=SecretStr("k"))

    TodoStore(config.db_path, config.db_key).create("buy milk")

    assert [todo.title for todo in TodoStore(config.db_path, config.db_key).list_all()] == [
        "buy milk"
    ]


def test_a_file_stamped_under_another_key_is_refused(tmp_path: Path) -> None:
    """The secret the sample declares is one it uses, not one it merely names."""
    path = tmp_path / "todo.json"
    TodoStore(path, SecretStr("one")).create("buy milk")

    with pytest.raises(TodoStoreUnreadable):
        TodoStore(path, SecretStr("two")).list_all()
