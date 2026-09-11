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
from vibepy_studio.internals import child_environment

TODO = FIXTURES / "todo-app"


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

    assert {tool.name for tool in listed.tools} >= {
        "inspect_framework",
        "inspect_app",
        "invoke_tool",
    }


@pytest.mark.integration
async def test_an_inspection_arrives_as_structured_content(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        inspected = await agent.call_tool("inspect_app", {"project": str(TODO)})

    assert inspected.is_error is False
    assert inspected.structured_content is not None
    apps = inspected.structured_content["apps"]
    assert [tool["name"] for tool in apps[0]["tools"]] == [
        "create_todo",
        "list_todos",
        "complete_todo",
    ]
    assert inspected.structured_content["diagnostic"] is None


@pytest.mark.integration
async def test_an_expected_failure_arrives_as_structured_data(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        inspected = await agent.call_tool("inspect_app", {"project": str(tmp_path / "nowhere")})

    assert inspected.is_error is False
    assert inspected.structured_content is not None
    assert inspected.structured_content["diagnostic"]["code"] == "authoring.project_not_found"


@pytest.mark.integration
async def test_invalid_input_arrives_as_the_framework_payload(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        refused = await agent.call_tool("inspect_app", {})

    assert refused.is_error is True
    block = refused.content[0]
    assert isinstance(block, TextContent)
    assert json.loads(block.text)["code"] == "tool.input_invalid"
