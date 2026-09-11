"""The command that invokes one Tool of an App, run as a real process."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_serve_command import child_environment
from vibepy_core import environment_for


def run_invoke(
    app: str, tool: str, request: object, *, config: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "vibepy_core.invoke", app, tool],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        env={**child_environment(), **environment_for(config or {})},
        check=False,
    )


def todo_config(tmp_path: Path) -> dict[str, str]:
    return {"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}


def reported(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 1, result.stderr
    lines = [line for line in result.stderr.splitlines() if line.startswith("{")]
    assert lines, result.stderr
    return json.loads(lines[-1])


@pytest.mark.integration
def test_a_tool_is_invoked_and_its_output_written(tmp_path: Path) -> None:
    result = run_invoke(
        "todo-app", "create_todo", {"input": {"title": "milk"}}, config=todo_config(tmp_path)
    )
    assert result.returncode == 0, result.stderr
    written = json.loads(result.stdout)
    assert written["title"] == "milk"
    assert written["done"] is False


@pytest.mark.integration
def test_a_second_invocation_sees_what_the_first_wrote(tmp_path: Path) -> None:
    config = todo_config(tmp_path)
    run_invoke("todo-app", "create_todo", {"input": {"title": "milk"}}, config=config)
    result = run_invoke("todo-app", "list_todos", {"input": {}}, config=config)
    assert result.returncode == 0, result.stderr
    assert [todo["title"] for todo in json.loads(result.stdout)["todos"]] == ["milk"]


@pytest.mark.integration
def test_an_unknown_tool_is_reported(tmp_path: Path) -> None:
    result = run_invoke("todo-app", "no_such_tool", {"input": {}}, config=todo_config(tmp_path))
    report = reported(result)
    assert report["code"] == "tool.not_found"
    assert report["category"] == "caller"
    assert result.stdout == ""


@pytest.mark.integration
def test_invalid_input_is_reported(tmp_path: Path) -> None:
    result = run_invoke("todo-app", "create_todo", {"input": {}}, config=todo_config(tmp_path))
    assert reported(result)["code"] == "tool.input_invalid"


@pytest.mark.integration
def test_invalid_configuration_is_reported() -> None:
    result = run_invoke("todo-app", "list_todos", {"input": {}})
    assert reported(result)["code"] == "config.invalid"


@pytest.mark.integration
def test_a_request_that_is_not_an_object_is_reported() -> None:
    result = run_invoke("todo-app", "list_todos", [1, 2])
    assert reported(result)["code"] == "invoke.request_invalid"


@pytest.mark.integration
def test_an_app_this_environment_does_not_declare_is_reported() -> None:
    result = run_invoke("no-such-app", "list_todos", {"input": {}})
    assert reported(result)["code"] == "package.app_not_declared"


@pytest.mark.integration
def test_the_old_request_shape_with_config_is_refused(tmp_path: Path) -> None:
    """Configuration on standard input is gone, and a request still carrying it
    fails rather than being silently ignored."""
    result = run_invoke(
        "todo-app", "create_todo", {"config": todo_config(tmp_path), "input": {"title": "milk"}}
    )
    assert reported(result)["code"] == "invoke.request_invalid"
