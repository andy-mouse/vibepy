"""One Tool of a project's App, invoked through the framework's own window."""

from pathlib import Path

import pytest

from tests_support import FIXTURES, studio
from vibepy_core import ErrorCategory
from vibepy_studio.authoring.models import Invocation

TODO = str(FIXTURES / "todo-app")


def config(tmp_path: Path) -> dict[str, str]:
    return {"db_path": str(tmp_path / "todo.json"), "db_key": "k"}


@pytest.mark.integration
async def test_a_tool_is_invoked_and_a_later_call_sees_what_it_wrote(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        created = await tools.invoke(
            "invoke_tool",
            {
                "project": TODO,
                "app": "todo-app",
                "tool": "create_todo",
                "input": {"title": "milk"},
                "config": config(tmp_path),
            },
        )
        listed = await tools.invoke(
            "invoke_tool",
            {"project": TODO, "app": "todo-app", "tool": "list_todos", "config": config(tmp_path)},
        )
    assert isinstance(created, Invocation) and isinstance(listed, Invocation)
    assert created.diagnostic is None, created.diagnostic
    assert created.output is not None and created.output["title"] == "milk"
    assert listed.output is not None
    assert [todo["title"] for todo in listed.output["todos"]] == ["milk"]  # type: ignore[index]


@pytest.mark.integration
async def test_a_tool_the_app_does_not_declare_arrives_as_the_childs_report(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        answered = await tools.invoke(
            "invoke_tool",
            {
                "project": TODO,
                "app": "todo-app",
                "tool": "no_such_tool",
                "config": config(tmp_path),
            },
        )
    assert isinstance(answered, Invocation)
    assert answered.output is None
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "tool.not_found"
    assert answered.diagnostic.category == ErrorCategory.CALLER


@pytest.mark.integration
async def test_invalid_input_and_invalid_configuration_arrive_as_data(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        bad_input = await tools.invoke(
            "invoke_tool",
            {"project": TODO, "app": "todo-app", "tool": "create_todo", "config": config(tmp_path)},
        )
        bad_config = await tools.invoke(
            "invoke_tool", {"project": TODO, "app": "todo-app", "tool": "list_todos"}
        )
    assert isinstance(bad_input, Invocation) and bad_input.diagnostic is not None
    assert bad_input.diagnostic.code == "tool.input_invalid"
    assert isinstance(bad_config, Invocation) and bad_config.diagnostic is not None
    assert bad_config.diagnostic.code == "config.invalid"


async def test_a_directory_without_a_pyproject_is_not_a_project(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        answered = await tools.invoke(
            "invoke_tool", {"project": str(tmp_path / "nowhere"), "app": "x", "tool": "y"}
        )
    assert isinstance(answered, Invocation) and answered.diagnostic is not None
    assert answered.diagnostic.code == "authoring.project_not_found"
