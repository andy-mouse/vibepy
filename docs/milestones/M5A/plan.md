# M5A AppRuntime and shared state - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the App an owner — `AppDefinition` declares one App, `AppRuntime` runs it, and both channels reach the same application-scoped resource through `ToolContext`.

**Architecture:** A type parameter `DepsT` carries the App's own resource type through the Tool layer. `AppDefinition` is a frozen dataclass holding a resource factory plus Tool and Page declarations; `AppRuntime` calls that factory once, fills both registries and builds both runtimes over them. Channel adapters are constructed from an `AppRuntime`, so the Web and Agent channels of one App provably share one resource. The Page layer is untouched.

**Tech Stack:** Python 3.12+, PEP 695 generics, Pydantic v2, pyright strict, ruff, pytest with `asyncio_mode = "auto"`, MCP Python SDK, NiceGUI.

**Design source:** `docs/milestones/M5A/spec.md`. Read it before Task 1.

## Global Constraints

- A change is done when `make lint typecheck test` passes. Run it at the end of every task.
- `Any` and `cast` are not acceptable in the public API. Use `Protocol`, `TypedDict`, dataclass, or `TypeVar`.
- pyright runs in `strict` mode over `src` and `tests`. An unparameterized generic in an annotation is an error, so every `ToolContext`, `Tool`, `ToolRegistry`, `ToolRuntime`, `AppDefinition` and `AppRuntime` annotation must carry its type argument.
- ruff `line-length = 100`, rules `E, F, I, UP, B, ASYNC, RUF`.
- Optional and configuration parameters are keyword-only.
- Framework exceptions derive from `VibepyError`. Exception types are the contract, not message strings.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- Tests verify public contracts, not internals.
- Do not build ahead: no lifecycle state machine (M6), no config model (M8), no manifest or entrypoint (M9).
- `docs/roadmap.md` is never edited.
- Commit after every task. Do not push.

---

### Task 1: The Tool layer carries app-scoped dependencies

Adds `DepsT` to `ToolContext`, `ToolHandler`, `Tool`, `ToolRegistry` and `ToolRuntime`, and moves handler binding from `ToolRegistry.register` into `Tool.__init__` so that a later `AppDefinition` can hold a uniformly typed sequence of Tools.

**Files:**
- Modify: `src/vibepy/tool/model.py`
- Modify: `src/vibepy/tool/runtime.py`
- Modify: `src/vibepy/tool/registry.py`
- Modify: `src/vibepy/tool/__init__.py`
- Test: `tests/test_tool_core.py`
- Modify (keep the tree green): `tests/test_page_core.py`, `tests/test_mcp_adapter.py`, `tests/test_nicegui_adapter.py`, `tests/todo_fixture.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `ToolContext[DepsT](app_id: str, invocation_id: str, dependencies: DepsT)` — frozen dataclass
  - `ToolHandler[DepsT, InputT: BaseModel, OutputT: BaseModel]` — Protocol, `__call__(ctx: ToolContext[DepsT], payload: InputT, /) -> Awaitable[OutputT]`
  - `Tool[DepsT]` with generic `__init__(*, definition: ToolDefinition[InputT, OutputT], handler: ToolHandler[DepsT, InputT, OutputT])`, attributes `definition: ToolDefinition[BaseModel, BaseModel]` and `bound: BoundTool[DepsT]`
  - `type BoundTool[DepsT] = Callable[[ToolContext[DepsT], Mapping[str, object]], Awaitable[BaseModel]]`
  - `ToolRegistry[DepsT]` with `register(tool: Tool[DepsT]) -> None`, `resolve(name: str) -> Tool[DepsT]`, `definitions() -> tuple[ToolDefinition[BaseModel, BaseModel], ...]`
  - `ToolRuntime[DepsT](*, app_id: str, registry: ToolRegistry[DepsT], dependencies: DepsT)` with `async invoke(name: str, raw_input: Mapping[str, object]) -> BaseModel`
  - `bind` is removed. `Tool` is re-exported from `vibepy.tool` but now lives in `vibepy.tool.runtime`.

- [ ] **Step 1: Write the failing test**

In `tests/test_tool_core.py`, add after the existing `build_registry` helper:

```python
async def test_the_handler_receives_the_runtime_dependencies() -> None:
    store = TodoStore()
    runtime = ToolRuntime(app_id="todo", registry=build_registry(), dependencies=store)

    await runtime.invoke("create_todo", {"title": "buy milk"})

    assert [todo.title for todo in store.list()] == ["buy milk"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_tool_core.py::test_the_handler_receives_the_runtime_dependencies -v`
Expected: FAIL — `ToolRuntime.__init__() got an unexpected keyword argument 'dependencies'`.

- [ ] **Step 3: Add the type parameter to the Tool declarations**

Replace `ToolContext` and `ToolHandler` in `src/vibepy/tool/model.py`, and delete the `Tool` dataclass from that module (it moves to `runtime.py` in Step 4). The module's remaining imports are `Awaitable`, `dataclass`, `Protocol`, `BaseModel`.

```python
@dataclass(frozen=True)
class ToolContext[DepsT]:
    """Invocation-scoped context. Created by ToolRuntime, never by a channel.

    ``dependencies`` is the App's own application-scoped resource. AppRuntime
    creates it once and every invocation on every channel receives that same
    value, which is narrower than AppRuntime and typed by the app itself.
    """

    app_id: str
    invocation_id: str
    dependencies: DepsT


class ToolHandler[DepsT, InputT: BaseModel, OutputT: BaseModel](Protocol):
    """The async operation behind a Tool.

    Parameters are positional-only so that an app author may name them freely.
    """

    def __call__(self, ctx: ToolContext[DepsT], payload: InputT, /) -> Awaitable[OutputT]: ...
```

`ToolDefinition` is unchanged. Update the module docstring's mention of `Tool` if it names the type.

- [ ] **Step 4: Move binding into `Tool` and parameterize `ToolRuntime`**

Replace the body of `src/vibepy/tool/runtime.py`:

```python
"""The single invocation path shared by every channel.

Input validation, the handler call and output validation belong together: input
validation is what proves a raw mapping has the handler's input type. They live
in the closure a Tool builds over its handler, so a Tool is addressable by one
uniform callable type regardless of the models it declares.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from vibepy.errors import ToolInputValidationError, ToolOutputValidationError
from vibepy.tool.model import ToolContext, ToolDefinition, ToolHandler

if TYPE_CHECKING:
    from vibepy.tool.registry import ToolRegistry

type BoundTool[DepsT] = Callable[
    [ToolContext[DepsT], Mapping[str, object]], Awaitable[BaseModel]
]


class Tool[DepsT]:
    """A ToolDefinition paired with the handler that implements it, already bound.

    The class is generic in ``DepsT`` only, while ``__init__`` is generic in the
    declared models. A Tool therefore has one static type per App, which is what
    lets an AppDefinition hold a sequence of them: ``InputT`` appears covariantly
    in the declaration and contravariantly in the handler, so a Tool generic in it
    would be invariant and no common element type would exist.

    Binding happens here rather than in a registry because a declaration is not
    useful before it is callable, and the erasure has exactly one cause.

    The output is revalidated from its dump rather than accepted as-is, so a
    result built by ``model_construct`` or mutated after construction cannot pass
    unchecked. Output models must round-trip through ``model_dump(by_alias=True)``.
    """

    def __init__[InputT: BaseModel, OutputT: BaseModel](
        self,
        *,
        definition: ToolDefinition[InputT, OutputT],
        handler: ToolHandler[DepsT, InputT, OutputT],
    ) -> None:
        async def bound(
            ctx: ToolContext[DepsT], raw_input: Mapping[str, object]
        ) -> BaseModel:
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

        self.definition: ToolDefinition[BaseModel, BaseModel] = definition
        self.bound: BoundTool[DepsT] = bound


class ToolRuntime[DepsT]:
    """Resolves a Tool by name, creates its ToolContext, and invokes it.

    ``dependencies`` is the application-scoped resource AppRuntime owns. The
    runtime holds it and puts it into every ToolContext it creates, so a channel
    never constructs a context and never sees AppRuntime.

    Concurrent invocations are permitted. Nothing here serializes them.
    """

    def __init__(
        self, *, app_id: str, registry: "ToolRegistry[DepsT]", dependencies: DepsT
    ) -> None:
        self._app_id = app_id
        self._registry = registry
        self._dependencies = dependencies

    async def invoke(self, name: str, raw_input: Mapping[str, object]) -> BaseModel:
        tool = self._registry.resolve(name)
        ctx = ToolContext(
            app_id=self._app_id,
            invocation_id=str(uuid4()),
            dependencies=self._dependencies,
        )
        return await tool.bound(ctx, raw_input)
```

- [ ] **Step 5: Reduce the registry to one dictionary**

Replace `src/vibepy/tool/registry.py`:

```python
"""Storage of Tools under their names."""

from pydantic import BaseModel

from vibepy.errors import ToolNotFoundError
from vibepy.tool.model import ToolDefinition
from vibepy.tool.runtime import Tool


class ToolRegistry[DepsT]:
    """Maps a Tool name to the Tool registered under it. Storage only.

    A Tool carries both its bound callable and its declaration, so one dictionary
    serves resolution and enumeration. The declaration is stored inside the Tool
    as ``ToolDefinition[BaseModel, BaseModel]``: its fields are read positions, so
    a frozen ToolDefinition is covariant in both parameters and a concrete
    declaration is assignable without ``Any`` or ``cast``.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool[DepsT]] = {}

    def register(self, tool: Tool[DepsT]) -> None:
        self._tools[tool.definition.name] = tool

    def resolve(self, name: str) -> Tool[DepsT]:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        return tool

    def definitions(self) -> tuple[ToolDefinition[BaseModel, BaseModel], ...]:
        """Every registered declaration, in registration order.

        A channel adapter projects these into its own discovery format, which is
        enumeration rather than lookup.
        """
        return tuple(tool.definition for tool in self._tools.values())
```

Then update `src/vibepy/tool/__init__.py` so `Tool` comes from `runtime`:

```python
"""The channel-neutral Tool model."""

from vibepy.tool.model import ToolContext, ToolDefinition, ToolHandler
from vibepy.tool.registry import ToolRegistry
from vibepy.tool.runtime import Tool, ToolRuntime

__all__ = [
    "Tool",
    "ToolContext",
    "ToolDefinition",
    "ToolHandler",
    "ToolRegistry",
    "ToolRuntime",
]
```

- [ ] **Step 6: Convert the Tool core tests to the dependency contract**

In `tests/test_tool_core.py`, the three Todo Tools stop closing over a store and read it from the context instead. Replace the `create_todo_tool` / `list_todos_tool` / `complete_todo_tool` helpers and the `build_registry` helper with:

```python
async def create_todo(ctx: ToolContext[TodoStore], payload: CreateTodoInput) -> Todo:
    return ctx.dependencies.create(payload.title)


async def list_todos(ctx: ToolContext[TodoStore], _payload: EmptyInput) -> TodoList:
    return TodoList(todos=ctx.dependencies.list())


async def complete_todo(ctx: ToolContext[TodoStore], payload: CompleteTodoInput) -> Todo:
    return ctx.dependencies.complete(payload.id)


def create_todo_tool() -> Tool[TodoStore]:
    return Tool(
        definition=ToolDefinition(
            name="create_todo",
            description="Create a todo item",
            input_model=CreateTodoInput,
            output_model=Todo,
        ),
        handler=create_todo,
    )


def list_todos_tool() -> Tool[TodoStore]:
    return Tool(
        definition=ToolDefinition(
            name="list_todos",
            description="List every todo item",
            input_model=EmptyInput,
            output_model=TodoList,
        ),
        handler=list_todos,
    )


def complete_todo_tool() -> Tool[TodoStore]:
    return Tool(
        definition=ToolDefinition(
            name="complete_todo",
            description="Mark a todo item done",
            input_model=CompleteTodoInput,
            output_model=Todo,
        ),
        handler=complete_todo,
    )


def build_registry() -> ToolRegistry[TodoStore]:
    registry: ToolRegistry[TodoStore] = ToolRegistry()
    registry.register(create_todo_tool())
    registry.register(list_todos_tool())
    registry.register(complete_todo_tool())
    return registry
```

Keep the existing descriptions verbatim if they differ from the strings above; only the handler wiring changes.

Then update the remaining call sites in the same file:

- `test_tool_definition_declares_its_models`: `tool = create_todo_tool()`.
- `test_tool_context_is_immutable`: `ctx = ToolContext(app_id="todo", invocation_id="inv-1", dependencies=None)`.
- `test_handler_protocol_accepts_a_plain_async_function`: build the context with `dependencies=store` and await the plain function directly, because a Tool no longer exposes its handler:

```python
async def test_handler_protocol_accepts_a_plain_async_function() -> None:
    store = TodoStore()
    ctx = ToolContext(app_id="todo", invocation_id="inv-1", dependencies=store)

    todo = await create_todo(ctx, CreateTodoInput(title="buy milk"))

    assert todo == Todo(id=1, title="buy milk", done=False)
```

- `test_resolving_an_unregistered_name_raises`: `registry: ToolRegistry[None] = ToolRegistry()`.
- `probe_tool()` and `broken_output_tool()`: return `Tool[None]`, and their handlers annotate `ToolContext[None]`.
- Every `ToolRuntime(...)` construction: add `dependencies=`. Use `dependencies=TodoStore()` where the test previously passed a store into `build_registry`, `dependencies=None` for the probe and broken-output registries. Bind the store to a local first where the test asserts against it.
- `test_tools_share_the_state_they_were_built_over`: rename to `test_tools_share_the_dependencies_they_were_invoked_with` and construct the runtime with one `TodoStore()` instance. The assertions are unchanged.
- `test_registry_enumerates_the_declarations_it_registered` and `test_registering_a_name_twice_replaces_its_declaration`: annotate the registries `ToolRegistry[TodoStore]` (or `[None]`, matching the Tools they register) and drop the store argument from the tool helpers.

- [ ] **Step 7: Keep the other test modules compiling**

These modules construct a `ToolRuntime` or annotate a `ToolContext` and would otherwise fail typecheck. Make the minimal change only; their behaviour is unchanged.

- `tests/test_page_core.py`: annotate the Tool handler `ToolContext[None]`, annotate `tool_registry: ToolRegistry[None] = ToolRegistry()`, and add `dependencies=None` to the `ToolRuntime(...)` call.
- `tests/test_mcp_adapter.py`: annotate every `ToolContext` in the fixture classes as `ToolContext[None]` (including the `self.contexts: list[ToolContext[None]]` field), annotate the registries `ToolRegistry[None]`, and add `dependencies=None` to the `ToolRuntime(...)` call. The fixtures keep their bound-method handlers; closures remain legal.
- `tests/test_nicegui_adapter.py`: in `build_runtime`, annotate `tool_registry: ToolRegistry[None] = ToolRegistry()` and add `dependencies=None` to the `ToolRuntime(...)` call.
- `tests/todo_fixture.py`: convert `TodoStore.create` / `TodoStore.list_all` into plain domain methods and lift the handlers out as module-level functions. Keep `build_todo_app` and the `TodoApp` dataclass for now; Task 3 replaces them.

```python
class TodoStore:
    """The app's domain internals. Not a Tool, and no channel reaches it."""

    def __init__(self) -> None:
        self._todos: list[Todo] = []

    def create(self, title: str) -> Todo:
        todo = Todo(id=len(self._todos) + 1, title=title, done=False)
        self._todos.append(todo)
        return todo

    def list_all(self) -> list[Todo]:
        return list(self._todos)


async def create_todo(ctx: ToolContext[TodoStore], payload: CreateTodoInput) -> Todo:
    return ctx.dependencies.create(payload.title)


async def list_todos(ctx: ToolContext[TodoStore], _payload: EmptyInput) -> TodoList:
    return TodoList(todos=ctx.dependencies.list_all())
```

In `build_todo_app`, register `Tool(definition=..., handler=create_todo)` and `Tool(definition=..., handler=list_todos)`, annotate `tool_registry: ToolRegistry[TodoStore] = ToolRegistry()`, and pass `dependencies=store` to `ToolRuntime`.

- [ ] **Step 8: Run the full suite**

Run: `make lint typecheck test`
Expected: PASS, including the new `test_the_handler_receives_the_runtime_dependencies`.

- [ ] **Step 9: Commit**

```bash
git add src/vibepy/tool tests/test_tool_core.py tests/test_page_core.py tests/test_mcp_adapter.py tests/test_nicegui_adapter.py tests/todo_fixture.py
git commit -m "Carry app-scoped dependencies through ToolContext"
```

---

### Task 2: AppDefinition and AppRuntime

Introduces the App layer. `AppDefinition` is the static declaration; `AppRuntime` is one executable instance of it and owns the application-scoped resource.

**Files:**
- Create: `src/vibepy/app/__init__.py`
- Create: `src/vibepy/app/model.py`
- Create: `src/vibepy/app/runtime.py`
- Modify: `src/vibepy/__init__.py`
- Test: `tests/test_app_runtime.py`
- Modify: `tests/test_package.py`

**Interfaces:**
- Consumes: `Tool[DepsT]`, `ToolContext[DepsT]`, `ToolRegistry[DepsT]`, `ToolRuntime[DepsT]` from Task 1; `Page`, `PageRegistry`, `PageRuntime` unchanged from M2.
- Produces:
  - `AppDefinition[DepsT](app_id: str, name: str, version: str, create_dependencies: Callable[[], DepsT], tools: Sequence[Tool[DepsT]], pages: Sequence[Page])` — frozen dataclass
  - `AppRuntime[DepsT](definition: AppDefinition[DepsT])` with read-only properties `definition`, `tool_registry`, `tool_runtime`, `page_registry`, `page_runtime`
  - Both re-exported from `vibepy` and from `vibepy.app`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_runtime.py`. The fixture is deliberately not the Todo app: these tests must not depend on NiceGUI.

```python
"""The App layer's contract: one definition, independently isolated runtimes."""

import pytest
from pydantic import BaseModel

from vibepy.app import AppDefinition, AppRuntime
from vibepy.page import Page, PageContext, PageDefinition
from vibepy.tool import Tool, ToolContext, ToolDefinition


class Counter:
    """The app's application-scoped resource."""

    def __init__(self) -> None:
        self.value = 0

    def increment(self) -> int:
        self.value += 1
        return self.value


class EmptyInput(BaseModel):
    pass


class Count(BaseModel):
    value: int


class Identity(BaseModel):
    app_id: str
    dependency_id: int


async def increment(ctx: ToolContext[Counter], _payload: EmptyInput) -> Count:
    return Count(value=ctx.dependencies.increment())


async def read(ctx: ToolContext[Counter], _payload: EmptyInput) -> Count:
    return Count(value=ctx.dependencies.value)


async def identify(ctx: ToolContext[Counter], _payload: EmptyInput) -> Identity:
    return Identity(app_id=ctx.app_id, dependency_id=id(ctx.dependencies))


INCREMENT = Tool(
    definition=ToolDefinition(
        name="increment",
        description="Add one to the counter",
        input_model=EmptyInput,
        output_model=Count,
    ),
    handler=increment,
)

READ = Tool(
    definition=ToolDefinition(
        name="read",
        description="Report the counter",
        input_model=EmptyInput,
        output_model=Count,
    ),
    handler=read,
)

IDENTIFY = Tool(
    definition=ToolDefinition(
        name="identify",
        description="Report the invocation's app id and dependency identity",
        input_model=EmptyInput,
        output_model=Identity,
    ),
    handler=identify,
)


async def counter_page(ctx: PageContext) -> None:
    await ctx.tools.call("increment", {})


def build_definition() -> AppDefinition[Counter]:
    return AppDefinition(
        app_id="counter-app",
        name="Counter",
        version="0.1.0",
        create_dependencies=Counter,
        tools=[INCREMENT, READ, IDENTIFY],
        pages=[
            Page(
                definition=PageDefinition(
                    name="counter", route="/counter", title="Counter"
                ),
                handler=counter_page,
            )
        ],
    )


async def test_calls_through_one_runtime_share_app_scoped_state() -> None:
    app = AppRuntime(build_definition())

    await app.tool_runtime.invoke("increment", {})
    await app.tool_runtime.invoke("increment", {})

    assert await app.tool_runtime.invoke("read", {}) == Count(value=2)


async def test_a_second_runtime_is_isolated_by_default() -> None:
    definition = build_definition()
    first = AppRuntime(definition)
    second = AppRuntime(definition)

    await first.tool_runtime.invoke("increment", {})

    assert await second.tool_runtime.invoke("read", {}) == Count(value=0)


async def test_every_invocation_receives_the_same_dependency_instance() -> None:
    app = AppRuntime(build_definition())

    first = await app.tool_runtime.invoke("identify", {})
    second = await app.tool_runtime.invoke("identify", {})

    assert isinstance(first, Identity)
    assert isinstance(second, Identity)
    assert first.dependency_id == second.dependency_id
    assert first.app_id == "counter-app"


async def test_a_declared_page_reaches_a_tool_through_the_runtime() -> None:
    app = AppRuntime(build_definition())

    await app.page_runtime.render("counter")

    assert await app.tool_runtime.invoke("read", {}) == Count(value=1)


def test_declared_tools_are_enumerable_for_channel_discovery() -> None:
    app = AppRuntime(build_definition())

    names = [definition.name for definition in app.tool_registry.definitions()]

    assert names == ["increment", "read", "identify"]


def test_declared_pages_are_enumerable_for_route_projection() -> None:
    app = AppRuntime(build_definition())

    routes = [definition.route for definition in app.page_registry.definitions()]

    assert routes == ["/counter"]


def test_the_definition_stays_reachable_from_the_runtime() -> None:
    definition = build_definition()

    app = AppRuntime(definition)

    assert app.definition is definition


async def test_an_unknown_tool_name_still_raises_through_the_app_runtime() -> None:
    app = AppRuntime(build_definition())

    with pytest.raises(ToolNotFoundError) as raised:
        await app.tool_runtime.invoke("nope", {})

    assert raised.value.tool_name == "nope"
```

The module's imports are `pytest`, `BaseModel` from `pydantic`, `AppDefinition` and
`AppRuntime` from `vibepy.app`, `ToolNotFoundError` from `vibepy.errors`, `Page`,
`PageContext` and `PageDefinition` from `vibepy.page`, and `Tool`, `ToolContext` and
`ToolDefinition` from `vibepy.tool`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_app_runtime.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'vibepy.app'`.

- [ ] **Step 3: Write the AppDefinition**

Create `src/vibepy/app/model.py`:

```python
"""Declaration of an App. Static: it holds no live resource and no runtime state."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from vibepy.page.model import Page
from vibepy.tool.runtime import Tool


@dataclass(frozen=True)
class AppDefinition[DepsT]:
    """Everything AppRuntime needs to compose one running App.

    ``create_dependencies`` is a factory rather than a resource. A definition that
    held a live resource could not be a declaration, and one definition would
    yield runtimes that shared state; a factory yields runtimes isolated from one
    another by default.

    ``DepsT`` is the app's own type for its application-scoped resource. An App
    that has none declares ``AppDefinition[None]`` with a factory returning
    ``None``; no default is provided, because the framework does not guess that an
    App is stateless.
    """

    app_id: str
    name: str
    version: str
    create_dependencies: Callable[[], DepsT]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
```

- [ ] **Step 4: Write the AppRuntime**

Create `src/vibepy/app/runtime.py`:

```python
"""The executable instance of an AppDefinition.

AppRuntime owns application-scoped state: the resource its definition declares,
the two registries filled from that definition, and the two runtimes over them.
Both channel adapters of one App are built from one AppRuntime, so both reach
that one resource.

The resource is created in the constructor. Runtime lifecycle is M6, and until a
start boundary exists there is nowhere else to create it. See
`docs/architecture/lifecycle.md`, which places dependency initialization at
startup.
"""

from vibepy.app.model import AppDefinition
from vibepy.page.registry import PageRegistry
from vibepy.page.runtime import PageRuntime
from vibepy.tool.registry import ToolRegistry
from vibepy.tool.runtime import ToolRuntime


class AppRuntime[DepsT]:
    """Composes one AppDefinition into a running App.

    Holds no lifecycle state. Constructing an AppRuntime starts no server and no
    adapter; a channel adapter is built from the AppRuntime, not by it.
    """

    def __init__(self, definition: AppDefinition[DepsT]) -> None:
        self._definition = definition
        self._dependencies = definition.create_dependencies()

        tool_registry: ToolRegistry[DepsT] = ToolRegistry()
        for tool in definition.tools:
            tool_registry.register(tool)
        self._tool_registry = tool_registry
        self._tool_runtime = ToolRuntime(
            app_id=definition.app_id,
            registry=tool_registry,
            dependencies=self._dependencies,
        )

        page_registry = PageRegistry()
        for page in definition.pages:
            page_registry.register(page)
        self._page_registry = page_registry
        self._page_runtime = PageRuntime(
            registry=page_registry, tool_runtime=self._tool_runtime
        )

    @property
    def definition(self) -> AppDefinition[DepsT]:
        return self._definition

    @property
    def tool_registry(self) -> ToolRegistry[DepsT]:
        return self._tool_registry

    @property
    def tool_runtime(self) -> ToolRuntime[DepsT]:
        return self._tool_runtime

    @property
    def page_registry(self) -> PageRegistry:
        return self._page_registry

    @property
    def page_runtime(self) -> PageRuntime:
        return self._page_runtime
```

The resource itself is not exposed. A Tool handler receives it through `ToolContext`; nothing else needs it, and `docs/architecture/app-model.md` keeps AppRuntime internals away from handlers.

- [ ] **Step 5: Export the App layer**

Create `src/vibepy/app/__init__.py`:

```python
"""The App: one unit of application definition and runtime composition."""

from vibepy.app.model import AppDefinition
from vibepy.app.runtime import AppRuntime

__all__ = ["AppDefinition", "AppRuntime"]
```

In `src/vibepy/__init__.py`, add `from vibepy.app import AppDefinition, AppRuntime` and insert `"AppDefinition"` and `"AppRuntime"` at the front of `__all__`, keeping it alphabetically sorted.

In `tests/test_package.py`, add `"AppDefinition"` and `"AppRuntime"` at the front of the expected list.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_app_runtime.py tests/test_package.py -v`
Expected: PASS.

- [ ] **Step 7: Run the full suite**

Run: `make lint typecheck test`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/vibepy/app src/vibepy/__init__.py tests/test_app_runtime.py tests/test_package.py
git commit -m "Compose an App from a definition into a runtime"
```

---

### Task 3: Channel adapters are built from an AppRuntime

Both adapters take one `AppRuntime` instead of a registry and a runtime, which makes "one App, one AppRuntime, two channels" a type-level guarantee.

**Files:**
- Modify: `src/vibepy/adapters/mcp/server.py`
- Modify: `src/vibepy/adapters/nicegui/web.py`
- Modify: `tests/todo_fixture.py`
- Modify: `tests/test_mcp_adapter.py`
- Modify: `tests/test_nicegui_adapter.py`
- Modify: `tests/test_dual_channel.py`

**Interfaces:**
- Consumes: `AppRuntime[DepsT]` and its properties from Task 2.
- Produces:
  - `build_mcp_server[DepsT](app: AppRuntime[DepsT]) -> Server[None]`
  - `register_pages[DepsT](app: AppRuntime[DepsT]) -> None`
  - `tests/todo_fixture.build_todo_app() -> AppRuntime[TodoStore]`; the `TodoApp` dataclass is removed.

- [ ] **Step 1: Write the failing test**

Rewrite `tests/todo_fixture.py`'s assembly so the fixture returns an `AppRuntime`. Replace the `TodoApp` dataclass and `build_todo_app` with:

```python
def build_todo_app() -> AppRuntime[TodoStore]:
    return AppRuntime(
        AppDefinition(
            app_id=APP_ID,
            name="Todo",
            version="0.0.0",
            create_dependencies=TodoStore,
            tools=[
                Tool(
                    definition=ToolDefinition(
                        name="create_todo",
                        description="Create a todo",
                        input_model=CreateTodoInput,
                        output_model=Todo,
                    ),
                    handler=create_todo,
                ),
                Tool(
                    definition=ToolDefinition(
                        name="list_todos",
                        description="List every todo",
                        input_model=EmptyInput,
                        output_model=TodoList,
                    ),
                    handler=list_todos,
                ),
            ],
            pages=[
                Page(
                    definition=PageDefinition(
                        name="todos", route="/todos", title="Todos"
                    ),
                    handler=todos_page,
                )
            ],
        )
    )
```

Update the module's imports to `from vibepy.app import AppDefinition, AppRuntime`, drop the `dataclass` import and the now-unused registry/runtime imports, and update the module docstring's closing note (it currently says AppRuntime "is M5A").

Then update `tests/test_dual_channel.py`. Its imports change from `TodoApp` to
`AppRuntime` and `TodoStore`, and the helper and the `register_pages` call become:

```python
def build_server(app_under_test: AppRuntime[TodoStore]) -> Server[None]:
    return build_mcp_server(app_under_test)
```

and replace the `register_pages(registry=..., runtime=...)` call with `register_pages(app_under_test)`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_dual_channel.py -v`
Expected: FAIL — `build_mcp_server() takes 0 positional arguments` / missing keyword arguments `name`, `version`, `registry`, `runtime`.

- [ ] **Step 3: Change the MCP adapter's signature**

In `src/vibepy/adapters/mcp/server.py`, replace the `build_mcp_server` signature and the `Server(...)` construction. Everything between is unchanged.

```python
def build_mcp_server[DepsT](app: AppRuntime[DepsT]) -> Server[None]:
    """Build the MCP projection of one App's Tools.

    Constructed from the AppRuntime rather than from a registry and a runtime, so
    the Agent channel provably addresses the same running App as the Web channel.
    The registry answers what Tools exist, which is enumeration; ToolRuntime runs
    them, which is the framework's only invocation path.
    """
    registry = app.tool_registry
    runtime = app.tool_runtime
    ...
    return Server(
        app.definition.app_id,
        version=app.definition.version,
        lifespan=_no_lifespan,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
```

`app_id` is the server name because it is the App's stable identifier. Add `from vibepy.app.runtime import AppRuntime` to the imports and drop the now-unused `ToolRegistry` / `ToolRuntime` imports.

- [ ] **Step 4: Change the NiceGUI adapter's signature**

In `src/vibepy/adapters/nicegui/web.py`:

```python
def register_pages[DepsT](app: AppRuntime[DepsT]) -> None:
    """Project every declared Page of one App onto a NiceGUI route.

    Every declaration is validated before any route is registered, so a rejected
    App leaves no half-registered application behind.
    """
    definitions = app.page_registry.definitions()
    ...
    for definition in definitions:
        ui.page(definition.route, title=definition.title)(
            _builder(app.page_runtime, definition.name)
        )
```

The validation loop and `_builder` are unchanged. Add `from vibepy.app.runtime import AppRuntime` and drop the now-unused `PageRegistry` import.

- [ ] **Step 5: Run the dual-channel test**

Run: `uv run pytest tests/test_dual_channel.py -v`
Expected: PASS. The test's assertions are unchanged; it is constitutional.

- [ ] **Step 6: Update the two adapter test modules**

`tests/test_mcp_adapter.py`: the fixture builds a registry and a runtime by hand. Give it an `AppRuntime[None]` instead — the fixture classes keep their bound-method handlers, so the App declares no dependencies:

```python
def build_server_for(tools: list[Tool[None]]) -> Server[None]:
    return build_mcp_server(
        AppRuntime(
            AppDefinition(
                app_id=APP_ID,
                name="Todo",
                version="0.0.0",
                create_dependencies=lambda: None,
                tools=tools,
                pages=[],
            )
        )
    )
```

Adjust the existing helpers to produce their Tool lists and pass them through this function. Keep every assertion as it is, including the one that asserts the discovered server name, if present — if a test asserts the MCP server's name, it must now expect `APP_ID`.

`tests/test_nicegui_adapter.py`: replace `build_runtime(registry: PageRegistry) -> PageRuntime` with a helper that returns an `AppRuntime[None]` built from a page list, and change every `register_pages(registry=..., runtime=...)` call to `register_pages(build_web_app([...]))`:

```python
def build_web_app(pages: list[Page]) -> AppRuntime[None]:
    return AppRuntime(
        AppDefinition(
            app_id=APP_ID,
            name="Test",
            version="0.0.0",
            create_dependencies=lambda: None,
            tools=[],
            pages=pages,
        )
    )
```

The route-validation tests (`test_a_route_that_is_not_a_path_is_rejected`, `test_two_pages_may_not_claim_one_route`, `test_a_rejected_registry_registers_nothing`) keep their `pytest.raises` assertions; only construction changes. `test_page_interaction_invokes_a_tool` becomes `register_pages(build_todo_app())`.

- [ ] **Step 7: Extend the import guards to the App package**

`vibepy.app` is core, so it must stay free of channel SDK types. In both `tests/test_mcp_adapter.py::test_the_core_tool_and_page_packages_do_not_import_mcp` and `tests/test_nicegui_adapter.py::test_the_core_tool_and_page_packages_do_not_import_nicegui`, rename the test to `test_the_core_packages_do_not_import_mcp` / `..._nicegui` and add the App package to the module list:

```python
    modules = (
        sorted((package / "tool").glob("*.py"))
        + sorted((package / "page").glob("*.py"))
        + sorted((package / "app").glob("*.py"))
    )
```

- [ ] **Step 8: Run the full suite**

Run: `make lint typecheck test`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/vibepy/adapters tests/todo_fixture.py tests/test_mcp_adapter.py tests/test_nicegui_adapter.py tests/test_dual_channel.py
git commit -m "Build both channel adapters from one AppRuntime"
```

---

### Task 4: Architecture documents and ADRs

The milestone folder is deleted on integration, so what stays true moves into the permanent documents now.

**Files:**
- Modify: `docs/architecture/app-model.md`
- Modify: `docs/architecture/tool-model.md`
- Modify: `docs/architecture/runtime.md`
- Modify: `docs/architecture/adapters.md`
- Modify: `docs/decisions/ADR-011-tool-registry-stores-declarations.md`
- Create: `docs/decisions/ADR-013-dependencies-reach-handlers-through-tool-context.md`
- Create: `docs/decisions/ADR-014-a-tool-carries-its-bound-callable.md`
- Create: `docs/decisions/ADR-015-adapters-are-built-from-an-app-runtime.md`

**Interfaces:**
- Consumes: the implemented public API from Tasks 1-3. Every signature quoted in a document must match the code exactly.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Record the three decisions**

Nygard format, matching the existing ADRs: `# ADR-NNN: <title>`, `Status: Accepted`, then `## Context`, `## Decision`, `## Consequences`. Cite official documentation with links where an external behaviour is claimed, as ADR-007 and ADR-009 do.

`ADR-013` — application-scoped dependencies reach handlers through ToolContext. Context: M5A must give the App an owner, and a handler needs the App's resource. Two mechanisms exist: closures bound at assembly, and a typed value on ToolContext. Decision: ToolContext, with the app's own type as a parameter. Reasons, in the order the spec gives them: `docs/architecture/runtime.md` already reserves the position; an AppDefinition that held handlers bound to a live resource would contain live connections, which `docs/architecture/app-model.md` forbids; and `docs/architecture/authoring.md` requires an App to be readable without running it, which a factory function is not. Consequences: `DepsT` threads through the Tool layer and the App layer; the Page layer is untouched because a Page reaches Tools by name; a handler still receives no access to AppRuntime; an App with no resource declares `None`.

`ADR-014` — a Tool carries its own bound callable. Status `Accepted`, with `Supersedes: ADR-011`. Context: ADR-011 put the declaration and the bound callable in two dictionaries inside ToolRegistry. AppDefinition must hold a sequence of Tools, and `Tool[DepsT, InputT, OutputT]` is invariant in `InputT` — it appears covariantly in the declaration and contravariantly in the handler — so no common element type exists. Decision: binding moves into `Tool.__init__`, which is generic in the declared models while the class is generic only in `DepsT`; the registry holds one dictionary. Consequences: one uniform element type for AppDefinition; the free function `bind` disappears; `Tool` moves to `tool/runtime.py` because it now carries invocation behaviour; the call site `Tool(definition=..., handler=...)` is unchanged; registering a name twice still replaces.

Then set ADR-011's status line to `Status: Superseded by ADR-014`, matching how ADR-008 records its own supersession. Do not rewrite ADR-011's body.

`ADR-015` — channel adapters are built from an AppRuntime. Context: `docs/architecture/app-model.md` requires that the Web and Agent adapters of one running App receive the same AppRuntime; the previous signatures took a registry and a runtime as separate parameters, which the type system cannot check for belonging together, and which would each have had to become generic in `DepsT` anyway. Decision: `build_mcp_server(app)` and `register_pages(app)`. Consequences: the pairing is a type-level guarantee; the MCP server's name and version come from AppDefinition, with `app_id` as the name; ADR-010 and ADR-012 are unaffected — building is still not running.

- [ ] **Step 2: Update `docs/architecture/app-model.md`**

Replace the speculative language in the `AppDefinition` and `AppRuntime` sections with what exists. `AppDefinition` now lists `app_id`, `name`, `version`, `create_dependencies`, `tools`, `pages`, and states that it is frozen and reusable. `AppRuntime` documents the constructor, the five properties, that the resource is created once in the constructor with M6 as the seam that may move it, and that the resource is not exposed. Remove "Do not introduce AppInstallation until packaging/Hub work requires it" only if it is now false — it is not; leave it. The three state scopes and the invariants stay; add that `DepsT` is the app's own type and that an App with no resource declares `None`.

- [ ] **Step 3: Update `docs/architecture/tool-model.md`**

In the `ToolRegistry` section, replace "it stores two things" with one dictionary of Tools, each carrying its declaration and its bound callable. In `ToolRuntime`, add `dependencies` to the constructor description and note that the ToolContext it creates carries it. Add a `ToolContext` note under `ToolHandler`'s conceptual contract showing the parameterized form:

```python
async def handler(ctx: ToolContext[Deps], payload: InputModel) -> OutputModel:
    ...
```

Point the binding paragraph at ADR-014 instead of ADR-011.

- [ ] **Step 4: Update `docs/architecture/runtime.md`**

In `## ToolContext`, replace "typed app services/config when required" with the concrete field: `dependencies`, the application-scoped resource, typed by the app. Keep "Do not make ToolContext an untyped service-locator bag" and add that the value is the app's own type, not a mapping. In `## Dependency ownership`, state that AppRuntime creates the resource from `AppDefinition.create_dependencies` and hands it to ToolRuntime, and that two AppRuntimes from one definition are isolated. In `## Dual-channel contract`, note that the test now builds both channels from one AppRuntime.

- [ ] **Step 5: Update `docs/architecture/adapters.md`**

In both adapter sections, replace the construction description with the AppRuntime-based signature and reference ADR-015. Keep every statement about not running a server: it is still true.

- [ ] **Step 6: Verify the documents against the code**

Run: `uv run pytest -q` and re-read each quoted signature against `src/vibepy/`. Every name, parameter and return type in the documents must match. Fix any drift.

- [ ] **Step 7: Commit**

```bash
git add docs/architecture docs/decisions
git commit -m "Record the App layer and its three decisions"
```

---

### Task 5: Retire the milestone folder

**Files:**
- Delete: `docs/milestones/M5A/spec.md`
- Delete: `docs/milestones/M5A/plan.md`

**Interfaces:**
- Consumes: Task 4's promotion of everything still true into the permanent documents.
- Produces: nothing.

- [ ] **Step 1: Confirm nothing is lost**

Re-read `docs/milestones/M5A/spec.md` section by section. Every statement that is still true must already appear in `docs/architecture/` or in an ADR. Non-goals that named a future milestone are recorded by that milestone's own entry in `docs/roadmap.md` and need no home. If anything else remains, add it to the owning document and amend Task 4's commit.

- [ ] **Step 2: Delete the folder**

```bash
git rm -r docs/milestones/M5A
```

- [ ] **Step 3: Run the full suite one last time**

Run: `make lint typecheck test`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git commit -m "Retire the M5A milestone folder"
```

---

## Acceptance

`docs/roadmap.md`'s M5A criteria are the tests:

- *Web-like and Agent-like calls share the same AppRuntime state* — `tests/test_dual_channel.py::test_both_channels_share_one_backend_state`, now built from one `AppRuntime`, plus `tests/test_app_runtime.py::test_calls_through_one_runtime_share_app_scoped_state`.
- *A second AppRuntime is isolated by default* — `tests/test_app_runtime.py::test_a_second_runtime_is_isolated_by_default`.

The milestone is done when `make lint typecheck test` passes on the final commit.
