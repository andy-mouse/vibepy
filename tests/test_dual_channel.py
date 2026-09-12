"""The dual-channel contract from docs/architecture/runtime.md.

Both channels reach one Tool implementation over one resource, so neither keeps
a backend of its own. This test is constitutional: it stays for the life of the
project.

What it does not claim is that a deployed App shares one resource across its
channels. ADR-017 puts each channel in its own process, so sharing is a property
of the composition an entrypoint or a test arranges, never a framework
guarantee. Here one lifespan is composed into both channels precisely so that a
private backend on either side would show up as a divergence.

It does not assert that every Tool belongs on every channel. Deciding that a
Tool is hidden from a channel is M14.
"""

import json
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.client import Client
from mcp.types import TextContent
from nicegui.testing import User

from todo_app.entry import TODO_APP, TodoConfig, TodoList, TodoStore
from vibepy_core import Principal
from vibepy_core.adapters.mcp import build_mcp_server
from vibepy_core.adapters.nicegui import register_pages
from vibepy_core.app import Lifespan, page_runtime_for


def one_store(config: Mapping[str, object], /) -> Lifespan[TodoStore, TodoConfig]:
    """One resource composed into both channels, so a private backend shows."""
    described = TodoConfig.model_validate(config)
    store = TodoStore(described.db_path, described.db_key)

    @asynccontextmanager
    async def lifespan(_config: TodoConfig) -> AsyncGenerator[TodoStore]:
        yield store

    return lifespan


def titles(result: object) -> list[str]:
    """Read the titles back through the Tool's own output model.

    Digging through the raw mapping would assert against a shape no contract
    guarantees; the output model is the contract.
    """
    return [todo.title for todo in TodoList.model_validate(result).todos]


async def test_both_channels_reach_one_backend(user: User, tmp_path: Path) -> None:
    config = {"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}
    lifespan = one_store(config)

    async with page_runtime_for(TODO_APP, lifespan, config=config) as pages:
        register_pages(TODO_APP, pages)

        async with Client(
            build_mcp_server(TODO_APP, lifespan, config=config, principal=Principal(id="agent"))
        ) as agent:
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
