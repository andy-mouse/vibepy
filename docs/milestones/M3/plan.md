# M3 MCP Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An App's Tools are discoverable and callable over the real MCP protocol, with every call going through ToolRuntime and no MCP type reaching the core Tool model.

**Architecture:** `src/vibepy/adapters/mcp/` holds the whole Agent channel: `projection.py` turns a `ToolDefinition` into an `mcp.types.Tool` with schemas derived from Pydantic, and `server.py` builds a low-level SDK `Server` whose `list_tools` enumerates `ToolRegistry.definitions()` and whose `call_tool` does one thing — `await runtime.invoke(...)` — then translates the validated output model and the framework's errors into MCP shapes. No transport is built: `build_mcp_server()` returns the `Server` object and never runs it. `ToolRegistry` gains declaration storage first, because M1 discarded each `ToolDefinition` at registration and discovery needs it.

**Tech Stack:** Python 3.12, Pydantic v2, official MCP Python SDK 2.1.x (low-level `mcp.server.Server`, in-memory `mcp.client.Client` for tests), pytest with `pytest-asyncio` in `asyncio_mode = "auto"`, ruff, pyright strict, uv.

## Global Constraints

- Spec: `docs/milestones/M3/spec.md`. Implement it exactly; build nothing beyond it.
- Neither `Any` nor `cast` appears anywhere in `src/` or `tests/`.
- Optional and configuration parameters are keyword-only.
- Framework exceptions derive from `VibepyError`. Exception types are the contract, message strings are not.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- Tests verify public contracts, not internals.
- `make lint typecheck test` passes at the end of every task.
- Line length 100 (`ruff`), lint rules `E, F, I, UP, B, ASYNC, RUF`.
- A pre-commit hook runs ruff and pyright on commit; a failing hook means the commit did not happen.
- Do not edit `docs/roadmap.md`.
- Nothing under `src/vibepy/tool/` or `src/vibepy/page/` may import `mcp`. Task 5 makes this a test.
- `vibepy/__init__.py` is not touched: importing `vibepy` must not require the MCP SDK.
- The only new dependency is `mcp>=2.1`, added in Task 2.

## Verified SDK facts

These were checked against `mcp` 2.1.1 on Python 3.12. Do not redesign around a remembered API.

- `Server(name, *, version=..., lifespan=..., on_list_tools=..., on_call_tool=...)`. Handlers are constructor arguments, not decorators.
- `types.Tool` fields are `name`, `description`, `input_schema`, `output_schema` (constructible under those Python names).
- `types.CallToolResult` fields are `content`, `structured_content`, `is_error`.
- A handler's `ListToolsResult` carries a Pydantic `model_json_schema()` through a `list_tools` round trip byte-identical, `$defs`/`$ref` included.
- Raising a bare exception from `on_call_tool` reaches the client as a generic `Internal server error` with the message discarded. Raising `MCPError(code, message)` reaches the client with both intact.
- `Server[None]` requires an explicit lifespan yielding `None`; the SDK's default lifespan is typed as yielding `dict[str, Any]` and fails strict pyright against `Server[None]`.

---

### Task 1: ToolRegistry keeps the declarations it registers

Repairs the M1 omission the spec describes. No MCP yet, no new dependency.

**Files:**
- Modify: `src/vibepy/tool/registry.py`
- Modify: `src/vibepy/tool/model.py` (docstring of `ToolDefinition` only, if needed — no field changes)
- Test: `tests/test_tool_core.py` (append at the end)

**Interfaces:**
- Consumes: `ToolDefinition`, `Tool`, `bind`, `BoundTool`, `ToolNotFoundError` — all already present.
- Produces: `ToolRegistry.definitions() -> tuple[ToolDefinition[BaseModel, BaseModel], ...]`, returning declarations in registration order. Task 3 calls it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tool_core.py` (the Todo fixtures at the top of that file are reused; do not duplicate them):

```python
def test_registry_enumerates_the_declarations_it_registered() -> None:
    store = TodoStore()
    registry = ToolRegistry()
    registry.register(create_todo_tool(store))
    registry.register(list_todos_tool(store))

    definitions = registry.definitions()

    assert [definition.name for definition in definitions] == ["create_todo", "list_todos"]
    assert definitions[0].input_model is CreateTodoInput
    assert definitions[0].output_model is Todo


def test_registering_a_name_twice_replaces_its_declaration() -> None:
    store = TodoStore()
    registry = ToolRegistry()
    registry.register(create_todo_tool(store))
    registry.register(
        Tool(
            definition=ToolDefinition(
                name="create_todo",
                description="Replaced",
                input_model=CreateTodoInput,
                output_model=Todo,
            ),
            handler=create_todo_tool(store).handler,
        )
    )

    definitions = registry.definitions()

    assert len(definitions) == 1
    assert definitions[0].description == "Replaced"
```

`create_todo_tool` and `list_todos_tool` already exist in that file, as do `CreateTodoInput`, `Todo` and `TodoStore`. Reuse them; add no fixtures and rewrite no existing test.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_tool_core.py -k declaration -v`
Expected: FAIL with `AttributeError: 'ToolRegistry' object has no attribute 'definitions'`.

- [ ] **Step 3: Store the declarations**

Replace the body of `src/vibepy/tool/registry.py` with:

```python
"""Storage of bound Tools, and of the declarations registered with them."""

from pydantic import BaseModel

from vibepy.errors import ToolNotFoundError
from vibepy.tool.model import Tool, ToolDefinition
from vibepy.tool.runtime import BoundTool, bind


class ToolRegistry:
    """Maps a Tool name to the Tool registered under it. Storage only.

    The bound callable and the declaration are stored separately because
    ADR-008 erases the handler's type parameters into one uniform callable
    type, while a ToolDefinition holds no callable: its fields are read
    positions, so a frozen ToolDefinition is covariant in both parameters and
    a concrete declaration is storable as ``ToolDefinition[BaseModel,
    BaseModel]`` without ``Any`` or ``cast``.
    """

    def __init__(self) -> None:
        self._bound: dict[str, BoundTool] = {}
        self._declarations: dict[str, ToolDefinition[BaseModel, BaseModel]] = {}

    def register[InputT: BaseModel, OutputT: BaseModel](self, tool: Tool[InputT, OutputT]) -> None:
        name = tool.definition.name
        self._bound[name] = bind(tool)
        self._declarations[name] = tool.definition

    def resolve(self, name: str) -> BoundTool:
        bound = self._bound.get(name)
        if bound is None:
            raise ToolNotFoundError(name)
        return bound

    def definitions(self) -> tuple[ToolDefinition[BaseModel, BaseModel], ...]:
        """Every registered declaration, in registration order.

        A channel adapter projects these into its own discovery format, which
        is enumeration rather than lookup.
        """
        return tuple(self._declarations.values())
```

- [ ] **Step 4: Run the full check**

Run: `make lint typecheck test`
Expected: all green, every pre-existing test in `tests/test_tool_core.py` and `tests/test_page_core.py` still passing.

- [ ] **Step 5: Commit**

```bash
git add src/vibepy/tool/registry.py tests/test_tool_core.py
git commit -m "Keep Tool declarations in the registry"
```

---

### Task 2: Project a ToolDefinition into an MCP Tool

**Files:**
- Modify: `pyproject.toml` (add the dependency)
- Create: `src/vibepy/adapters/__init__.py`
- Create: `src/vibepy/adapters/mcp/__init__.py`
- Create: `src/vibepy/adapters/mcp/projection.py`
- Test: `tests/test_mcp_adapter.py`

**Interfaces:**
- Consumes: `ToolRegistry.definitions()` from Task 1 (not called here, but the projected type must accept its element type); `vibepy.tool.model.ToolDefinition`.
- Produces: `to_mcp_tool(definition: ToolDefinition[BaseModel, BaseModel]) -> mcp.types.Tool`, exported from `vibepy.adapters.mcp`. Task 3 calls it once per declaration.

- [ ] **Step 1: Add the dependency**

Run: `uv add "mcp>=2.1"`
Expected: `pyproject.toml` `[project].dependencies` gains `"mcp>=2.1"` and `uv.lock` updates. Do not add it to `[dependency-groups].dev`, and do not create an optional extra.

- [ ] **Step 2: Write the failing test**

Create `tests/test_mcp_adapter.py`:

```python
from pydantic import BaseModel

from vibepy.adapters.mcp import to_mcp_tool
from vibepy.tool import ToolDefinition


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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_mcp_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vibepy.adapters'`.

- [ ] **Step 4: Write the projection**

Create `src/vibepy/adapters/__init__.py`:

```python
"""Channel adapters. Each projects the framework's declarations into one channel."""
```

Create `src/vibepy/adapters/mcp/projection.py`:

```python
"""Projection of a Tool declaration into an MCP Tool definition.

``docs/architecture/adapters.md`` fixes the direction as
``Framework ToolDefinition -> MCP projection``, so schemas are derived from the
declaration's Pydantic models and never written by hand.
"""

from mcp import types
from pydantic import BaseModel

from vibepy.tool.model import ToolDefinition


def to_mcp_tool(definition: ToolDefinition[BaseModel, BaseModel]) -> types.Tool:
    """Project one declaration. Only fields with a source in ToolDefinition are set."""
    return types.Tool(
        name=definition.name,
        description=definition.description,
        input_schema=definition.input_model.model_json_schema(),
        output_schema=definition.output_model.model_json_schema(),
    )
```

Create `src/vibepy/adapters/mcp/__init__.py`:

```python
"""The Agent channel: framework Tools projected onto MCP."""

from vibepy.adapters.mcp.projection import to_mcp_tool

__all__ = ["to_mcp_tool"]
```

- [ ] **Step 5: Run the full check**

Run: `make lint typecheck test`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/vibepy/adapters tests/test_mcp_adapter.py
git commit -m "Project Tool declarations onto MCP Tools"
```

---

### Task 3: Build the MCP server and route calls through ToolRuntime

Covers acceptance criteria 1, 2 and 3 over the real protocol.

**Files:**
- Create: `src/vibepy/adapters/mcp/server.py`
- Modify: `src/vibepy/adapters/mcp/__init__.py`
- Test: `tests/test_mcp_adapter.py` (append)

**Interfaces:**
- Consumes: `to_mcp_tool` from Task 2; `ToolRegistry.definitions()` from Task 1; `ToolRuntime.invoke(name, raw_input) -> Awaitable[BaseModel]`.
- Produces: `build_mcp_server(*, name: str, version: str, registry: ToolRegistry, runtime: ToolRuntime) -> mcp.server.Server[None]`, exported from `vibepy.adapters.mcp`. Task 4 adds error mapping inside its `call_tool`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mcp_adapter.py`. At the top of the file add `import json`, add the
two SDK imports, replace the existing `vibepy.adapters.mcp` import line so it also brings in
`build_mcp_server`, and replace the `vibepy.tool` import line so it brings in everything the
fixtures need:

```python
import json

from mcp.client import Client
from mcp.server import Server

from vibepy.adapters.mcp import build_mcp_server, to_mcp_tool
from vibepy.tool import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolRuntime
```

```python
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
        registry.register(
            Tool(definition=create_todo_definition(), handler=self.create_todo)
        )
        registry.register(
            Tool(definition=list_todos_definition(), handler=self.list_todos)
        )
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
    assert json.loads(result.content[0].text) == expected


async def test_a_nested_result_survives_the_round_trip() -> None:
    fixture = TodoFixture()

    async with Client(build_server(fixture.registry())) as client:
        await client.call_tool("create_todo", {"title": "milk"})
        result = await client.call_tool("list_todos", {})

    assert result.structured_content == {
        "todos": [{"id": 1, "title": "milk", "done": False}]
    }
```

`result.content[0]` is typed as a union of content blocks, so reading `.text` off it directly
will not survive strict pyright. Narrow it first, with `from mcp.types import TextContent`
added to the imports:

```python
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert json.loads(block.text) == expected
```

Use that form in `test_a_result_is_the_validated_output_model` rather than the direct
attribute access shown above.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_mcp_adapter.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_mcp_server'`.

- [ ] **Step 3: Write the server**

Create `src/vibepy/adapters/mcp/server.py`:

```python
"""The MCP server an agent talks to, and the single call path behind it.

``docs/architecture/adapters.md`` gives this adapter four jobs: project
declarations, expose them for discovery, translate arguments into a
ToolRuntime invocation, and translate results back. It owns no business logic
and creates no invocation context: ``docs/architecture/runtime.md`` reserves
that for ToolRuntime.

Building a Server is not running one. In stdio the agent platform owns the
process, so the entrypoint belongs to package metadata rather than here.
"""

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from mcp import types
from mcp.server import Server, ServerRequestContext

from vibepy.adapters.mcp.projection import to_mcp_tool
from vibepy.tool.registry import ToolRegistry
from vibepy.tool.runtime import ToolRuntime

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _no_lifespan(server: Server[None]) -> AsyncGenerator[None]:
    """Create no app-scoped state; AppRuntime owns that.

    Declared only so the server's lifespan result type is ``None``. The SDK's
    default lifespan is typed as yielding ``dict[str, Any]``, which would put
    ``Any`` into this module's public return type.
    """
    yield None


def build_mcp_server(
    *, name: str, version: str, registry: ToolRegistry, runtime: ToolRuntime
) -> Server[None]:
    """Build the MCP projection of one App's Tools.

    The registry answers what Tools exist, which is enumeration; ToolRuntime
    runs them, which is the framework's only invocation path.
    """

    async def list_tools(
        ctx: ServerRequestContext[None], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[to_mcp_tool(definition) for definition in registry.definitions()]
        )

    async def call_tool(
        ctx: ServerRequestContext[None], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        result = await runtime.invoke(params.name, params.arguments or {})
        data = result.model_dump(by_alias=True, mode="json")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(data))],
            structured_content=data,
        )

    return Server(
        name,
        version=version,
        lifespan=_no_lifespan,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
```

Task 4 adds the error handling around `runtime.invoke`. Leave it absent here so its tests fail for the right reason.

Update `src/vibepy/adapters/mcp/__init__.py`:

```python
"""The Agent channel: framework Tools projected onto MCP."""

from vibepy.adapters.mcp.projection import to_mcp_tool
from vibepy.adapters.mcp.server import build_mcp_server

__all__ = ["build_mcp_server", "to_mcp_tool"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_mcp_adapter.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full check**

Run: `make lint typecheck test`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/vibepy/adapters/mcp tests/test_mcp_adapter.py
git commit -m "Serve framework Tools over MCP through ToolRuntime"
```

---

### Task 4: Map framework failures onto MCP

**Files:**
- Modify: `src/vibepy/adapters/mcp/server.py`
- Test: `tests/test_mcp_adapter.py` (append)

**Interfaces:**
- Consumes: `build_mcp_server` from Task 3; `ToolNotFoundError`, `ToolInputValidationError`, `ToolOutputValidationError` from `vibepy.errors`.
- Produces: no new name. `call_tool` gains the mapping in the spec's table.

- [ ] **Step 1: Write the failing tests**

Add to the imports at the top of `tests/test_mcp_adapter.py`:

```python
import pytest
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS
```

Append:

```python
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
```

Both failure fixtures use the techniques `tests/test_tool_core.py` already uses, so no new
one is invented: an empty mapping for a model with a required field, and `model_construct`
to skip validation on the way out. The MCP client forwards arguments that violate the
advertised input schema rather than rejecting them locally, so the empty mapping does reach
`call_tool` (verified against `mcp` 2.1.1). A failed result carries no structured content.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_mcp_adapter.py -v -k "unknown or invalid or raising"`
Expected: FAIL. The unknown-name test fails because a bare `ToolNotFoundError` surfaces as a generic internal error whose message does not contain the name; the others fail with the framework exception escaping instead of a result.

- [ ] **Step 3: Add the mapping**

In `src/vibepy/adapters/mcp/server.py`, add to the imports:

```python
from mcp.shared.exceptions import MCPError

from vibepy.errors import (
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
)
```

Add the module-level helper below `_no_lifespan`:

```python
def _failure(message: str) -> types.CallToolResult:
    """A failure the agent can read and act on, rather than a protocol error."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)], is_error=True
    )
```

Replace the body of `call_tool` with:

```python
    async def call_tool(
        ctx: ServerRequestContext[None], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        try:
            result = await runtime.invoke(params.name, params.arguments or {})
        except ToolNotFoundError as error:
            raise MCPError(types.INVALID_PARAMS, str(error)) from error
        except ToolInputValidationError as error:
            return _failure(str(error))
        except ToolOutputValidationError as error:
            logger.error("Tool %r returned output its own model rejected", params.name)
            return _failure(str(error))
        except Exception:
            logger.exception("Tool %r raised", params.name)
            return _failure(f"Tool {params.name!r} failed")
        data = result.model_dump(by_alias=True, mode="json")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(data))],
            structured_content=data,
        )
```

Why the shape is this: an unknown name is a protocol error because the caller addressed something that does not exist, and it must be raised as `MCPError` because a bare exception reaches the client as `Internal server error` with the message discarded. Invalid input is a result, not a protocol error, so the agent can read the message and correct itself. Output validation failure and an unexpected handler exception are app defects: the agent gets a failed result and the traceback goes to the log, not over the wire.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_mcp_adapter.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full check**

Run: `make lint typecheck test`
Expected: all green. If ruff flags the broad `except Exception`, do not narrow it — the branch exists to keep an app defect from becoming a protocol error. Add the specific `noqa` ruff names, with a comment saying why.

- [ ] **Step 6: Commit**

```bash
git add src/vibepy/adapters/mcp/server.py tests/test_mcp_adapter.py
git commit -m "Map framework Tool failures onto MCP"
```

---

### Task 5: Make the no-leak invariant a test

**Files:**
- Test: `tests/test_mcp_adapter.py` (append)

**Interfaces:**
- Consumes: nothing from the framework. It reads source files.
- Produces: no name. A standing guard for acceptance criterion 4.

- [ ] **Step 1: Write the failing test**

Add to the imports at the top of `tests/test_mcp_adapter.py`:

```python
import ast
from pathlib import Path
```

Append:

```python
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
```

- [ ] **Step 2: Run the test to verify it passes, and that it can fail**

Run: `uv run pytest tests/test_mcp_adapter.py -k core_tool_and_page -v`
Expected: PASS.

Then prove the test has teeth: temporarily add `import mcp` to the top of `src/vibepy/tool/model.py`, run the same command, and confirm it FAILS naming `model.py`. Remove the import afterwards and re-run to confirm PASS. A guard that cannot fail is not a guard.

- [ ] **Step 3: Run the full check**

Run: `make lint typecheck test`
Expected: all green, and `git status` clean apart from the test file.

- [ ] **Step 4: Commit**

```bash
git add tests/test_mcp_adapter.py
git commit -m "Assert the core packages stay free of MCP types"
```

---

### Task 6: Record the decisions and promote the contracts

The milestone folder is deleted on integration, so anything still true moves into the documents that own it.

**Files:**
- Create: `docs/decisions/ADR-009-mcp-adapter-uses-the-low-level-server.md`
- Create: `docs/decisions/ADR-010-agent-platform-owns-the-mcp-process.md`
- Create: `docs/decisions/ADR-011-tool-registry-stores-declarations.md`
- Modify: `docs/decisions/ADR-008-tools-are-bound-at-registration.md` (status line only)
- Modify: `docs/architecture/adapters.md` (MCP Adapter section)
- Modify: `docs/architecture/tool-model.md` (ToolRegistry section)

**Interfaces:**
- Consumes: the reasoning already written in `docs/milestones/M3/spec.md`.
- Produces: nothing in code.

- [ ] **Step 1: Write ADR-009**

Nygard format, matching the existing ADRs: `# ADR-009: ...`, `Status: Accepted`, `## Context`, `## Decision`, `## Consequences`. Cite the official SDK documentation URL for the low-level server. Content, from the spec's "SDK surface" section: the adapter is built on `mcp.server.Server` with handlers passed as constructor arguments; the high-level `MCPServer` with `@mcp.tool()` is rejected because it derives schemas and result conversion from a Python function signature, which would make the SDK the source of truth for what a Tool is, against `docs/architecture/adapters.md`; the accepted cost is that the adapter constructs `CallToolResult` and maps errors by hand.

- [ ] **Step 2: Write ADR-010**

Content, from the spec's "Transport ownership" section: in stdio the agent platform spawns the server process, so the two leftmost links of the Agent channel chain in `docs/architecture.md` are owned outside the framework; `docs/architecture/lifecycle.md`'s startup step 4 therefore describes adapters living inside the app process, not stdio MCP; what the framework supplies is a command the platform executes, which is package metadata, so the entrypoint belongs to the App Package layer; `build_mcp_server()` returns a `Server` and never runs it, and that object is what an entrypoint wraps in stdio or what a runtime starts in-process if MCP is ever served over HTTP.

- [ ] **Step 3: Write ADR-011 and mark ADR-008 superseded**

ADR-011 supersedes ADR-008. It restates and keeps ADR-008's decision — a typed Tool is bound into one uniform callable at registration — and corrects its reach: `ToolDefinition` holds no callable, so the contravariance argument does not apply to it; under PEP 695 inferred variance a frozen `ToolDefinition` is covariant in both parameters and a concrete declaration is storable as `ToolDefinition[BaseModel, BaseModel]` with no `Any` and no `cast`; the registry therefore stores declarations alongside bound callables and enumerates them through `definitions()`, which channel adapters need for discovery. Add a line to ADR-011's header: `Supersedes: ADR-008`.

In `docs/decisions/ADR-008-tools-are-bound-at-registration.md`, change only the status line to `Status: Superseded by ADR-011`. Do not edit its Context, Decision or Consequences: `AGENTS.md` forbids rewriting an accepted ADR.

- [ ] **Step 4: Promote the contracts into the architecture documents**

In `docs/architecture/adapters.md`, MCP Adapter section: state that the adapter builds an SDK server object and does not run it, that in stdio the agent platform owns the process, and that the executable entrypoint therefore belongs to package metadata rather than to the runtime lifecycle. Point at ADR-010. Keep it to a short paragraph; the reasoning lives in the ADR.

In `docs/architecture/tool-model.md`, ToolRegistry section: replace the storage description with the truth — the registry stores each Tool's bound callable and its declaration, `definitions()` enumerates the declarations in registration order for channel discovery, and registering a name twice replaces both. Do not restate ADR-011's reasoning here; one role per document.

Add nothing about MCP result shapes or the error table to `docs/architecture/`: the error mapping is adapter-internal and M7 will own error codes.

- [ ] **Step 5: Verify the documents agree with the code**

Run: `make lint typecheck test`
Expected: all green.

Then re-read `docs/architecture/tool-model.md`'s ToolRegistry section against `src/vibepy/tool/registry.py` and confirm every sentence is true of the code. This section is what M3 exists to reconcile.

- [ ] **Step 6: Commit**

```bash
git add docs/decisions docs/architecture
git commit -m "Record the M3 decisions and promote the contracts"
```

---

## Finishing

The milestone is done when `make lint typecheck test` passes, all four acceptance criteria in
`docs/roadmap.md` M3 have a test naming them, and Task 6's documents are committed. Then use
`superpowers:finishing-a-development-branch`: `docs/milestones/M3/` is deleted as part of
integration, and the branch merges into `main` with `--no-ff`. Do not push until the milestone
is merged and the owner asks.
