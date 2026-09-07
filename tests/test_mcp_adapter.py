import ast
import json
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.server import Server
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, TextContent
from pydantic import BaseModel

from vibepy.adapters.mcp import build_mcp_server, to_mcp_tool
from vibepy.tool import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolRuntime


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
        self.contexts: list[ToolContext] = []

    async def create_todo(self, ctx: ToolContext, payload: CreateTodoInput) -> Todo:
        self.contexts.append(ctx)
        todo = Todo(id=len(self.todos) + 1, title=payload.title, done=False)
        self.todos.append(todo)
        return todo

    async def list_todos(self, ctx: ToolContext, payload: EmptyInput) -> TodoList:
        self.contexts.append(ctx)
        return TodoList(todos=list(self.todos))

    def registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(Tool(definition=create_todo_definition(), handler=self.create_todo))
        registry.register(Tool(definition=list_todos_definition(), handler=self.list_todos))
        return registry


def build_server(registry: ToolRegistry) -> Server[None]:
    return build_mcp_server(
        name="test-app",
        version="0.0.0",
        registry=registry,
        runtime=ToolRuntime(app_id=APP_ID, registry=registry),
    )


async def test_framework_tools_appear_in_mcp_discovery() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        listed = await client.list_tools()

    assert [tool.name for tool in listed.tools] == ["create_todo", "list_todos"]
    assert [tool.description for tool in listed.tools] == ["Create a todo", "List every todo"]


async def test_discovered_schemas_are_the_projected_schemas() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        listed = await client.list_tools()

    assert listed.tools[0].input_schema == CreateTodoInput.model_json_schema()
    assert listed.tools[0].output_schema == Todo.model_json_schema()
    assert listed.tools[1].output_schema == TodoList.model_json_schema()


async def test_a_call_reaches_the_tool_and_changes_app_state() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        await client.call_tool("create_todo", {"title": "milk"})

    assert [todo.title for todo in fixture.todos] == ["milk"]


async def test_the_invocation_context_is_created_by_the_tool_runtime() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        await client.call_tool("create_todo", {"title": "milk"})
        await client.call_tool("create_todo", {"title": "eggs"})

    first, second = fixture.contexts
    assert first.app_id == APP_ID
    assert second.app_id == APP_ID
    assert first.invocation_id != ""
    assert first.invocation_id != second.invocation_id


async def test_a_result_is_the_validated_output_model() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        result = await client.call_tool("create_todo", {"title": "milk"})

    expected = Todo(id=1, title="milk", done=False).model_dump(by_alias=True, mode="json")
    assert result.is_error is False
    assert result.structured_content == expected
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert json.loads(block.text) == expected


async def test_a_nested_result_survives_the_round_trip() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        await client.call_tool("create_todo", {"title": "milk"})
        result = await client.call_tool("list_todos", {})

    assert result.structured_content == {"todos": [{"id": 1, "title": "milk", "done": False}]}


class Boom(Exception):
    """A domain exception owned by the fixture, not by the framework."""


class BrokenFixture:
    """Tools that fail: one raises, one returns output its own model rejects."""

    async def explode(self, ctx: ToolContext, payload: EmptyInput) -> Todo:
        raise Boom("the handler failed")

    async def lie(self, ctx: ToolContext, payload: EmptyInput) -> Todo:
        return Todo.model_construct(id="not-an-integer", title="broken", done=False)

    def registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(
            Tool(
                definition=ToolDefinition(
                    name="explode",
                    description="Always raises",
                    input_model=EmptyInput,
                    output_model=Todo,
                ),
                handler=self.explode,
            )
        )
        registry.register(
            Tool(
                definition=ToolDefinition(
                    name="lie",
                    description="Returns invalid output",
                    input_model=EmptyInput,
                    output_model=Todo,
                ),
                handler=self.lie,
            )
        )
        return registry


async def test_an_unknown_tool_name_is_a_protocol_error() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        with pytest.raises(MCPError) as raised:
            await client.call_tool("no_such_tool", {})

    assert raised.value.code == INVALID_PARAMS
    assert "no_such_tool" in raised.value.message


async def test_invalid_input_is_reported_inside_the_result() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        result = await client.call_tool("create_todo", {})

    assert result.is_error is True
    assert result.structured_content is None


async def test_a_raising_handler_is_reported_inside_the_result() -> None:
    async with Client(build_server(BrokenFixture().registry())) as client:
        result = await client.call_tool("explode", {})

    assert result.is_error is True


async def test_invalid_output_is_reported_inside_the_result() -> None:
    async with Client(build_server(BrokenFixture().registry())) as client:
        result = await client.call_tool("lie", {})

    assert result.is_error is True


def _imported_module_names(source: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_the_core_tool_and_page_packages_do_not_import_mcp() -> None:
    package = Path(__file__).resolve().parent.parent / "src" / "vibepy"
    modules = sorted((package / "tool").glob("*.py")) + sorted((package / "page").glob("*.py"))
    assert modules != []

    offenders = [
        module.name
        for module in modules
        for name in _imported_module_names(module.read_text(encoding="utf-8"))
        if name == "mcp" or name.startswith("mcp.")
    ]

    assert offenders == []
