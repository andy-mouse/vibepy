# M1 Tool Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the six core Tool abstractions so that a raw dictionary flows through validation, an async handler, and output validation, with deterministic framework errors.

**Architecture:** `Tool[InputT, OutputT]` keeps the app author's types intact. `bind()` is a generic function that closes over a typed Tool and returns a plain callable, `BoundTool`, from raw input to a validated output model - the closure is what lets heterogeneous Tools share a single name-keyed map without `Any` or `cast`. `ToolRegistry` only stores those callables. `ToolRuntime` is the sole entry point: it resolves the name, creates a fresh `ToolContext` per invocation, and calls the `BoundTool`. No class beyond the six named in the roadmap is introduced.

**Tech Stack:** Python 3.12 (PEP 695 generics), Pydantic 2.9+, pytest with `asyncio_mode = "auto"`, ruff, pyright strict.

**Spec:** `docs/milestones/M1/spec.md`

**Prerequisite:** work on a branch, not `main`. `git switch -c m1-tool-core`.

## Global Constraints

- `pyproject.toml` is the only project config. No `setup.py`, no `requirements.txt`.
- `Any` and `cast` are not acceptable in the public API. Use `Protocol`, `TypedDict`, dataclass, or `TypeVar`.
- Optional and configuration parameters are keyword-only.
- Framework exceptions derive from a single base class. Exception types are the contract, not message strings.
- Tests verify public contracts, not internals.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- Python `>=3.12`, `pydantic>=2.9`. Line length 100. Ruff lint rules: `E`, `F`, `I`, `UP`, `B`, `ASYNC`, `RUF`. Pyright `typeCheckingMode = "strict"`.
- Implement only M1. Do not add query/command kind, permissions, exposure policy, MCP concerns, timeouts, or `AppRuntime`.
- A change is done when `make lint typecheck test` passes.

## File Structure

| File | Responsibility |
| --- | --- |
| Create `src/vibepy/errors.py` | `VibepyError` base plus the four framework error types |
| Create `src/vibepy/tool/__init__.py` | public surface of the Tool model |
| Create `src/vibepy/tool/model.py` | `ToolContext`, `ToolDefinition`, `ToolHandler`, `Tool` — declarations only, no behaviour |
| Create `src/vibepy/tool/binding.py` | `BoundTool` alias and `bind` — validation and handler call, framework-internal |
| Create `src/vibepy/tool/registry.py` | `ToolRegistry` — storage of bound Tools under their names |
| Create `src/vibepy/tool/runtime.py` | `ToolRuntime` — resolution, context creation, invocation |
| Modify `src/vibepy/__init__.py` | re-export the public API |
| Create `tests/test_tool_core.py` | Todo fixtures and the contract tests, grown task by task |
| Modify `tests/test_package.py` | assert the public API surface instead of an empty `__all__` |
| Modify `docs/architecture/tool-model.md` | reflect the implemented contract |

---

### Task 1: Tool model declarations

**Files:**
- Create: `src/vibepy/errors.py`
- Create: `src/vibepy/tool/__init__.py`
- Create: `src/vibepy/tool/model.py`
- Test: `tests/test_tool_core.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `VibepyError`, `ToolAlreadyRegisteredError(tool_name: str)`, `ToolInputValidationError(tool_name: str)`, `ToolNotFoundError(tool_name: str)`, `ToolOutputValidationError(tool_name: str)`, each exposing a `tool_name: str` attribute; `ToolContext(app_id: str, invocation_id: str)`; `ToolDefinition[InputT, OutputT](name: str, description: str, input_model: type[InputT], output_model: type[OutputT])`; `ToolHandler[InputT, OutputT]` protocol callable as `handler(ctx, payload)` with positional-only parameters; `Tool[InputT, OutputT](definition, handler)`. All four framework error types are created here so later tasks import them rather than editing this file.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tool_core.py`. The Todo fixtures at the top of this file are reused by every later task; do not move them.

```python
from dataclasses import FrozenInstanceError

import pytest
from pydantic import BaseModel

from vibepy.tool import Tool, ToolContext, ToolDefinition


class CreateTodoInput(BaseModel):
    title: str


class CompleteTodoInput(BaseModel):
    id: int


class EmptyInput(BaseModel):
    pass


class Todo(BaseModel):
    id: int
    title: str
    done: bool


class TodoList(BaseModel):
    todos: list[Todo]


class TodoNotFound(Exception):
    """Domain exception owned by the Todo fixture, not by the framework."""

    def __init__(self, todo_id: int) -> None:
        super().__init__(f"No todo with id {todo_id}")
        self.todo_id = todo_id


class TodoStore:
    def __init__(self) -> None:
        self._todos: dict[int, Todo] = {}
        self._next_id = 1

    def create(self, title: str) -> Todo:
        todo = Todo(id=self._next_id, title=title, done=False)
        self._todos[todo.id] = todo
        self._next_id += 1
        return todo

    def list(self) -> list[Todo]:
        return list(self._todos.values())

    def complete(self, todo_id: int) -> Todo:
        todo = self._todos.get(todo_id)
        if todo is None:
            raise TodoNotFound(todo_id)
        completed = todo.model_copy(update={"done": True})
        self._todos[todo_id] = completed
        return completed


def create_todo_tool(store: TodoStore) -> Tool[CreateTodoInput, Todo]:
    async def handler(_ctx: ToolContext, payload: CreateTodoInput) -> Todo:
        return store.create(payload.title)

    return Tool(
        definition=ToolDefinition(
            name="create_todo",
            description="Create a todo item",
            input_model=CreateTodoInput,
            output_model=Todo,
        ),
        handler=handler,
    )


def list_todos_tool(store: TodoStore) -> Tool[EmptyInput, TodoList]:
    async def handler(_ctx: ToolContext, _payload: EmptyInput) -> TodoList:
        return TodoList(todos=store.list())

    return Tool(
        definition=ToolDefinition(
            name="list_todos",
            description="List every todo item",
            input_model=EmptyInput,
            output_model=TodoList,
        ),
        handler=handler,
    )


def complete_todo_tool(store: TodoStore) -> Tool[CompleteTodoInput, Todo]:
    async def handler(_ctx: ToolContext, payload: CompleteTodoInput) -> Todo:
        return store.complete(payload.id)

    return Tool(
        definition=ToolDefinition(
            name="complete_todo",
            description="Mark a todo item as done",
            input_model=CompleteTodoInput,
            output_model=Todo,
        ),
        handler=handler,
    )


def test_tool_definition_declares_its_models() -> None:
    tool = create_todo_tool(TodoStore())

    assert tool.definition.name == "create_todo"
    assert tool.definition.description == "Create a todo item"
    assert tool.definition.input_model is CreateTodoInput
    assert tool.definition.output_model is Todo


def test_tool_context_is_immutable() -> None:
    ctx = ToolContext(app_id="todo", invocation_id="inv-1")

    with pytest.raises(FrozenInstanceError):
        ctx.app_id = "other"  # type: ignore[misc]


async def test_handler_protocol_accepts_a_plain_async_function() -> None:
    store = TodoStore()
    tool = create_todo_tool(store)
    ctx = ToolContext(app_id="todo", invocation_id="inv-1")

    todo = await tool.handler(ctx, CreateTodoInput(title="buy milk"))

    assert todo == Todo(id=1, title="buy milk", done=False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tool_core.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vibepy.tool'`

- [ ] **Step 3: Write the errors module**

Create `src/vibepy/errors.py`:

```python
"""Framework exceptions. Exception types are the contract, message strings are not."""


class VibepyError(Exception):
    """Base class for every exception raised by the framework."""


class ToolNotFoundError(VibepyError):
    """No Tool is registered under the requested name."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"No Tool is registered under the name {tool_name!r}")
        self.tool_name = tool_name


class ToolAlreadyRegisteredError(VibepyError):
    """A Tool name was registered twice."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"A Tool is already registered under the name {tool_name!r}")
        self.tool_name = tool_name


class ToolInputValidationError(VibepyError):
    """Raw input did not satisfy the Tool's input model."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Input for Tool {tool_name!r} failed validation")
        self.tool_name = tool_name


class ToolOutputValidationError(VibepyError):
    """A handler result did not satisfy the Tool's output model."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Output of Tool {tool_name!r} failed validation")
        self.tool_name = tool_name
```

- [ ] **Step 4: Write the Tool model**

Create `src/vibepy/tool/model.py`:

```python
"""Declarations of the Tool model. These types carry no invocation behaviour."""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolContext:
    """Invocation-scoped context. Created by ToolRuntime, never by a channel."""

    app_id: str
    invocation_id: str


@dataclass(frozen=True)
class ToolDefinition[InputT: BaseModel, OutputT: BaseModel]:
    """Static declaration of a Tool. Both models are required."""

    name: str
    description: str
    input_model: type[InputT]
    output_model: type[OutputT]


class ToolHandler[InputT: BaseModel, OutputT: BaseModel](Protocol):
    """The async operation behind a Tool.

    Parameters are positional-only so that an app author may name them freely.
    """

    def __call__(self, ctx: ToolContext, payload: InputT, /) -> Awaitable[OutputT]: ...


@dataclass(frozen=True)
class Tool[InputT: BaseModel, OutputT: BaseModel]:
    """A ToolDefinition paired with the handler that implements it."""

    definition: ToolDefinition[InputT, OutputT]
    handler: ToolHandler[InputT, OutputT]
```

Create `src/vibepy/tool/__init__.py`:

```python
"""The channel-neutral Tool model."""

from vibepy.tool.model import Tool, ToolContext, ToolDefinition, ToolHandler

__all__ = [
    "Tool",
    "ToolContext",
    "ToolDefinition",
    "ToolHandler",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tool_core.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 6: Run the full gate**

Run: `make lint typecheck test`
Expected: all three pass. `tests/test_package.py` still passes because `src/vibepy/__init__.py` is untouched in this task.

- [ ] **Step 7: Commit**

```bash
git add src/vibepy/errors.py src/vibepy/tool/__init__.py src/vibepy/tool/model.py tests/test_tool_core.py
git commit -m "Add the Tool model declarations"
```

---

### Task 2: Tool binding and the registry

**Files:**
- Create: `src/vibepy/tool/binding.py`
- Create: `src/vibepy/tool/registry.py`
- Modify: `src/vibepy/tool/__init__.py`
- Test: `tests/test_tool_core.py` (append)

**Interfaces:**
- Consumes: `Tool`, `ToolContext` from `vibepy.tool.model`; `ToolAlreadyRegisteredError`, `ToolInputValidationError`, `ToolNotFoundError`, `ToolOutputValidationError` from `vibepy.errors`.
- Produces: `type BoundTool = Callable[[ToolContext, Mapping[str, object]], Awaitable[BaseModel]]` and `bind(tool: Tool[InputT, OutputT]) -> BoundTool` in `vibepy.tool.binding`; `ToolRegistry()` with `register(tool: Tool[InputT, OutputT]) -> None` and `resolve(name: str) -> BoundTool`. `BoundTool` and `bind` are framework-internal and are not re-exported from `vibepy`; Task 3 calls `await resolve(name)(ctx, raw_input)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tool_core.py`, and add `ToolRegistry` to the existing `from vibepy.tool import ...` line plus a new `from vibepy.errors import ToolAlreadyRegisteredError, ToolNotFoundError` import:

```python
def build_registry(store: TodoStore) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(create_todo_tool(store))
    registry.register(list_todos_tool(store))
    registry.register(complete_todo_tool(store))
    return registry


def test_registering_a_name_twice_raises() -> None:
    store = TodoStore()
    registry = ToolRegistry()
    registry.register(create_todo_tool(store))

    with pytest.raises(ToolAlreadyRegisteredError) as raised:
        registry.register(create_todo_tool(store))

    assert raised.value.tool_name == "create_todo"


def test_resolving_an_unregistered_name_raises() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolNotFoundError) as raised:
        registry.resolve("create_todo")

    assert raised.value.tool_name == "create_todo"


async def test_a_registered_tool_can_be_resolved_and_called() -> None:
    bound = build_registry(TodoStore()).resolve("create_todo")
    ctx = ToolContext(app_id="todo", invocation_id="inv-1")

    result = await bound(ctx, {"title": "buy milk"})

    assert result == Todo(id=1, title="buy milk", done=False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tool_core.py -v`
Expected: FAIL — `ImportError: cannot import name 'ToolRegistry' from 'vibepy.tool'`

- [ ] **Step 3: Write the binding module**

Create `src/vibepy/tool/binding.py`:

```python
"""Binding of a typed Tool into a uniform callable.

A name-keyed map holds one static type, while every handler has its own input
type, and an input type cannot be widened. Binding is the one step that turns a
typed Tool into a uniform value, and it can only run where the model types are
still concrete. This is the execution layer, not storage: ToolRegistry stores
what ``bind`` produces and ToolRuntime is its only caller.
"""

from collections.abc import Awaitable, Callable, Mapping

from pydantic import BaseModel, ValidationError

from vibepy.errors import ToolInputValidationError, ToolOutputValidationError
from vibepy.tool.model import Tool, ToolContext

type BoundTool = Callable[[ToolContext, Mapping[str, object]], Awaitable[BaseModel]]


def bind[InputT: BaseModel, OutputT: BaseModel](tool: Tool[InputT, OutputT]) -> BoundTool:
    """Close over a typed Tool and return a callable addressable by name.

    A closure rather than a wrapper class: a method would have to prove again
    that the value it received is the handler's input type, which cannot be
    expressed. Input validation, the handler call and output validation happen
    together because input validation is what proves the raw mapping has the
    handler's input type.

    The output is revalidated from its dump rather than accepted as-is: Pydantic
    does not revalidate an instance of the same model, so a result built by
    ``model_construct`` or mutated after construction would pass unchecked.
    Output models must therefore round-trip through ``model_dump(by_alias=True)``.
    """
    definition = tool.definition
    handler = tool.handler

    async def bound(ctx: ToolContext, raw_input: Mapping[str, object]) -> BaseModel:
        try:
            payload = definition.input_model.model_validate(raw_input)
        except ValidationError as error:
            raise ToolInputValidationError(definition.name) from error

        result = await handler(ctx, payload)
        dumped = result.model_dump(by_alias=True, warnings=False)

        try:
            return definition.output_model.model_validate(dumped)
        except ValidationError as error:
            raise ToolOutputValidationError(definition.name) from error

    return bound
```

- [ ] **Step 4: Write the registry**

Create `src/vibepy/tool/registry.py`:

```python
"""Storage of bound Tools under their names."""

from pydantic import BaseModel

from vibepy.errors import ToolAlreadyRegisteredError, ToolNotFoundError
from vibepy.tool.binding import BoundTool, bind
from vibepy.tool.model import Tool


class ToolRegistry:
    """Maps a Tool name to its bound callable. Storage only."""

    def __init__(self) -> None:
        self._bound: dict[str, BoundTool] = {}

    def register[InputT: BaseModel, OutputT: BaseModel](
        self, tool: Tool[InputT, OutputT]
    ) -> None:
        name = tool.definition.name
        if name in self._bound:
            raise ToolAlreadyRegisteredError(name)
        self._bound[name] = bind(tool)

    def resolve(self, name: str) -> BoundTool:
        bound = self._bound.get(name)
        if bound is None:
            raise ToolNotFoundError(name)
        return bound
```

Modify `src/vibepy/tool/__init__.py` to add the registry:

```python
"""The channel-neutral Tool model."""

from vibepy.tool.model import Tool, ToolContext, ToolDefinition, ToolHandler
from vibepy.tool.registry import ToolRegistry

__all__ = [
    "Tool",
    "ToolContext",
    "ToolDefinition",
    "ToolHandler",
    "ToolRegistry",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tool_core.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 6: Run the full gate**

Run: `make lint typecheck test`
Expected: all three pass.

- [ ] **Step 7: Commit**

```bash
git add src/vibepy/tool/binding.py src/vibepy/tool/registry.py src/vibepy/tool/__init__.py tests/test_tool_core.py
git commit -m "Bind typed Tools into uniform callables and register them"
```

---

### Task 3: ToolRuntime

**Files:**
- Create: `src/vibepy/tool/runtime.py`
- Modify: `src/vibepy/tool/__init__.py`
- Test: `tests/test_tool_core.py` (append)

**Interfaces:**
- Consumes: `ToolRegistry.resolve`, the `BoundTool` it returns, and `ToolContext`.
- Produces: `ToolRuntime(*, app_id: str, registry: ToolRegistry)` with `async invoke(name: str, raw_input: Mapping[str, object]) -> BaseModel`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tool_core.py`. Add `ToolRuntime` to the `from vibepy.tool import ...` line and extend the errors import to `from vibepy.errors import ToolAlreadyRegisteredError, ToolInputValidationError, ToolNotFoundError, ToolOutputValidationError`.

```python
class ProbeOutput(BaseModel):
    app_id: str
    invocation_id: str


def probe_tool() -> Tool[EmptyInput, ProbeOutput]:
    async def handler(ctx: ToolContext, _payload: EmptyInput) -> ProbeOutput:
        return ProbeOutput(app_id=ctx.app_id, invocation_id=ctx.invocation_id)

    return Tool(
        definition=ToolDefinition(
            name="probe",
            description="Report the context of this invocation",
            input_model=EmptyInput,
            output_model=ProbeOutput,
        ),
        handler=handler,
    )


def broken_output_tool() -> Tool[EmptyInput, Todo]:
    async def handler(_ctx: ToolContext, _payload: EmptyInput) -> Todo:
        return Todo.model_construct(id="not-an-integer", title="broken", done=False)

    return Tool(
        definition=ToolDefinition(
            name="broken_output",
            description="Return a value that violates its own output model",
            input_model=EmptyInput,
            output_model=Todo,
        ),
        handler=handler,
    )


async def test_raw_input_round_trips_into_a_validated_output_model() -> None:
    runtime = ToolRuntime(app_id="todo", registry=build_registry(TodoStore()))

    result = await runtime.invoke("create_todo", {"title": "buy milk"})

    assert result == Todo(id=1, title="buy milk", done=False)


async def test_tools_share_the_state_they_were_built_over() -> None:
    runtime = ToolRuntime(app_id="todo", registry=build_registry(TodoStore()))
    await runtime.invoke("create_todo", {"title": "buy milk"})
    await runtime.invoke("create_todo", {"title": "walk the dog"})

    result = await runtime.invoke("list_todos", {})

    assert result == TodoList(
        todos=[
            Todo(id=1, title="buy milk", done=False),
            Todo(id=2, title="walk the dog", done=False),
        ]
    )


async def test_invoking_an_unknown_name_raises() -> None:
    runtime = ToolRuntime(app_id="todo", registry=ToolRegistry())

    with pytest.raises(ToolNotFoundError) as raised:
        await runtime.invoke("create_todo", {})

    assert raised.value.tool_name == "create_todo"


async def test_malformed_raw_input_raises_input_validation_error() -> None:
    runtime = ToolRuntime(app_id="todo", registry=build_registry(TodoStore()))

    with pytest.raises(ToolInputValidationError) as raised:
        await runtime.invoke("create_todo", {})

    assert raised.value.tool_name == "create_todo"


async def test_a_result_violating_the_output_model_raises_output_validation_error() -> None:
    registry = ToolRegistry()
    registry.register(broken_output_tool())
    runtime = ToolRuntime(app_id="todo", registry=registry)

    with pytest.raises(ToolOutputValidationError) as raised:
        await runtime.invoke("broken_output", {})

    assert raised.value.tool_name == "broken_output"


async def test_a_domain_exception_reaches_the_caller_unchanged() -> None:
    runtime = ToolRuntime(app_id="todo", registry=build_registry(TodoStore()))

    with pytest.raises(TodoNotFound) as raised:
        await runtime.invoke("complete_todo", {"id": 999})

    assert raised.value.todo_id == 999


async def test_the_handler_receives_the_runtime_app_id() -> None:
    registry = ToolRegistry()
    registry.register(probe_tool())
    runtime = ToolRuntime(app_id="todo-app", registry=registry)

    result = await runtime.invoke("probe", {})

    assert isinstance(result, ProbeOutput)
    assert result.app_id == "todo-app"


async def test_each_invocation_receives_its_own_invocation_id() -> None:
    registry = ToolRegistry()
    registry.register(probe_tool())
    runtime = ToolRuntime(app_id="todo-app", registry=registry)

    first = await runtime.invoke("probe", {})
    second = await runtime.invoke("probe", {})

    assert isinstance(first, ProbeOutput)
    assert isinstance(second, ProbeOutput)
    assert first.invocation_id != second.invocation_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tool_core.py -v`
Expected: FAIL — `ImportError: cannot import name 'ToolRuntime' from 'vibepy.tool'`

- [ ] **Step 3: Write the runtime**

Create `src/vibepy/tool/runtime.py`:

```python
"""The single invocation path shared by every channel."""

from collections.abc import Mapping
from uuid import uuid4

from pydantic import BaseModel

from vibepy.tool.model import ToolContext
from vibepy.tool.registry import ToolRegistry


class ToolRuntime:
    """Resolves a Tool by name, creates its ToolContext, and invokes it.

    Concurrent invocations are permitted. Nothing here serializes them.
    """

    def __init__(self, *, app_id: str, registry: ToolRegistry) -> None:
        self._app_id = app_id
        self._registry = registry

    async def invoke(self, name: str, raw_input: Mapping[str, object]) -> BaseModel:
        bound = self._registry.resolve(name)
        ctx = ToolContext(app_id=self._app_id, invocation_id=str(uuid4()))
        return await bound(ctx, raw_input)
```

Modify `src/vibepy/tool/__init__.py` to add the runtime:

```python
"""The channel-neutral Tool model."""

from vibepy.tool.model import Tool, ToolContext, ToolDefinition, ToolHandler
from vibepy.tool.registry import ToolRegistry
from vibepy.tool.runtime import ToolRuntime

__all__ = [
    "Tool",
    "ToolContext",
    "ToolDefinition",
    "ToolHandler",
    "ToolRegistry",
    "ToolRuntime",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tool_core.py -v`
Expected: PASS, 14 tests.

- [ ] **Step 5: Run the full gate**

Run: `make lint typecheck test`
Expected: all three pass.

- [ ] **Step 6: Commit**

```bash
git add src/vibepy/tool/runtime.py src/vibepy/tool/__init__.py tests/test_tool_core.py
git commit -m "Add the Tool runtime"
```

---

### Task 4: Public API surface

**Files:**
- Modify: `src/vibepy/__init__.py`
- Test: `tests/test_package.py`

**Interfaces:**
- Consumes: everything produced by Tasks 1 to 3.
- Produces: the ten public names importable directly from `vibepy`.

- [ ] **Step 1: Write the failing test**

Replace the whole of `tests/test_package.py`:

```python
import vibepy


def test_public_api_is_exported_from_the_package_root() -> None:
    assert vibepy.__all__ == [
        "Tool",
        "ToolAlreadyRegisteredError",
        "ToolContext",
        "ToolDefinition",
        "ToolHandler",
        "ToolInputValidationError",
        "ToolNotFoundError",
        "ToolOutputValidationError",
        "ToolRegistry",
        "ToolRuntime",
        "VibepyError",
    ]


def test_every_exported_name_is_reachable() -> None:
    for name in vibepy.__all__:
        assert hasattr(vibepy, name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_package.py -v`
Expected: FAIL — `assert [] == ['Tool', ...]`

- [ ] **Step 3: Write the package root**

Replace the whole of `src/vibepy/__init__.py`:

```python
"""Agent-native application framework."""

from vibepy.errors import (
    ToolAlreadyRegisteredError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    VibepyError,
)
from vibepy.tool import Tool, ToolContext, ToolDefinition, ToolHandler, ToolRegistry, ToolRuntime

__all__ = [
    "Tool",
    "ToolAlreadyRegisteredError",
    "ToolContext",
    "ToolDefinition",
    "ToolHandler",
    "ToolInputValidationError",
    "ToolNotFoundError",
    "ToolOutputValidationError",
    "ToolRegistry",
    "ToolRuntime",
    "VibepyError",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: PASS, 16 tests.

- [ ] **Step 5: Run the full gate**

Run: `make lint typecheck test`
Expected: all three pass.

- [ ] **Step 6: Commit**

```bash
git add src/vibepy/__init__.py tests/test_package.py
git commit -m "Export the Tool Core public API"
```

---

### Task 5: Align the architecture documents

**Files:**
- Modify: `docs/architecture/tool-model.md`

**Interfaces:**
- Consumes: the implemented contract.
- Produces: no code.

`docs/architecture/` is the current truth of public contracts, so three statements in
`tool-model.md` need to match what now exists. `docs/architecture/runtime.md` already
describes `ToolContext` as app id plus invocation id and needs no change. Do not restate
anything the spec or the git history already carries.

- [ ] **Step 1: Make the output model required**

In the `### ToolDefinition` section, replace the bullet list

```text
- name
- description
- input model
- optional output model
```

with

```text
- name
- description
- input model
- output model
```

- [ ] **Step 2: Record the handler signature actually shipped**

In the `### ToolHandler` section, replace the code block with

```python
async def handler(ctx: ToolContext, payload: InputModel) -> OutputModel:
    ...
```

and add one sentence below it: "Handler parameters are positional-only in the `ToolHandler`
Protocol, so an app author may name them freely."

- [ ] **Step 3: Record the invocation contract**

At the end of the `### ToolRuntime` section, after "Business logic does not belong in
ToolRuntime.", add:

```text
`ToolRuntime.invoke(name, raw_input)` returns the validated output model instance.
Serialization belongs to channel adapters.

Framework errors are `ToolNotFoundError`, `ToolInputValidationError` and
`ToolOutputValidationError`. Exceptions raised by a handler propagate unchanged.

A handler result is revalidated through the output model, so an output model must
round-trip through `model_dump(by_alias=True)` back into `model_validate`.
```

- [ ] **Step 4: Run the full gate**

Run: `make lint typecheck test`
Expected: all three pass, unchanged from Task 4.

- [ ] **Step 5: Commit**

```bash
git add docs/architecture/tool-model.md
git commit -m "Align the Tool model document with the implementation"
```

---

## After the plan

Implementation is complete when all five tasks are committed and `make lint typecheck test`
passes. Then use `superpowers:finishing-a-development-branch` to integrate. Per `AGENTS.md`,
integration promotes whatever remains true out of `docs/milestones/M1/` and deletes the
folder, and the push happens only once the milestone is merged.
