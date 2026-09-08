"""The dual-channel contract from docs/architecture/runtime.md.

Both channels reach one Tool implementation over one resource, so neither keeps
a backend of its own. This test is constitutional: it stays for the life of the
project.

What it does not claim is that a deployed Plugin shares one resource across its
channels. ADR-017 puts each channel in its own process, so sharing is a property
of the composition an entrypoint or a test arranges, never a framework
guarantee. Here one lifespan is composed into both channels precisely so that a
private backend on either side would show up as a divergence.

It does not assert that every Tool belongs on every channel. Deciding that a
Tool is hidden from a channel is M14.
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from mcp.client import Client
from mcp.types import TextContent
from nicegui.testing import User

from tests.todo_fixture import TODO_PLUGIN, TodoList, TodoStore
from vibepy.adapters.mcp import build_mcp_server
from vibepy.adapters.nicegui import register_pages
from vibepy.plugin import Lifespan, page_runtime_for


def one_store() -> Lifespan[TodoStore]:
    """One resource composed into both channels, so a private backend shows."""
    store = TodoStore()

    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[TodoStore]:
        yield store

    return lifespan


def titles(result: object) -> list[str]:
    """Read the titles back through the Tool's own output model.

    Digging through the raw mapping would assert against a shape no contract
    guarantees; the output model is the contract.
    """
    return [todo.title for todo in TodoList.model_validate(result).todos]


async def test_both_channels_reach_one_backend(user: User) -> None:
    lifespan = one_store()

    async with page_runtime_for(TODO_PLUGIN, lifespan) as pages:
        register_pages(TODO_PLUGIN, pages)

        async with Client(build_mcp_server(TODO_PLUGIN, lifespan)) as agent:
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
