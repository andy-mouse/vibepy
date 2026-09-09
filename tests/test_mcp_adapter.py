import ast
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.server import Server
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, CallToolResult, TextContent
from pydantic import BaseModel, TypeAdapter

from tests.lifecycle import no_dependencies
from vibepy_core.adapters.mcp import build_mcp_server, to_mcp_tool
from vibepy_core.app import AppDefinition, NoConfig
from vibepy_core.errors import UNHANDLED_CODE, ErrorCategory, VibepyError
from vibepy_core.tool import Tool, ToolContext, ToolDefinition, ToolRuntime


class CreateTodoInput(BaseModel):
    title: str


class EmptyInput(BaseModel):
    pass


class Todo(BaseModel):
    id: int
    title: str
    done: bool


class TodoList(BaseModel):
    todos: list[Todo]


def create_todo_definition() -> ToolDefinition[CreateTodoInput, Todo]:
    return ToolDefinition(
        name="create_todo",
        description="Create a todo",
        input_model=CreateTodoInput,
        output_model=Todo,
    )


def list_todos_definition() -> ToolDefinition[EmptyInput, TodoList]:
    return ToolDefinition(
        name="list_todos",
        description="List every todo",
        input_model=EmptyInput,
        output_model=TodoList,
    )


def test_projection_carries_the_declaration_over() -> None:
    projected = to_mcp_tool(create_todo_definition())

    assert projected.name == "create_todo"
    assert projected.description == "Create a todo"


def test_projected_schemas_are_derived_from_the_models() -> None:
    projected = to_mcp_tool(create_todo_definition())

    assert projected.input_schema == CreateTodoInput.model_json_schema()
    assert projected.output_schema == Todo.model_json_schema()


def test_a_nested_output_model_keeps_its_definitions() -> None:
    projected = to_mcp_tool(list_todos_definition())

    assert projected.output_schema == TodoList.model_json_schema()
    assert projected.output_schema is not None
    assert "$defs" in projected.output_schema


APP_ID = "test-app"


class TodoFixture:
    """The Todo sample from docs/roadmap.md, plus the ToolContexts its handlers saw."""

    def __init__(self) -> None:
        self.todos: list[Todo] = []
        self.contexts: list[ToolContext[None]] = []

    async def create_todo(self, ctx: ToolContext[None], payload: CreateTodoInput) -> Todo:
        self.contexts.append(ctx)
        todo = Todo(id=len(self.todos) + 1, title=payload.title, done=False)
        self.todos.append(todo)
        return todo

    async def list_todos(self, ctx: ToolContext[None], payload: EmptyInput) -> TodoList:
        self.contexts.append(ctx)
        return TodoList(todos=list(self.todos))

    def tools(self) -> list[Tool[None]]:
        return [
            Tool(definition=create_todo_definition(), handler=self.create_todo),
            Tool(definition=list_todos_definition(), handler=self.list_todos),
        ]


@asynccontextmanager
async def server_for(tools: list[Tool[None]]) -> AsyncGenerator[Server[ToolRuntime[None]]]:
    """One App with no application-scoped resource: these fixtures hold their own."""
    yield build_mcp_server(
        AppDefinition(
            app_id=APP_ID,
            name="Test",
            version="0.0.0",
            config=NoConfig,
            tools=tools,
            pages=[],
        ),
        no_dependencies,
        config={},
    )


async def test_framework_tools_appear_in_mcp_discovery() -> None:
    fixture = TodoFixture()

    async with server_for(fixture.tools()) as server, Client(server) as client:
        listed = await client.list_tools()

    assert [tool.name for tool in listed.tools] == ["create_todo", "list_todos"]
    assert [tool.description for tool in listed.tools] == ["Create a todo", "List every todo"]


async def test_discovered_schemas_are_the_projected_schemas() -> None:
    fixture = TodoFixture()

    async with server_for(fixture.tools()) as server, Client(server) as client:
        listed = await client.list_tools()

    assert listed.tools[0].input_schema == CreateTodoInput.model_json_schema()
    assert listed.tools[0].output_schema == Todo.model_json_schema()
    assert listed.tools[1].output_schema == TodoList.model_json_schema()


async def test_a_call_reaches_the_tool_and_changes_app_state() -> None:
    fixture = TodoFixture()

    async with server_for(fixture.tools()) as server, Client(server) as client:
        await client.call_tool("create_todo", {"title": "milk"})

    assert [todo.title for todo in fixture.todos] == ["milk"]


async def test_the_invocation_context_is_created_by_the_tool_runtime() -> None:
    fixture = TodoFixture()

    async with server_for(fixture.tools()) as server, Client(server) as client:
        await client.call_tool("create_todo", {"title": "milk"})
        await client.call_tool("create_todo", {"title": "eggs"})

    first, second = fixture.contexts
    assert first.app_id == APP_ID
    assert second.app_id == APP_ID
    assert first.invocation_id != ""
    assert first.invocation_id != second.invocation_id


async def test_a_result_is_the_validated_output_model() -> None:
    fixture = TodoFixture()

    async with server_for(fixture.tools()) as server, Client(server) as client:
        result = await client.call_tool("create_todo", {"title": "milk"})

    expected = Todo(id=1, title="milk", done=False).model_dump(by_alias=True, mode="json")
    assert result.is_error is False
    assert result.structured_content == expected
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert json.loads(block.text) == expected


async def test_a_nested_result_survives_the_round_trip() -> None:
    fixture = TodoFixture()

    async with server_for(fixture.tools()) as server, Client(server) as client:
        await client.call_tool("create_todo", {"title": "milk"})
        result = await client.call_tool("list_todos", {})

    assert result.structured_content == {"todos": [{"id": 1, "title": "milk", "done": False}]}


class Boom(Exception):
    """A domain exception owned by the fixture, not by the framework."""


class BrokenFixture:
    """Tools that fail: one raises, one returns output its own model rejects."""

    async def explode(self, ctx: ToolContext[None], payload: EmptyInput) -> Todo:
        raise Boom("the handler failed")

    async def lie(self, ctx: ToolContext[None], payload: EmptyInput) -> Todo:
        return Todo.model_construct(id="not-an-integer", title="broken", done=False)

    def tools(self) -> list[Tool[None]]:
        return [
            Tool(
                definition=ToolDefinition(
                    name="explode",
                    description="Always raises",
                    input_model=EmptyInput,
                    output_model=Todo,
                ),
                handler=self.explode,
            ),
            Tool(
                definition=ToolDefinition(
                    name="lie",
                    description="Returns invalid output",
                    input_model=EmptyInput,
                    output_model=Todo,
                ),
                handler=self.lie,
            ),
        ]


_ERROR_PAYLOAD = TypeAdapter(dict[str, object])


def _payload(result: CallToolResult) -> dict[str, object]:
    """The error an agent reads out of a failed result."""
    content = result.content[0]
    assert isinstance(content, TextContent)
    return _ERROR_PAYLOAD.validate_json(content.text)


async def test_an_unknown_tool_name_is_a_protocol_error() -> None:
    fixture = TodoFixture()

    async with server_for(fixture.tools()) as server, Client(server) as client:
        with pytest.raises(MCPError) as raised:
            await client.call_tool("no_such_tool", {})

    assert raised.value.code == INVALID_PARAMS
    assert raised.value.data == {
        "code": "tool.not_found",
        "category": ErrorCategory.CALLER.value,
        "message": raised.value.message,
        "details": {"tool_name": "no_such_tool"},
    }


async def test_invalid_input_is_reported_inside_the_result() -> None:
    fixture = TodoFixture()

    async with server_for(fixture.tools()) as server, Client(server) as client:
        result = await client.call_tool("create_todo", {})

    assert result.is_error is True
    assert result.structured_content is None
    payload = _payload(result)
    assert payload["code"] == "tool.input_invalid"
    assert payload["category"] == ErrorCategory.CALLER.value
    assert payload["details"] == {"tool_name": "create_todo"}


async def test_a_raising_handler_is_reported_inside_the_result() -> None:
    async with server_for(BrokenFixture().tools()) as server, Client(server) as client:
        result = await client.call_tool("explode", {})

    assert result.is_error is True
    payload = _payload(result)
    assert payload["code"] == UNHANDLED_CODE
    assert payload["category"] == ErrorCategory.EXECUTION.value
    assert payload["details"] == {}


async def test_an_app_defined_error_answers_with_a_result_not_a_protocol_error() -> None:
    """The public base is subclassable, and a subclass must not escape `except`.

    `call_tool` catches `Exception` so a app defect cannot surface as a protocol
    error. Normalizing an App's own subclass used to raise inside that clause,
    which was the protocol error the clause exists to prevent.
    """

    class AppOwnError(VibepyError):
        code = "app.its_own"

    async def raises(_ctx: ToolContext[None], _payload: EmptyInput) -> Todo:
        raise AppOwnError("the app's own failure")

    tools = [
        Tool(
            definition=ToolDefinition(
                name="app_error",
                description="Raises an App-defined subclass of the public base",
                input_model=EmptyInput,
                output_model=Todo,
            ),
            handler=raises,
        )
    ]

    async with server_for(tools) as server, Client(server) as client:
        result = await client.call_tool("app_error", {})

    assert result.is_error is True
    payload = _payload(result)
    assert payload["code"] == UNHANDLED_CODE
    assert payload["category"] == ErrorCategory.EXECUTION.value
    assert payload["details"] == {}


async def test_invalid_output_is_reported_inside_the_result() -> None:
    async with server_for(BrokenFixture().tools()) as server, Client(server) as client:
        result = await client.call_tool("lie", {})

    assert result.is_error is True
    payload = _payload(result)
    assert payload["code"] == "tool.output_invalid"
    assert payload["category"] == ErrorCategory.EXECUTION.value
    assert payload["details"] == {"tool_name": "lie"}


async def test_a_failure_never_carries_a_structured_result() -> None:
    """A declared output schema binds structuredContent, so an error may not use it.

    https://modelcontextprotocol.io/specification/2025-06-18/server/tools
    """
    async with server_for(BrokenFixture().tools()) as server, Client(server) as client:
        explode = await client.call_tool("explode", {})
        lie = await client.call_tool("lie", {})

    assert explode.structured_content is None
    assert lie.structured_content is None


def _imported_module_names(source: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_the_core_packages_do_not_import_mcp() -> None:
    package = Path(__file__).resolve().parent.parent / "src" / "vibepy_core"
    modules = (
        sorted((package / "tool").glob("*.py"))
        + sorted((package / "page").glob("*.py"))
        + sorted((package / "app").glob("*.py"))
    )
    assert modules != []

    offenders = [
        module.name
        for module in modules
        for name in _imported_module_names(module.read_text(encoding="utf-8"))
        if name == "mcp" or name.startswith("mcp.")
    ]

    assert offenders == []
