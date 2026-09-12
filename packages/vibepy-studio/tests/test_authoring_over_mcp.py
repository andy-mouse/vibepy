"""Studio's Agent channel as an agent platform reaches it: a stdio process."""

import json
import os
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import TextContent

from tests_support import FIXTURES
from vibepy_core import environment_for
from vibepy_core.errors import ErrorInfo
from vibepy_studio.authoring.models import AppInspection, Invocation
from vibepy_studio.internals import child_environment

TODO = FIXTURES / "todo-app"
EXPENSE = FIXTURES / "expense-app"


def studio_server(root: Path) -> StdioServerParameters:
    """Studio served from this interpreter's environment, over `root`.

    `uv` must be on the child's PATH: the authoring Tools run it.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "vibepy_core.mcp", "studio"],
        env={
            **child_environment(),
            "PATH": os.environ["PATH"],
            **environment_for({"root": str(root), "proxy_port": 8080}),
        },
    )


@pytest.mark.integration
async def test_authoring_tools_are_discoverable(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        listed = await agent.list_tools()

    assert {tool.name for tool in listed.tools} == {
        "inspect_framework",
        "inspect_app",
        "invoke_tool",
    }


@pytest.mark.integration
async def test_read_only_authoring_tools_say_so(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        listed = await agent.list_tools()
    hints = {
        tool.name: (tool.annotations.read_only_hint if tool.annotations else None)
        for tool in listed.tools
    }
    assert hints == {"inspect_framework": True, "inspect_app": True, "invoke_tool": None}


@pytest.mark.integration
async def test_an_inspection_arrives_as_structured_content(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        inspected = await agent.call_tool("inspect_app", {"project": str(TODO)})

    assert inspected.is_error is False
    assert inspected.structured_content is not None
    inspection = AppInspection.model_validate(inspected.structured_content)
    assert [tool.name for tool in inspection.apps[0].description.tools] == [
        "create_todo",
        "list_todos",
        "complete_todo",
    ]
    assert inspection.diagnostic is None


@pytest.mark.integration
async def test_an_expected_failure_arrives_as_structured_data(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        inspected = await agent.call_tool("inspect_app", {"project": str(tmp_path / "nowhere")})

    assert inspected.is_error is False
    assert inspected.structured_content is not None
    inspection = AppInspection.model_validate(inspected.structured_content)
    assert inspection.diagnostic is not None
    assert inspection.diagnostic.code == "authoring.project_not_found"


@pytest.mark.integration
async def test_invalid_input_arrives_as_the_framework_payload(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        refused = await agent.call_tool("inspect_app", {})

    assert refused.is_error is True
    block = refused.content[0]
    assert isinstance(block, TextContent)
    assert ErrorInfo.model_validate(json.loads(block.text)).code == "tool.input_invalid"


@pytest.mark.integration
async def test_the_agents_own_channel_and_principal_reach_the_invoked_tool(tmp_path: Path) -> None:
    """Studio forwards what it was given, and grants itself no role on the way."""
    async with Client(studio_server(tmp_path / "studio")) as agent:
        invoked = await agent.call_tool(
            "invoke_tool",
            {
                "project": str(EXPENSE),
                "app": "expense-app",
                "tool": "approve_expense",
                "input": {"id": 1},
                "config": {},
            },
        )

    assert invoked.is_error is False
    assert invoked.structured_content is not None
    diagnostic = Invocation.model_validate(invoked.structured_content).diagnostic
    assert diagnostic is not None
    assert diagnostic.code == "tool.forbidden"
    assert diagnostic.details["reason"] == "role_required"
    assert diagnostic.details["principal"] == "agent"
    assert diagnostic.details["channel"] == "agent"
