"""The command that invokes one Tool of an App, run as a real process."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from expense_app.entry import Decision
from notes_app.entry import Note
from test_serve_command import child_environment
from vibepy_core import ErrorCategory, ErrorInfo
from vibepy_core.app.config import environment_for


def run_invoke(
    app: str,
    tool: str,
    request: object,
    *,
    config: dict[str, str] | None = None,
    channel: str = "agent",
    principal: str = "tester",
    roles: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    argv = [
        sys.executable,
        "-m",
        "vibepy_core.invoke",
        app,
        tool,
        "--channel",
        channel,
        "--principal",
        principal,
    ]
    for role in roles:
        argv += ["--role", role]
    return subprocess.run(
        argv,
        input=json.dumps(request),
        capture_output=True,
        text=True,
        env={**child_environment(), **environment_for(config or {})},
        check=False,
    )


def todo_config(tmp_path: Path) -> dict[str, str]:
    return {"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}


def reported(result: subprocess.CompletedProcess[str]) -> ErrorInfo:
    assert result.returncode == 1, result.stderr
    lines = [line for line in result.stderr.splitlines() if line.startswith("{")]
    assert lines, result.stderr
    return ErrorInfo.model_validate(json.loads(lines[-1]))


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
    assert report.code == "tool.not_found"
    assert report.category is ErrorCategory.CALLER
    assert result.stdout == ""


@pytest.mark.integration
def test_invalid_input_is_reported(tmp_path: Path) -> None:
    result = run_invoke("todo-app", "create_todo", {"input": {}}, config=todo_config(tmp_path))
    assert reported(result).code == "tool.input_invalid"


@pytest.mark.integration
def test_invalid_configuration_is_reported() -> None:
    result = run_invoke("todo-app", "list_todos", {"input": {}})
    assert reported(result).code == "config.invalid"


@pytest.mark.integration
def test_a_request_that_is_not_an_object_is_reported() -> None:
    result = run_invoke("todo-app", "list_todos", [1, 2])
    assert reported(result).code == "invoke.request_invalid"


@pytest.mark.integration
def test_an_app_this_environment_does_not_declare_is_reported() -> None:
    result = run_invoke("no-such-app", "list_todos", {"input": {}})
    assert reported(result).code == "package.app_not_declared"


@pytest.mark.integration
def test_channel_and_principal_are_required() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "vibepy_core.invoke", "todo-app", "list_todos"],
        input="{}",
        capture_output=True,
        text=True,
        env=child_environment(),
        check=False,
    )
    assert result.returncode == 2
    assert "--channel" in result.stderr and "--principal" in result.stderr


@pytest.mark.integration
def test_the_old_request_shape_with_config_is_refused(tmp_path: Path) -> None:
    """Configuration on standard input is gone, and a request still carrying it
    fails rather than being silently ignored."""
    result = run_invoke(
        "todo-app", "create_todo", {"config": todo_config(tmp_path), "input": {"title": "milk"}}
    )
    assert reported(result).code == "invoke.request_invalid"


@pytest.mark.integration
def test_a_role_gated_tool_refuses_a_principal_without_the_role() -> None:
    result = run_invoke("expense-app", "approve_expense", {"input": {"id": 1}}, principal="alice")
    payload = reported(result)
    assert payload.code == "tool.forbidden"
    assert payload.details["reason"] == "role_required"


@pytest.mark.integration
def test_a_manager_passes_the_role_gate_through_the_command() -> None:
    result = run_invoke(
        "expense-app", "approve_expense", {"input": {"id": 1}}, principal="bob", roles=("manager",)
    )
    assert result.returncode == 0, result.stderr
    decision = Decision.model_validate(json.loads(result.stdout))
    assert decision.failure is not None
    assert decision.failure.code == "expense.not_found"


@pytest.mark.integration
def test_the_web_channel_reaches_a_tool_that_declares_no_channels() -> None:
    result = run_invoke(
        "notes",
        "measure_note",
        {
            "input": {"body": "hello"},
        },
        config={"api_base_url": "https://example.invalid", "api_token": "t"},
        channel="web",
    )
    assert result.returncode == 0, result.stderr
    assert Note.model_validate(json.loads(result.stdout)).length == 5
