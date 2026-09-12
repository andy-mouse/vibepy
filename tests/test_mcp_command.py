"""The command that opens an App's Agent channel over stdio, run as a real process."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import TextContent

from test_serve_command import child_environment, reported_failure
from vibepy_core import ErrorCategory
from vibepy_core.app.config import environment_for


def todo_server(tmp_path: Path) -> StdioServerParameters:
    """`vibepy-todo` served from this interpreter's environment, configured for `tmp_path`."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "vibepy_core.mcp", "todo-app"],
        env={
            **child_environment(),
            **environment_for({"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}),
        },
    )


@pytest.mark.integration
async def test_declared_tools_are_discoverable_over_stdio(tmp_path: Path) -> None:
    async with Client(todo_server(tmp_path)) as agent:
        listed = await agent.list_tools()

    assert {tool.name for tool in listed.tools} >= {"create_todo", "list_todos", "complete_todo"}


@pytest.mark.integration
async def test_a_call_returns_structured_content_over_stdio(tmp_path: Path) -> None:
    async with Client(todo_server(tmp_path)) as agent:
        created = await agent.call_tool("create_todo", {"title": "milk"})

    assert created.is_error is False
    assert created.structured_content is not None
    assert created.structured_content["title"] == "milk"
    block = created.content[0]
    assert isinstance(block, TextContent)
    assert json.loads(block.text)["title"] == "milk"


@pytest.mark.integration
def test_an_unknown_app_name_fails_with_the_framework_code() -> None:
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.mcp", "absent"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode == 1
    assert finished.stdout == b""
    assert reported_failure(finished.stderr).code == "package.app_not_declared"


@pytest.mark.integration
def test_a_window_that_will_not_open_ends_the_process() -> None:
    """No `VIBEPY_*` is set, so the window refuses and the process exits before
    any client message; nothing but MCP may reach stdout, and nothing did."""
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.mcp", "todo-app"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        env=child_environment(),
        timeout=60,
    )

    assert finished.returncode == 1
    assert finished.stdout == b""
    reported = reported_failure(finished.stderr)
    assert reported.code == "config.invalid"
    assert reported.category is ErrorCategory.CALLER
