"""The dual-channel contract from docs/architecture/runtime.md.

Both channels converge on one ToolRuntime, so neither keeps a backend of its
own. This test is constitutional: it stays for the life of the project.

It does not assert that every Tool belongs on every channel. Deciding that a
Tool is hidden from a channel is M14.
"""

import json

from mcp.client import Client
from mcp.server import Server
from mcp.types import TextContent
from nicegui.testing import User

from tests.lifecycle import started
from tests.todo_fixture import TodoList, TodoStore, build_todo_app
from vibepy.adapters.mcp import build_mcp_server
from vibepy.adapters.nicegui import register_pages
from vibepy.app import AppRuntime


def build_server(app_under_test: AppRuntime[TodoStore]) -> Server[None]:
    return build_mcp_server(app_under_test)


def titles(result: object) -> list[str]:
    """Read the titles back through the Tool's own output model.

    Digging through the raw mapping would assert against a shape no contract
    guarantees; the output model is the contract.
    """
    return [todo.title for todo in TodoList.model_validate(result).todos]


async def test_both_channels_share_one_backend_state(user: User) -> None:
    async with started(build_todo_app()) as app_under_test:
        register_pages(app_under_test)

        async with Client(build_server(app_under_test)) as agent:
            await agent.call_tool("create_todo", {"title": "from the agent"})

            await user.open("/todos")
            await user.should_see("todo: from the agent")

            user.find("title").type("from the human")
            user.find("Add").click()
            await user.should_see("todo: from the human")

            listed = await agent.call_tool("list_todos", {})

    assert titles(listed.structured_content) == ["from the agent", "from the human"]
    block = listed.content[0]
    assert isinstance(block, TextContent)
    assert titles(json.loads(block.text)) == ["from the agent", "from the human"]
