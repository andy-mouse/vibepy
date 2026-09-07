# M2 Page Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Page, addressed by name, runs its handler and invokes an existing Tool through the narrow ToolInvoker interface.

**Architecture:** `src/vibepy/page/` mirrors `src/vibepy/tool/`: declarations in `model.py`, name-keyed storage in `registry.py`, the execution path in `runtime.py`. A Page is not generic over any model, so there is no binding closure as in ADR-008 — the registry stores Page directly. `ToolInvoker` is a Protocol in `model.py`, and its only implementation, backed by `ToolRuntime`, lives in `runtime.py`, so the core Page model depends on the shape of Tool invocation rather than on the Tool runtime.

**Tech Stack:** Python 3.12+, Pydantic v2, pytest with `pytest-asyncio` in `asyncio_mode = "auto"`, ruff, pyright strict, uv.

## Global Constraints

- Spec: `docs/milestones/M2/spec.md`. Implement it exactly; build nothing beyond it.
- Neither `Any` nor `cast` appears anywhere in `src/` or `tests/`.
- Optional and configuration parameters are keyword-only.
- Framework exceptions derive from `VibepyError`. Exception types are the contract, message strings are not.
- Tests verify public contracts, not internals.
- `make lint typecheck test` passes at the end of every task.
- Line length 100 (`ruff`).
- A pre-commit hook runs ruff and pyright on commit; a failing hook means the commit did not happen.
- Do not edit `docs/roadmap.md`. Do not touch `docs/architecture/` in this plan — integration promotes the contracts afterwards.
- No new dependency is added.

---

### Task 1: Page model declarations and PageNotFoundError

**Files:**
- Create: `src/vibepy/page/__init__.py`
- Create: `src/vibepy/page/model.py`
- Modify: `src/vibepy/errors.py` (append after `ToolOutputValidationError`)
- Test: `tests/test_page_core.py`

**Interfaces:**
- Consumes: `vibepy.errors.VibepyError`; `pydantic.BaseModel` for the ToolInvoker return type.
- Produces:
  - `PageDefinition(name: str, route: str, title: str)`, frozen dataclass, positional construction allowed.
  - `PageContext(tools: ToolInvoker)`, frozen dataclass.
  - `ToolInvoker` Protocol: `def call(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]`.
  - `PageHandler` Protocol: `def __call__(self, ctx: PageContext, /) -> Awaitable[None]`.
  - `Page(definition: PageDefinition, handler: PageHandler)`, frozen dataclass.
  - `PageNotFoundError(page_name: str)` with attribute `page_name`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_page_core.py`:

```python
from collections.abc import Awaitable, Mapping
from dataclasses import FrozenInstanceError, fields

import pytest
from pydantic import BaseModel

from vibepy.errors import PageNotFoundError, VibepyError
from vibepy.page import Page, PageContext, PageDefinition


class RecordingInvoker:
    """A ToolInvoker that records calls instead of reaching a ToolRuntime."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object]]] = []

    def call(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]:
        self.calls.append((name, raw_input))
        raise AssertionError("this fixture records calls and never returns a result")


def todos_definition() -> PageDefinition:
    return PageDefinition(name="todos", route="/todos", title="Todos")


def test_page_definition_declares_its_metadata() -> None:
    definition = todos_definition()

    assert definition.name == "todos"
    assert definition.route == "/todos"
    assert definition.title == "Todos"


def test_page_context_is_immutable() -> None:
    ctx = PageContext(tools=RecordingInvoker())

    with pytest.raises(FrozenInstanceError):
        ctx.tools = RecordingInvoker()  # type: ignore[misc]


def test_page_context_exposes_nothing_but_its_tool_invoker() -> None:
    assert [field.name for field in fields(PageContext)] == ["tools"]


async def test_handler_protocol_accepts_a_plain_async_function() -> None:
    seen: list[PageContext] = []

    async def handler(ctx: PageContext) -> None:
        seen.append(ctx)

    page = Page(definition=todos_definition(), handler=handler)
    ctx = PageContext(tools=RecordingInvoker())

    await page.handler(ctx)

    assert seen == [ctx]


def test_page_not_found_error_carries_the_page_name() -> None:
    error = PageNotFoundError("todos")

    assert error.page_name == "todos"
    assert isinstance(error, VibepyError)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_page_core.py -v`
Expected: FAIL at collection with `ImportError: cannot import name 'PageNotFoundError' from 'vibepy.errors'`.

- [ ] **Step 3: Append the error**

Append to `src/vibepy/errors.py`:

```python
class PageNotFoundError(VibepyError):
    """No Page is registered under the requested name."""

    def __init__(self, page_name: str) -> None:
        super().__init__(f"No Page is registered under the name {page_name!r}")
        self.page_name = page_name
```

- [ ] **Step 4: Write the declarations**

Create `src/vibepy/page/model.py`:

```python
"""Declarations of the Page model. These types carry no invocation behaviour."""

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


class ToolInvoker(Protocol):
    """The narrow interface a Page invokes Tools through.

    The signature is ``ToolRuntime.invoke``'s: a raw mapping in, a validated output
    model out. Validation stays inside ToolRuntime, so no second validation path
    exists, and a Page never sees the runtime itself.
    """

    def call(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]: ...


@dataclass(frozen=True)
class PageContext:
    """Page-scoped context. Created by PageRuntime, never by a Page or a channel."""

    tools: ToolInvoker


@dataclass(frozen=True)
class PageDefinition:
    """Static declaration of a Page.

    ``name`` is the identifier the framework addresses the Page by. ``route`` and
    ``title`` are consumed by the Web channel adapter, which does not exist yet.
    """

    name: str
    route: str
    title: str


class PageHandler(Protocol):
    """The human-facing implementation behind a Page.

    Returns ``None``: a Page builds its interface by side effect, as NiceGUI page
    builders do. Parameters are positional-only so that an app author may name them
    freely.
    """

    def __call__(self, ctx: PageContext, /) -> Awaitable[None]: ...


@dataclass(frozen=True)
class Page:
    """A PageDefinition paired with the handler that implements it.

    Not generic: a PageHandler declares no input or output model, so every Page
    already shares one static type and needs no binding step before storage.
    """

    definition: PageDefinition
    handler: PageHandler
```

Create `src/vibepy/page/__init__.py`:

```python
"""The channel-neutral Page model."""

from vibepy.page.model import Page, PageContext, PageDefinition, PageHandler, ToolInvoker

__all__ = [
    "Page",
    "PageContext",
    "PageDefinition",
    "PageHandler",
    "ToolInvoker",
]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_page_core.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 6: Run the full gate**

Run: `make lint typecheck test`
Expected: ruff clean, pyright reports 0 errors, every test passes.

- [ ] **Step 7: Commit**

```bash
git add src/vibepy/errors.py src/vibepy/page tests/test_page_core.py
git commit -m "Add the Page model declarations"
```

---

### Task 2: PageRegistry

**Files:**
- Create: `src/vibepy/page/registry.py`
- Modify: `src/vibepy/page/__init__.py`
- Test: `tests/test_page_core.py` (append)

**Interfaces:**
- Consumes: `Page`, `PageDefinition` from Task 1; `PageNotFoundError` from Task 1.
- Produces: `PageRegistry()` with `register(page: Page) -> None`, `resolve(name: str) -> Page`, `definitions() -> tuple[PageDefinition, ...]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_page_core.py`, and add `PageRegistry` to the existing `from vibepy.page import ...` line:

```python
async def noop_handler(_ctx: PageContext) -> None:
    return None


def test_resolving_an_unregistered_name_raises() -> None:
    registry = PageRegistry()

    with pytest.raises(PageNotFoundError) as raised:
        registry.resolve("todos")

    assert raised.value.page_name == "todos"


def test_a_registered_page_resolves_by_name() -> None:
    registry = PageRegistry()
    page = Page(definition=todos_definition(), handler=noop_handler)
    registry.register(page)

    assert registry.resolve("todos") is page


def test_registering_a_name_twice_replaces_the_earlier_page() -> None:
    registry = PageRegistry()
    registry.register(Page(definition=todos_definition(), handler=noop_handler))
    replacement = Page(
        definition=PageDefinition(name="todos", route="/todo-list", title="Todo list"),
        handler=noop_handler,
    )
    registry.register(replacement)

    assert registry.resolve("todos") is replacement
    assert registry.definitions() == (replacement.definition,)


def test_definitions_enumerates_every_registered_page() -> None:
    registry = PageRegistry()
    todos = Page(definition=todos_definition(), handler=noop_handler)
    archive = Page(
        definition=PageDefinition(name="archive", route="/archive", title="Archive"),
        handler=noop_handler,
    )
    registry.register(todos)
    registry.register(archive)

    assert registry.definitions() == (todos.definition, archive.definition)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_page_core.py -v`
Expected: FAIL at collection with `ImportError: cannot import name 'PageRegistry' from 'vibepy.page'`.

- [ ] **Step 3: Write the registry**

Create `src/vibepy/page/registry.py`:

```python
"""Storage of Pages under their names."""

from vibepy.errors import PageNotFoundError
from vibepy.page.model import Page, PageDefinition


class PageRegistry:
    """Maps a Page name to the Page registered under it. Storage only.

    Keyed by name rather than by route: the name is the identifier that survives a
    route change, and routes have no meaning until a Web channel registers them.
    """

    def __init__(self) -> None:
        self._pages: dict[str, Page] = {}

    def register(self, page: Page) -> None:
        self._pages[page.definition.name] = page

    def resolve(self, name: str) -> Page:
        page = self._pages.get(name)
        if page is None:
            raise PageNotFoundError(name)
        return page

    def definitions(self) -> tuple[PageDefinition, ...]:
        """Every registered declaration, in registration order.

        A Web channel adapter projects these into routes, which is enumeration
        rather than lookup.
        """
        return tuple(page.definition for page in self._pages.values())
```

Update `src/vibepy/page/__init__.py` to add the import and the `__all__` entry:

```python
"""The channel-neutral Page model."""

from vibepy.page.model import Page, PageContext, PageDefinition, PageHandler, ToolInvoker
from vibepy.page.registry import PageRegistry

__all__ = [
    "Page",
    "PageContext",
    "PageDefinition",
    "PageHandler",
    "PageRegistry",
    "ToolInvoker",
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_page_core.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Run the full gate**

Run: `make lint typecheck test`
Expected: ruff clean, pyright 0 errors, every test passes.

- [ ] **Step 6: Commit**

```bash
git add src/vibepy/page tests/test_page_core.py
git commit -m "Register Pages under their names"
```

---

### Task 3: PageRuntime and the ToolRuntime-backed ToolInvoker

This task carries the milestone's acceptance criterion.

**Files:**
- Create: `src/vibepy/page/runtime.py`
- Modify: `src/vibepy/page/__init__.py`
- Test: `tests/test_page_core.py` (append)

**Interfaces:**
- Consumes: `PageRegistry` from Task 2; `PageContext`, `ToolInvoker` from Task 1; `vibepy.tool.ToolRuntime` with `async def invoke(self, name: str, raw_input: Mapping[str, object]) -> BaseModel`.
- Produces: `PageRuntime(*, registry: PageRegistry, tool_runtime: ToolRuntime)` with `async def render(self, name: str) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_page_core.py`. Add `PageRuntime` to the `from vibepy.page import ...` line, and add these imports at the top of the file:

```python
from vibepy.errors import ToolInputValidationError, ToolNotFoundError
from vibepy.tool import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolRuntime
```

Then append:

```python
class CreateTodoInput(BaseModel):
    title: str


class Todo(BaseModel):
    id: int
    title: str
    done: bool


class TodoStore:
    def __init__(self) -> None:
        self._todos: list[Todo] = []

    def create(self, title: str) -> Todo:
        todo = Todo(id=len(self._todos) + 1, title=title, done=False)
        self._todos.append(todo)
        return todo

    def list(self) -> list[Todo]:
        return list(self._todos)


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


def build_page_runtime(registry: PageRegistry, store: TodoStore) -> PageRuntime:
    tool_registry = ToolRegistry()
    tool_registry.register(create_todo_tool(store))
    return PageRuntime(
        registry=registry,
        tool_runtime=ToolRuntime(app_id="todo", registry=tool_registry),
    )


class PageFailed(Exception):
    """Exception owned by the fixture, not by the framework."""


async def test_a_page_reaches_a_tool_through_the_tool_invoker() -> None:
    store = TodoStore()
    registry = PageRegistry()

    async def handler(ctx: PageContext) -> None:
        await ctx.tools.call("create_todo", {"title": "buy milk"})

    registry.register(Page(definition=todos_definition(), handler=handler))

    await build_page_runtime(registry, store).render("todos")

    assert store.list() == [Todo(id=1, title="buy milk", done=False)]


async def test_a_page_receives_the_validated_output_model() -> None:
    store = TodoStore()
    registry = PageRegistry()
    received: list[BaseModel] = []

    async def handler(ctx: PageContext) -> None:
        received.append(await ctx.tools.call("create_todo", {"title": "buy milk"}))

    registry.register(Page(definition=todos_definition(), handler=handler))

    await build_page_runtime(registry, store).render("todos")

    assert received == [Todo(id=1, title="buy milk", done=False)]


async def test_rendering_an_unregistered_page_raises() -> None:
    runtime = build_page_runtime(PageRegistry(), TodoStore())

    with pytest.raises(PageNotFoundError) as raised:
        await runtime.render("todos")

    assert raised.value.page_name == "todos"


async def test_calling_an_unknown_tool_name_reaches_the_caller_unchanged() -> None:
    registry = PageRegistry()

    async def handler(ctx: PageContext) -> None:
        await ctx.tools.call("delete_todo", {})

    registry.register(Page(definition=todos_definition(), handler=handler))
    runtime = build_page_runtime(registry, TodoStore())

    with pytest.raises(ToolNotFoundError) as raised:
        await runtime.render("todos")

    assert raised.value.tool_name == "delete_todo"


async def test_malformed_tool_input_reaches_the_caller_unchanged() -> None:
    registry = PageRegistry()

    async def handler(ctx: PageContext) -> None:
        await ctx.tools.call("create_todo", {})

    registry.register(Page(definition=todos_definition(), handler=handler))
    runtime = build_page_runtime(registry, TodoStore())

    with pytest.raises(ToolInputValidationError) as raised:
        await runtime.render("todos")

    assert raised.value.tool_name == "create_todo"


async def test_an_exception_from_a_page_handler_reaches_the_caller_unchanged() -> None:
    registry = PageRegistry()

    async def handler(_ctx: PageContext) -> None:
        raise PageFailed

    registry.register(Page(definition=todos_definition(), handler=handler))
    runtime = build_page_runtime(registry, TodoStore())

    with pytest.raises(PageFailed):
        await runtime.render("todos")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_page_core.py -v`
Expected: FAIL at collection with `ImportError: cannot import name 'PageRuntime' from 'vibepy.page'`.

- [ ] **Step 3: Write the runtime**

Create `src/vibepy/page/runtime.py`:

```python
"""The path that runs a Page's human-facing implementation.

``docs/architecture/page-model.md`` routes a Page to a Tool through PageContext and
ToolInvoker, so PageRuntime owns PageContext creation and hands the Page an invoker
backed by ToolRuntime.
"""

from collections.abc import Awaitable, Mapping

from pydantic import BaseModel

from vibepy.page.model import PageContext
from vibepy.page.registry import PageRegistry
from vibepy.tool.runtime import ToolRuntime


class _ToolRuntimeInvoker:
    """The ToolInvoker a Page receives. Forwards to ToolRuntime and adds nothing.

    Not async itself: ``ToolRuntime.invoke`` already returns the awaitable the
    ToolInvoker Protocol declares.
    """

    def __init__(self, tool_runtime: ToolRuntime) -> None:
        self._tool_runtime = tool_runtime

    def call(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]:
        return self._tool_runtime.invoke(name, raw_input)


class PageRuntime:
    """Resolves a Page by name, creates its PageContext, and runs its handler.

    Holds no per-Page state and does not serialize renders.
    """

    def __init__(self, *, registry: PageRegistry, tool_runtime: ToolRuntime) -> None:
        self._registry = registry
        self._tools = _ToolRuntimeInvoker(tool_runtime)

    async def render(self, name: str) -> None:
        page = self._registry.resolve(name)
        ctx = PageContext(tools=self._tools)
        await page.handler(ctx)
```

Update `src/vibepy/page/__init__.py`:

```python
"""The channel-neutral Page model."""

from vibepy.page.model import Page, PageContext, PageDefinition, PageHandler, ToolInvoker
from vibepy.page.registry import PageRegistry
from vibepy.page.runtime import PageRuntime

__all__ = [
    "Page",
    "PageContext",
    "PageDefinition",
    "PageHandler",
    "PageRegistry",
    "PageRuntime",
    "ToolInvoker",
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_page_core.py -v`
Expected: PASS, 15 tests. `test_a_page_reaches_a_tool_through_the_tool_invoker` is the milestone's acceptance criterion.

- [ ] **Step 5: Run the full gate**

Run: `make lint typecheck test`
Expected: ruff clean, pyright 0 errors, every test passes.

- [ ] **Step 6: Commit**

```bash
git add src/vibepy/page tests/test_page_core.py
git commit -m "Add the Page runtime and its Tool invoker"
```

---

### Task 4: Export the Page Core public API

**Files:**
- Modify: `src/vibepy/__init__.py`
- Test: `tests/test_package.py:4-17`

**Interfaces:**
- Consumes: every name produced by Tasks 1-3.
- Produces: `vibepy.__all__` containing the Page Core names alongside the existing Tool Core names, sorted.

- [ ] **Step 1: Update the failing test**

Replace the expected list in `tests/test_package.py::test_public_api_is_exported_from_the_package_root`:

```python
def test_public_api_is_exported_from_the_package_root() -> None:
    assert vibepy.__all__ == [
        "Page",
        "PageContext",
        "PageDefinition",
        "PageHandler",
        "PageNotFoundError",
        "PageRegistry",
        "PageRuntime",
        "Tool",
        "ToolContext",
        "ToolDefinition",
        "ToolHandler",
        "ToolInputValidationError",
        "ToolInvoker",
        "ToolNotFoundError",
        "ToolOutputValidationError",
        "ToolRegistry",
        "ToolRuntime",
        "VibepyError",
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_package.py -v`
Expected: FAIL, the assertion shows the current list without the Page names.

- [ ] **Step 3: Re-export from the package root**

Replace `src/vibepy/__init__.py` with:

```python
"""Agent-native application framework."""

from vibepy.errors import (
    PageNotFoundError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    VibepyError,
)
from vibepy.page import (
    Page,
    PageContext,
    PageDefinition,
    PageHandler,
    PageRegistry,
    PageRuntime,
    ToolInvoker,
)
from vibepy.tool import Tool, ToolContext, ToolDefinition, ToolHandler, ToolRegistry, ToolRuntime

__all__ = [
    "Page",
    "PageContext",
    "PageDefinition",
    "PageHandler",
    "PageNotFoundError",
    "PageRegistry",
    "PageRuntime",
    "Tool",
    "ToolContext",
    "ToolDefinition",
    "ToolHandler",
    "ToolInputValidationError",
    "ToolInvoker",
    "ToolNotFoundError",
    "ToolOutputValidationError",
    "ToolRegistry",
    "ToolRuntime",
    "VibepyError",
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -v`
Expected: PASS, every test in `tests/`.

- [ ] **Step 5: Run the full gate**

Run: `make lint typecheck test`
Expected: ruff clean, pyright 0 errors, every test passes.

- [ ] **Step 6: Commit**

```bash
git add src/vibepy/__init__.py tests/test_package.py
git commit -m "Export the Page Core public API"
```

---

## Integration

After Task 4, follow `AGENTS.md`: promote what is still true out of `docs/milestones/M2/` into
`docs/architecture/page-model.md` — the decided contracts (PageHandler returning `None`,
PageContext carrying only a ToolInvoker in this milestone, PageRegistry keyed by name with
enumeration, PageRuntime owning PageContext creation, Tool errors propagating unchanged) —
then delete `docs/milestones/M2/`. Do not restate in `page-model.md` anything already stated
in `tool-model.md`. Push once the milestone is merged.

## Spec coverage

| Spec section | Task |
| --- | --- |
| Package layout | 1-3 |
| PageDefinition | 1 |
| PageHandler | 1 |
| Page | 1 |
| ToolInvoker (Protocol) | 1 |
| ToolInvoker (ToolRuntime-backed implementation) | 3 |
| PageContext | 1 |
| PageRegistry | 2 |
| PageRuntime | 3 |
| Data flow | 3 |
| Public API | 4 |
| Errors | 1 |
| Testing 1 (acceptance) | 3 |
| Testing 2 (validated output model) | 3 |
| Testing 3 (unknown Page) | 2, 3 |
| Testing 4 (`ToolNotFoundError`) | 3 |
| Testing 5 (`ToolInputValidationError`) | 3 |
| Testing 6 (handler exception) | 3 |
| Testing 7 (re-registration) | 2 |
| Testing 8 (`definitions()`) | 2 |
| Testing 9 (PageContext exposes only `tools`) | 1 |
