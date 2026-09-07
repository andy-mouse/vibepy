# M4 NiceGUI Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose framework Pages through NiceGUI so that a PageDefinition becomes a Web route whose handler reaches Tools through ToolRuntime.

**Architecture:** A new thin adapter package, `vibepy.adapters.nicegui`, projects every PageDefinition in a PageRegistry onto a NiceGUI route whose builder awaits `PageRuntime.render(name)`. The adapter validates route format and uniqueness before registering anything, and it never starts a server. Design: `docs/milestones/M4/spec.md`.

**Tech Stack:** Python 3.12+, NiceGUI 3.16, Pydantic 2, pytest with `asyncio_mode = "auto"`, `nicegui.testing.user_simulation`, ruff, pyright strict.

## Global Constraints

- `make lint typecheck test` must pass before a task is considered done.
- `pyproject.toml` is the only project config file.
- `Any` and `cast` are not acceptable in the public API.
- Optional and configuration parameters are keyword-only.
- Framework exceptions derive from `VibepyError`. Exception types are the contract, message strings are not.
- Filesystem paths are `pathlib.Path`, never strings.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- Tests verify public contracts, not internals.
- Implement only M4. Do not build ahead into M5A (AppRuntime), M6 (lifecycle) or M14 (per-Tool exposure).
- `docs/roadmap.md` is never edited.

## Verified facts about NiceGUI 3.16

These were confirmed against the installed package and the official documentation. Do not re-derive them.

- `ui.page` is a class whose `__call__(func)` registers the route. `ui.page("/todos", title="Todos")(builder)` is the programmatic form of the decorator.
- `ui.page.__call__` begins with `core.app.remove_route(self.path)`, so a second registration of the same path **silently replaces** the first. NiceGUI will never report a route collision; the framework must.
- A page builder may be `async def`, and awaiting inside it works.
- `nicegui.testing.user_simulation` is public API (`nicegui/testing/__init__.py` `__all__`). It is an async context manager yielding a `User`.
- Pages registered **inside** an open `user_simulation()` context are reachable: the context resets NiceGUI globals on entry, so registering afterwards is the correct order.
- `User.open(path)` raises `AssertionError` for an unregistered path ("Expected status code 200, got 404").
- `nicegui` ships `py.typed`.
- The `testing` extra pulls in `httpx` and does not pull in selenium. Selenium is only needed for the `Screen` fixture, which this milestone does not use.
- Registered paths are readable from `nicegui.app.routes` via each route's `path` attribute.
- On leaving `user_simulation()`, NiceGUI drops each registered page builder's module from `sys.modules` unless that module's name starts with `tests.` (`nicegui/testing/general.py`). The builder this adapter registers lives in `vibepy.adapters.nicegui.web`, so `vibepy` is dropped after every such test. This is harmless because every test module binds its `vibepy` names at collection time, before any test runs. Do not import `vibepy` lazily inside a test body: that would re-import the package and produce a second set of class objects.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/vibepy/adapters/nicegui/__init__.py` | re-export `register_pages` |
| `src/vibepy/adapters/nicegui/web.py` | route validation and projection onto NiceGUI |
| `src/vibepy/errors.py` (modify) | add `PageRouteInvalidError`, `PageRouteConflictError` |
| `pyproject.toml` (modify) | add the `nicegui` runtime dependency and the `testing` extra to the dev group |
| `tests/todo_fixture.py` | the Todo sample: models, Tools, Page, and a builder returning both registries |
| `tests/test_nicegui_adapter.py` | adapter contract: routes, context, validation, interaction |
| `tests/test_dual_channel.py` | the constitutional dual-channel test from `docs/architecture/runtime.md` |
| `docs/architecture/adapters.md` (modify) | describe what the NiceGUI adapter owns |
| `docs/decisions/ADR-012-nicegui-adapter-registers-routes.md` | the decision to register without running |

`tests/test_mcp_adapter.py` keeps its own private Todo fixture. It is M3's proof and is not in this milestone's scope; do not refactor it to import `tests/todo_fixture.py`.

---

### Task 1: Route projection

**Files:**
- Modify: `pyproject.toml`
- Create: `src/vibepy/adapters/nicegui/__init__.py`
- Create: `src/vibepy/adapters/nicegui/web.py`
- Create: `tests/test_nicegui_adapter.py`

**Interfaces:**
- Consumes: `PageRegistry.definitions() -> tuple[PageDefinition, ...]`, `PageRuntime.render(name: str) -> None` (async), `PageDefinition(name, route, title)`.
- Produces: `register_pages(*, registry: PageRegistry, runtime: PageRuntime) -> None`, imported as `from vibepy.adapters.nicegui import register_pages`.

- [ ] **Step 1: Add the dependencies**

In `pyproject.toml`, add to `[project].dependencies`:

```toml
    "nicegui>=3.16",
```

and to `[dependency-groups].dev`:

```toml
    "nicegui[testing]>=3.16",
```

- [ ] **Step 2: Sync and confirm the version**

```bash
uv sync
uv run python -c "import nicegui; print(nicegui.__version__)"
```

Expected: `3.16.0` or later.

- [ ] **Step 3: Write the failing test**

Create `tests/test_nicegui_adapter.py`:

Import only what this task uses. Later tasks say which imports to add.

```python
from nicegui import app, ui
from nicegui.testing import user_simulation

from vibepy.adapters.nicegui import register_pages
from vibepy.page import Page, PageContext, PageDefinition, PageRegistry, PageRuntime
from vibepy.tool import ToolRegistry, ToolRuntime

APP_ID = "test-app"


def build_runtime(registry: PageRegistry) -> PageRuntime:
    tool_registry = ToolRegistry()
    return PageRuntime(
        registry=registry,
        tool_runtime=ToolRuntime(app_id=APP_ID, registry=tool_registry),
    )


def registered_paths() -> list[str]:
    return [route.path for route in app.routes if hasattr(route, "path")]


async def test_a_page_definition_becomes_a_web_route() -> None:
    registry = PageRegistry()

    async def handler(ctx: PageContext) -> None:
        ui.label("Todos")

    registry.register(
        Page(
            definition=PageDefinition(name="todos", route="/todos", title="Todos"),
            handler=handler,
        )
    )

    async with user_simulation() as user:
        register_pages(registry=registry, runtime=build_runtime(registry))

        assert "/todos" in registered_paths()
        await user.open("/todos")
        await user.should_see("Todos")


async def test_the_handler_receives_a_page_context() -> None:
    registry = PageRegistry()
    seen: list[PageContext] = []

    async def handler(ctx: PageContext) -> None:
        seen.append(ctx)
        ui.label("Todos")

    registry.register(
        Page(
            definition=PageDefinition(name="todos", route="/todos", title="Todos"),
            handler=handler,
        )
    )

    async with user_simulation() as user:
        register_pages(registry=registry, runtime=build_runtime(registry))
        await user.open("/todos")

    assert len(seen) == 1
    assert callable(seen[0].tools.call)
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
uv run pytest tests/test_nicegui_adapter.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'vibepy.adapters.nicegui'`.

- [ ] **Step 5: Write the adapter**

Create `src/vibepy/adapters/nicegui/web.py`:

```python
"""The Web routes a human reaches, and the single render path behind them.

``docs/architecture/adapters.md`` gives this adapter four jobs: project
PageDefinitions into routes, construct PageContext, run PageHandlers in the
NiceGUI lifecycle, and connect Page interaction to ToolRuntime. Only the first
is work this module does itself: ``docs/architecture/page-model.md`` gives
PageContext creation to PageRuntime, and the ToolInvoker a Page receives is
already backed by ToolRuntime.

Registering routes is not running a server. Startup belongs to the runtime
lifecycle; see docs/decisions/ADR-012-nicegui-adapter-registers-routes.md.
"""

from collections.abc import Awaitable, Callable

from nicegui import ui

from vibepy.errors import PageRouteConflictError, PageRouteInvalidError
from vibepy.page.registry import PageRegistry
from vibepy.page.runtime import PageRuntime


def register_pages(*, registry: PageRegistry, runtime: PageRuntime) -> None:
    """Project every declared Page onto a NiceGUI route.

    Every declaration is validated before any route is registered, so a
    rejected registry leaves no half-registered application behind.
    """
    definitions = registry.definitions()
    claimed: dict[str, str] = {}
    for definition in definitions:
        if not definition.route.startswith("/"):
            raise PageRouteInvalidError(definition.name, definition.route)
        owner = claimed.get(definition.route)
        if owner is not None:
            raise PageRouteConflictError(definition.route, owner, definition.name)
        claimed[definition.route] = definition.name

    for definition in definitions:
        ui.page(definition.route, title=definition.title)(_builder(runtime, definition.name))


def _builder(runtime: PageRuntime, name: str) -> Callable[[], Awaitable[None]]:
    """The page builder NiceGUI calls per visitor.

    Addressed by name rather than by route, so a route change never reaches
    PageRuntime.
    """

    async def build() -> None:
        await runtime.render(name)

    return build
```

Create `src/vibepy/adapters/nicegui/__init__.py`:

```python
"""The Web channel: framework Pages projected onto NiceGUI routes."""

from vibepy.adapters.nicegui.web import register_pages

__all__ = ["register_pages"]
```

- [ ] **Step 6: Add the two exceptions**

Append to `src/vibepy/errors.py`:

```python
class PageRouteInvalidError(VibepyError):
    """A Page declared a route the Web channel cannot register."""

    def __init__(self, page_name: str, route: str) -> None:
        super().__init__(f"Page {page_name!r} declared the invalid route {route!r}")
        self.page_name = page_name
        self.route = route


class PageRouteConflictError(VibepyError):
    """Two Pages declared the same route."""

    def __init__(self, route: str, page_name: str, conflicting_page_name: str) -> None:
        super().__init__(
            f"Pages {page_name!r} and {conflicting_page_name!r} both declare the route {route!r}"
        )
        self.route = route
        self.page_name = page_name
        self.conflicting_page_name = conflicting_page_name
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
uv run pytest tests/test_nicegui_adapter.py -v
```

Expected: 2 passed.

- [ ] **Step 8: Add the leak check**

Append to `tests/test_nicegui_adapter.py`:

```python
def _imported_module_names(source: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_the_core_tool_and_page_packages_do_not_import_nicegui() -> None:
    package = Path(__file__).resolve().parent.parent / "src" / "vibepy"
    modules = sorted((package / "tool").glob("*.py")) + sorted((package / "page").glob("*.py"))
    assert modules != []

    offenders = [
        module.name
        for module in modules
        for name in _imported_module_names(module.read_text(encoding="utf-8"))
        if name == "nicegui" or name.startswith("nicegui.")
    ]

    assert offenders == []
```

Add `import ast` and `from pathlib import Path` to the imports at the top of the file.

- [ ] **Step 9: Run the full gate**

```bash
make lint typecheck test
```

Expected: all pass. Remove any import left unused by the test file as written.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock src/vibepy/adapters/nicegui src/vibepy/errors.py tests/test_nicegui_adapter.py
git commit -m "Project PageDefinitions onto NiceGUI routes"
```

---

### Task 2: Route validation

**Files:**
- Modify: `tests/test_nicegui_adapter.py`

**Interfaces:**
- Consumes: `register_pages`, `PageRouteInvalidError`, `PageRouteConflictError` from Task 1.
- Produces: nothing new. This task proves the validation Task 1 wrote is the contract.

The validation code already exists from Task 1 because `register_pages` cannot be written twice. This task's deliverable is the proof, including the atomicity claim that a rejected registry registers nothing.

- [ ] **Step 1: Write the failing tests**

Add to the imports:

```python
import pytest

from vibepy.errors import PageRouteConflictError, PageRouteInvalidError
```

Append to `tests/test_nicegui_adapter.py`:

```python
async def noop_handler(ctx: PageContext) -> None:
    ui.label("Todos")


def page(name: str, route: str) -> Page:
    return Page(
        definition=PageDefinition(name=name, route=route, title=name),
        handler=noop_handler,
    )


async def test_a_route_that_is_not_a_path_is_rejected() -> None:
    registry = PageRegistry()
    registry.register(page("todos", "todos"))

    async with user_simulation():
        with pytest.raises(PageRouteInvalidError) as error:
            register_pages(registry=registry, runtime=build_runtime(registry))

    assert error.value.page_name == "todos"
    assert error.value.route == "todos"


async def test_two_pages_may_not_claim_one_route() -> None:
    registry = PageRegistry()
    registry.register(page("todos", "/todos"))
    registry.register(page("archive", "/todos"))

    async with user_simulation():
        with pytest.raises(PageRouteConflictError) as error:
            register_pages(registry=registry, runtime=build_runtime(registry))

    assert error.value.route == "/todos"
    assert {error.value.page_name, error.value.conflicting_page_name} == {"todos", "archive"}


async def test_a_rejected_registry_registers_nothing() -> None:
    registry = PageRegistry()
    registry.register(page("todos", "/todos"))
    registry.register(page("archive", "archive"))

    async with user_simulation():
        with pytest.raises(PageRouteInvalidError):
            register_pages(registry=registry, runtime=build_runtime(registry))

        assert "/todos" not in registered_paths()
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_nicegui_adapter.py -v
```

Expected: all pass, because Task 1's `register_pages` validates every declaration before registering any. If `test_a_rejected_registry_registers_nothing` fails, the two loops in `register_pages` were collapsed into one; restore the separation.

- [ ] **Step 3: Run the full gate**

```bash
make lint typecheck test
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_nicegui_adapter.py
git commit -m "Prove the Web channel owns route validation"
```

---

### Task 3: Page interaction reaches Tools

**Files:**
- Create: `tests/todo_fixture.py`
- Modify: `tests/test_nicegui_adapter.py`

**Interfaces:**
- Consumes: `register_pages` from Task 1; `Tool`, `ToolDefinition`, `ToolContext`, `ToolRegistry`, `ToolRuntime` from `vibepy.tool`; `Page`, `PageContext`, `PageDefinition`, `PageRegistry`, `PageRuntime` from `vibepy.page`.
- Produces, for Task 4:
  - `tests/todo_fixture.py::TodoApp` — a frozen dataclass with fields `tool_registry: ToolRegistry`, `tool_runtime: ToolRuntime`, `page_registry: PageRegistry`, `page_runtime: PageRuntime`
  - `tests/todo_fixture.py::build_todo_app() -> TodoApp`
  - `tests/todo_fixture.py::APP_ID: str`
  - models `CreateTodoInput`, `EmptyInput`, `Todo`, `TodoList`

- [ ] **Step 1: Write the Todo fixture**

Create `tests/todo_fixture.py`:

```python
"""The Todo sample app from docs/roadmap.md, used as a test fixture.

It stays a fixture rather than a package: an importable sample app presumes the
App Package layer, which is M9.
"""

from dataclasses import dataclass

from nicegui import ui
from pydantic import BaseModel

from vibepy.page import Page, PageContext, PageDefinition, PageRegistry, PageRuntime
from vibepy.tool import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolRuntime

APP_ID = "todo-app"


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


class TodoStore:
    """The app's domain internals. Not a Tool, and no channel reaches it."""

    def __init__(self) -> None:
        self._todos: list[Todo] = []

    async def create(self, ctx: ToolContext, payload: CreateTodoInput) -> Todo:
        todo = Todo(id=len(self._todos) + 1, title=payload.title, done=False)
        self._todos.append(todo)
        return todo

    async def list_all(self, ctx: ToolContext, payload: EmptyInput) -> TodoList:
        return TodoList(todos=list(self._todos))


async def todos_page(ctx: PageContext) -> None:
    """The human workflow. It reaches the domain only through Tools."""
    listing = await ctx.tools.call("list_todos", {})

    @ui.refreshable
    def rendered(todos: TodoList) -> None:
        for todo in todos.todos:
            ui.label(f"todo: {todo.title}")

    title = ui.input("title")

    async def add() -> None:
        await ctx.tools.call("create_todo", {"title": title.value})
        refreshed = await ctx.tools.call("list_todos", {})
        assert isinstance(refreshed, TodoList)
        rendered.refresh(refreshed)

    ui.button("Add", on_click=add)
    assert isinstance(listing, TodoList)
    rendered(listing)


@dataclass(frozen=True)
class TodoApp:
    """One App's registries and runtimes. AppRuntime, which owns these, is M5A."""

    tool_registry: ToolRegistry
    tool_runtime: ToolRuntime
    page_registry: PageRegistry
    page_runtime: PageRuntime


def build_todo_app() -> TodoApp:
    store = TodoStore()
    tool_registry = ToolRegistry()
    tool_registry.register(
        Tool(
            definition=ToolDefinition(
                name="create_todo",
                description="Create a todo",
                input_model=CreateTodoInput,
                output_model=Todo,
            ),
            handler=store.create,
        )
    )
    tool_registry.register(
        Tool(
            definition=ToolDefinition(
                name="list_todos",
                description="List every todo",
                input_model=EmptyInput,
                output_model=TodoList,
            ),
            handler=store.list_all,
        )
    )

    tool_runtime = ToolRuntime(app_id=APP_ID, registry=tool_registry)

    page_registry = PageRegistry()
    page_registry.register(
        Page(
            definition=PageDefinition(name="todos", route="/todos", title="Todos"),
            handler=todos_page,
        )
    )

    return TodoApp(
        tool_registry=tool_registry,
        tool_runtime=tool_runtime,
        page_registry=page_registry,
        page_runtime=PageRuntime(registry=page_registry, tool_runtime=tool_runtime),
    )
```

- [ ] **Step 2: Write the failing interaction test**

Append to `tests/test_nicegui_adapter.py`:

```python
async def test_page_interaction_invokes_a_tool() -> None:
    app_under_test = build_todo_app()

    async with user_simulation() as user:
        register_pages(
            registry=app_under_test.page_registry,
            runtime=app_under_test.page_runtime,
        )
        await user.open("/todos")
        user.find("title").type("write the spec")
        user.find("Add").click()
        await user.should_see("todo: write the spec")
```

Add `from tests.todo_fixture import build_todo_app` to the imports.

- [ ] **Step 3: Make `tests` an importable package**

Create an empty `tests/__init__.py`. `from tests.todo_fixture import ...` needs it, and it also keeps every test handler's `__module__` under the `tests.` prefix, which matters for the NiceGUI teardown behaviour described in the verified-facts section.

```bash
touch tests/__init__.py
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run pytest tests/test_nicegui_adapter.py::test_page_interaction_invokes_a_tool -v
```

Expected: PASS. The adapter already exists, so this task's failing state was the missing fixture, not missing behaviour. If it fails with `ModuleNotFoundError: No module named 'tests'`, `tests/__init__.py` was not created.

- [ ] **Step 5: Run the whole adapter test module**

```bash
uv run pytest tests/test_nicegui_adapter.py -v
```

Expected: all pass. The assertion text `todo: write the spec` is deliberately distinct from the input's own value `write the spec`: matching on the bare title would pass against the input field alone and prove nothing.

- [ ] **Step 6: Run the full gate**

```bash
make lint typecheck test
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add tests/todo_fixture.py tests/__init__.py tests/test_nicegui_adapter.py
git commit -m "Prove a Page interaction reaches a Tool through ToolRuntime"
```

---

### Task 4: The dual-channel proof

**Files:**
- Create: `tests/test_dual_channel.py`

**Interfaces:**
- Consumes: `build_todo_app`, `APP_ID`, `Todo` from `tests/todo_fixture.py` (Task 3); `build_mcp_server` from `vibepy.adapters.mcp`; `register_pages` from `vibepy.adapters.nicegui`.
- Produces: nothing. This is the terminal proof of the milestone.

`docs/architecture/runtime.md` calls this "a constitutional integration test" that "should remain throughout the project", which is why it gets its own module rather than living inside an adapter's tests.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dual_channel.py`:

```python
"""The dual-channel contract from docs/architecture/runtime.md.

Both channels converge on one ToolRuntime, so neither keeps a backend of its
own. This test is constitutional: it stays for the life of the project.

It does not assert that every Tool belongs on every channel. Deciding that a
Tool is hidden from a channel is M14.
"""

import json

from mcp.client import Client
from mcp.types import TextContent
from nicegui.testing import user_simulation

from tests.todo_fixture import TodoApp, build_todo_app
from vibepy.adapters.mcp import build_mcp_server
from vibepy.adapters.nicegui import register_pages


def build_server(app_under_test: TodoApp):
    return build_mcp_server(
        name="todo-app",
        version="0.0.0",
        registry=app_under_test.tool_registry,
        runtime=app_under_test.tool_runtime,
    )


def titles(result: object) -> list[str]:
    assert isinstance(result, dict)
    todos = result["todos"]
    assert isinstance(todos, list)
    return [todo["title"] for todo in todos]


async def test_both_channels_share_one_backend_state() -> None:
    app_under_test = build_todo_app()

    async with user_simulation() as user:
        register_pages(
            registry=app_under_test.page_registry,
            runtime=app_under_test.page_runtime,
        )

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
```

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/test_dual_channel.py -v
```

Expected: PASS. Everything it exercises exists after Task 3. If the Web side does not see `from the agent`, the two channels were built over different registries; both must come from one `build_todo_app()` result.

- [ ] **Step 3: Run the full gate**

```bash
make lint typecheck test
```

Expected: all pass. `build_server`'s return type is `Server[None]`; add the annotation and the `from mcp.server import Server` import if pyright asks for it.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dual_channel.py
git commit -m "Prove the Web and Agent channels share one backend"
```

---

### Task 5: Documentation

**Files:**
- Modify: `docs/architecture/adapters.md`
- Create: `docs/decisions/ADR-012-nicegui-adapter-registers-routes.md`

**Interfaces:**
- Consumes: the behaviour built in Tasks 1 to 4.
- Produces: nothing executable.

`AGENTS.md` allows one role per document and forbids stating the same fact twice. The architecture document says what the adapter is; the ADR says why registration and startup are separate.

- [ ] **Step 1: Rewrite the NiceGUI section of `docs/architecture/adapters.md`**

Replace the `## NiceGUI Adapter` section's closing two paragraphs with the following, keeping the numbered responsibility list as it stands:

```markdown
`register_pages()` projects every PageDefinition in a PageRegistry onto a NiceGUI route
whose builder awaits `PageRuntime.render(name)`. A Page is addressed by name, so a route
change never reaches PageRuntime, and the adapter constructs no PageContext: PageRuntime
owns that.

Route format and route uniqueness are validated here, which is where
`docs/architecture/page-model.md` places them. Every declaration is checked before any
route is registered, so a rejected registry leaves no half-registered app behind.

Errors are not translated. A Tool error or a handler exception propagates into NiceGUI,
which renders it. The MCP adapter wraps failures in a result because the MCP protocol
demands an answer to every call; the Web channel makes no such demand.

The adapter registers routes and starts no server. See
`docs/decisions/ADR-012-nicegui-adapter-registers-routes.md`.

The app owns the actual Page UI implementation. The framework owns the
integration/runtime mechanism.

NiceGUI-specific types must not leak into the core Page model unless required at the app
UI implementation boundary.
```

- [ ] **Step 2: Write the ADR**

Create `docs/decisions/ADR-012-nicegui-adapter-registers-routes.md`:

```markdown
# ADR-012: The NiceGUI adapter registers routes and does not run the server

Status: Accepted

## Context

`docs/architecture/lifecycle.md`'s startup step 4 initializes and starts channel adapters,
and ADR-010 confirms that this step covers the NiceGUI Web server, which unlike a stdio
MCP server does live inside the app process. So the Web channel could legitimately own its
own startup.

It has nothing to start it from. AppRuntime is M5A and the lifecycle is M6, so an adapter
that ran a server today would define startup where no lifecycle exists to own it, and M6
would have to take it back.

NiceGUI also registers routes on a process-global app object. `ui.page.__call__` begins by
removing any route already at that path, so a second registration of one path silently
replaces the first and no collision is ever reported.

## Decision

Registering routes is separated from running a server. `register_pages()` projects a
PageRegistry onto NiceGUI routes and returns; the framework starts no Web server and holds
no server object.

Route format and uniqueness are validated by the adapter before any route is registered.
The framework does not rely on NiceGUI to report a route collision, because NiceGUI does
not report one.

## Consequences

- the Web channel is testable in-process through `nicegui.testing.user_simulation`, with no
  server and no browser
- what M6 adds is a call to `ui.run()` at startup step 4, not a rewrite of this adapter
- two Pages declaring one route fail loudly at registration rather than one silently
  disappearing
- registration is process-global, so one process serves one App's Pages. Isolating several
  installed Apps is M17 and this decision does not prejudge it
```

- [ ] **Step 3: Run the full gate**

```bash
make lint typecheck test
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture/adapters.md docs/decisions/ADR-012-nicegui-adapter-registers-routes.md
git commit -m "Record how the Web channel registers routes"
```

---

## Integration

After Task 5, follow `AGENTS.md`: promote what is still true out of `docs/milestones/M4/`, delete the folder, and merge the branch with `--no-ff`. Do not push unless asked.
