"""The sample Apps are distributions, discoverable without importing them."""

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
