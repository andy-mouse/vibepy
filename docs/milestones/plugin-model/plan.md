# Plugin Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dissolve the App into a Plugin declaration plus a per-channel running window owned by the channel's own host, removing the framework's runtime object and its state machine.

**Architecture:** `PluginDefinition` is a frozen value holding only declarations. An entrypoint pairs it with a lifespan at composition time. Two framework-supplied async context managers, `tool_runtime_for` and `page_runtime_for`, yield the one runtime a channel needs, for exactly as long as the block lasts. The Agent channel hands its context manager to `Server(lifespan=...)` and reads `ctx.lifespan_context`; the Web channel registers routes inside the block and its page builders close over the runtime.

**Tech Stack:** Python 3.12+, pydantic 2.9+, mcp 2.1+, nicegui 3.16+, pytest, pyright strict, ruff.

## Global Constraints

- `docs/milestones/plugin-model/spec.md` is the specification; `docs/roadmap.md` is never edited.
- `Any` and `cast` are not acceptable in the public API. Use `Protocol`, `TypedDict`, dataclass, or `TypeVar`.
- Exhaustive branches over typed unions end with `else: assert_never(value)`.
- Optional and configuration parameters are keyword-only.
- Framework exceptions derive from `VibepyError`. Exception types are the contract, message strings are not.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- Tests verify public contracts, not internals. A test-only gate standing in for a library mechanism is not acceptable.
- Every task ends green: `make lint typecheck test`.
- ADRs use the Nygard format. An `Accepted` ADR is superseded, never rewritten; marking its `Status` line as superseded is the repository's existing convention (see ADR-011).
- The verified MCP facts: the attribute is `ctx.lifespan_context` on SDK 2.1.1, and the in-memory `Client(server)` enters and exits the server's lifespan.

---

### Task 1: Record the decisions

**Files:**
- Create: `docs/decisions/ADR-020-the-plugin-replaces-the-app.md`
- Create: `docs/decisions/ADR-021-the-channel-host-owns-the-runtime-lifecycle.md`
- Create: `docs/decisions/ADR-022-a-declaration-holds-no-resource-factory.md`
- Modify: `docs/decisions/ADR-004-definition-runtime-separated.md:3`
- Modify: `docs/decisions/ADR-015-adapters-are-built-from-an-app-runtime.md:3`
- Modify: `docs/decisions/ADR-018-app-scoped-resource-is-an-async-context-manager.md:3`

**Interfaces:**
- Consumes: nothing.
- Produces: the citations every later task's docstrings and documents point at — `ADR-020`, `ADR-021`, `ADR-022`.

- [ ] **Step 1: Write ADR-020**

Context: the App is not the packaging unit (a package is), not the execution unit (ADR-017 makes that the channel process), and not a dependency scope (the lifespan is). Cite `docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md`.

Decision: `AppDefinition` becomes `PluginDefinition`, `app_id` becomes `plugin_id`, and `App` leaves the framework vocabulary. `AppRuntime` is not renamed; ADR-021 removes it.

Consequences must include, verbatim in substance:

- the error code `app.unhandled` is retired and `plugin.unhandled` replaces it; a retired code is never reused
- `docs/roadmap.md` is not edited. Its "App" and "AppDefinition" are read as "Plugin" and "PluginDefinition", and M9's "App Package" as the Plugin's package
- supersedes ADR-004, whose artifact `AppDefinition -> AppRuntime` no longer exists; the principle that a declaration is not executable state survives in ADR-022

- [ ] **Step 2: Write ADR-021**

Context: an `AppRuntime` exists while CREATED and while STOPPED, so `tool_runtime` and `page_runtime` must refuse to answer outside the running window. Quote the two host mechanisms with their sources:

- `lifespan: Callable[[Server[LifespanResultT]], AbstractAsyncContextManager[LifespanResultT]]`, entered and exited inside `run()` (<https://py.sdk.modelcontextprotocol.io/v2/api/mcp/server/lowlevel/server>)
- NiceGUI documents `app.on_startup`/`app.on_shutdown` and no lifespan (<https://nicegui.io/documentation/section_action_events>); it mounts as a sub-application under `ui.run_with` (<https://github.com/zauberzeug/nicegui/blob/main/nicegui/llms.md>); Starlette does not document lifespan state reaching a mounted sub-application (<https://github.com/kludex/starlette/blob/main/docs/lifespan.md>)

Decision: the channel host owns the running window. The framework supplies `tool_runtime_for` and `page_runtime_for` and owns no lifecycle object. The Agent channel reads its runtime from the SDK's request context; the Web channel closes over its runtime at registration, inside the block.

Consequences must include:

- `AppRuntime`, `AppRuntimeState`, `AppRuntimeTransitionError` and `AppRuntimeNotRunningError` are removed, and with them the codes `lifecycle.transition_forbidden` and `lifecycle.not_running` and the now-empty `ErrorCategory.LIFECYCLE`
- `_no_lifespan` is removed. It existed to keep `Any` out of the adapter's return type, and a real lifespan carries a real type
- the two channels use different mechanisms because each host documents a different one; a common shape would have to be invented, which ADR-003 forbids
- the SDK enters its lifespan per `run()`, so the window is one connection. Over stdio that is the process, because the client launches one process per server
- ADR-017's premise is completed: a lifespan is entered once per channel process, and ADR-015's requirement that both adapters receive one instance is destroyed by that same fact
- ADR-006 and ADR-012 stand. Their wording "AppRuntime manages start/stop execution lifecycle only" and "the runtime lifecycle adds a call to `ui.run()` at startup" names an object that no longer exists; this ADR carries both decisions forward unchanged, and how to serve becomes the entrypoint's decision
- supersedes ADR-015 and ADR-018. ADR-018's shape survives — acquisition and release are one async context manager, never paired hooks — and only its owner changes
- M6's acceptance criterion "runtime transitions through the defined lifecycle states predictably" is superseded rather than unmet. The owner was asked and approved

- [ ] **Step 3: Write ADR-022**

Context: `lifespan` is a factory, an assembly step, sitting inside a frozen value whose purpose is to be read without running. ADR-013 requires that package validation, inspection and conformance read declarations without running an App.

Decision: `PluginDefinition` declares no resource factory. An entrypoint pairs a definition with a lifespan, and that entrypoint is the composition root. Cite Seemann on composition roots being an application's, not a library's.

Consequences must include:

- ADR-013 is satisfied exactly as before. Tools and Pages remain values in the definition, and `DepsT` was never inspectable
- the definition stays generic in `DepsT`: it declares that its Tools require a resource of that type and not where one comes from, and the type checker rejects a mismatch at the one composition site
- M9 must resolve an entrypoint, not only a definition; its acceptance criterion is unaffected, because inspecting a package still means reading declarations

- [ ] **Step 4: Mark the superseded ADRs**

In each of the three files replace the `Status:` line only. Do not touch any other line.

```text
docs/decisions/ADR-004-definition-runtime-separated.md
  Status: Accepted            ->  Status: Superseded by ADR-020

docs/decisions/ADR-015-adapters-are-built-from-an-app-runtime.md
  Status: Accepted            ->  Status: Superseded by ADR-021

docs/decisions/ADR-018-app-scoped-resource-is-an-async-context-manager.md
  Status: Accepted            ->  Status: Superseded by ADR-021
```

- [ ] **Step 5: Verify**

Run: `grep -c "^Status: Superseded by ADR-02" docs/decisions/*.md | grep -v ":0"`
Expected: exactly the three files above.

Run: `make lint typecheck test`
Expected: PASS, unchanged from before this task.

- [ ] **Step 6: Commit**

```bash
git add docs/decisions
git commit -m "Decide that the Plugin replaces the App and the channel host owns the lifecycle"
```

---

### Task 2: Rename the App identifier to the Plugin identifier

Mechanical and complete in one step, so that every later task is written in the final vocabulary.

**Files:**
- Modify: `src/vibepy/tool/model.py:19`
- Modify: `src/vibepy/tool/runtime.py:76-85`
- Modify: `src/vibepy/app/model.py:32`
- Modify: `src/vibepy/app/runtime.py:69,80,91,116,122`
- Modify: `src/vibepy/adapters/mcp/server.py:112`
- Modify: `src/vibepy/errors.py:142-163`
- Test: `tests/test_tool_core.py`, `tests/test_page_core.py`, `tests/test_mcp_adapter.py`, `tests/test_nicegui_adapter.py`, `tests/test_execution_semantics.py`, `tests/test_app_runtime.py`, `tests/test_app_lifecycle.py`, `tests/test_errors.py`, `tests/todo_fixture.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ToolContext.plugin_id: str`; `ToolRuntime(*, plugin_id: str, registry: ToolRegistry[DepsT], dependencies: DepsT)`; `AppDefinition.plugin_id`.

- [ ] **Step 1: Rename the field on ToolContext**

`src/vibepy/tool/model.py`:

```python
@dataclass(frozen=True)
class ToolContext[DepsT]:
    """Invocation-scoped context. Created by ToolRuntime, never by a channel.

    ``dependencies`` is the Plugin's own application-scoped resource. The channel's
    running window creates it once and every invocation in that window receives
    that same value, typed by the plugin itself.
    """

    plugin_id: str
    invocation_id: str
    dependencies: DepsT
```

- [ ] **Step 2: Rename the parameter on ToolRuntime**

`src/vibepy/tool/runtime.py`:

```python
    def __init__(
        self, *, plugin_id: str, registry: "ToolRegistry[DepsT]", dependencies: DepsT
    ) -> None:
        self._plugin_id = plugin_id
        self._registry = registry
        self._dependencies = dependencies

    async def invoke(self, name: str, raw_input: Mapping[str, object]) -> BaseModel:
        tool = self._registry.resolve(name)
        ctx = ToolContext(
            plugin_id=self._plugin_id,
            invocation_id=str(uuid4()),
            dependencies=self._dependencies,
        )
        return await tool.bound(ctx, raw_input)
```

- [ ] **Step 3: Rename every remaining occurrence**

Rename `app_id` to `plugin_id` in the remaining `src` and `tests` sites listed under Files. In `src/vibepy/errors.py` the two lifecycle exceptions keep their `details()` key in step with the constructor parameter — the whole pair is deleted in Task 5, so the rename only has to keep the suite green here.

Run: `grep -rn "app_id" src tests | grep -v __pycache__`
Expected: no output.

- [ ] **Step 4: Verify**

Run: `make lint typecheck test`
Expected: PASS, with the same test count as before this task.

- [ ] **Step 5: Commit**

```bash
git add src tests
git commit -m "Rename the App identifier to the Plugin identifier"
```

---

### Task 3: Introduce the Plugin package

The new package lands beside the old one. Nothing imports it yet, so the suite stays green and this task is reviewable on its own.

**Files:**
- Create: `src/vibepy/plugin/__init__.py`
- Create: `src/vibepy/plugin/model.py`
- Create: `src/vibepy/plugin/composition.py`
- Test: `tests/test_plugin_composition.py`
- Modify: `tests/todo_fixture.py`

**Interfaces:**
- Consumes: `ToolContext.plugin_id` and `ToolRuntime(plugin_id=...)` from Task 2.
- Produces: `PluginDefinition[DepsT]` with fields `plugin_id, name, version, tools, pages`; `type Lifespan[DepsT] = Callable[[], AbstractAsyncContextManager[DepsT]]`; `tool_registry_for(definition, /) -> ToolRegistry[DepsT]`; `page_registry_for(definition, /) -> PageRegistry`; `tool_runtime_for(definition, lifespan, /)` and `page_runtime_for(definition, lifespan, /)`, both async context managers. From the fixture: `TODO_PLUGIN: PluginDefinition[TodoStore]` and `todo_lifespan`.

- [ ] **Step 1: Write the failing test**

`tests/test_plugin_composition.py`:

```python
"""What a channel's running window is, and what it is not.

There is no object for a plugin that is not running. These tests address the
window itself, which is why every one of them is an ``async with``.
"""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from pydantic import BaseModel

from vibepy.page import Page, PageContext, PageDefinition
from vibepy.plugin import Lifespan, PluginDefinition, page_runtime_for, tool_runtime_for
from vibepy.tool import Tool, ToolContext, ToolDefinition


class Journal:
    """The plugin's resource. Records what the lifespan did to it."""

    def __init__(self, log: list[str]) -> None:
        self.log = log


class EmptyInput(BaseModel):
    pass


class Entry(BaseModel):
    seen: str


def journal_definition(log: list[str]) -> PluginDefinition[Journal]:
    async def read(ctx: ToolContext[Journal], _payload: EmptyInput) -> Entry:
        ctx.dependencies.log.append("invoked")
        return Entry(seen=ctx.plugin_id)

    async def render(ctx: PageContext) -> None:
        await ctx.tools.invoke("read", {})

    return PluginDefinition(
        plugin_id="journal",
        name="Journal",
        version="0.0.0",
        tools=[
            Tool(
                definition=ToolDefinition(
                    name="read",
                    description="Read the journal",
                    input_model=EmptyInput,
                    output_model=Entry,
                ),
                handler=read,
            )
        ],
        pages=[
            Page(
                definition=PageDefinition(name="journal", route="/journal", title="Journal"),
                handler=render,
            )
        ],
    )


def journal_lifespan(log: list[str]) -> Lifespan[Journal]:
    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[Journal]:
        log.append("acquired")
        try:
            yield Journal(log)
        finally:
            log.append("released")

    return lifespan


async def test_the_lifespan_runs_on_both_sides_of_the_window() -> None:
    log: list[str] = []

    async with tool_runtime_for(journal_definition(log), journal_lifespan(log)):
        assert log == ["acquired"]

    assert log == ["acquired", "released"]


async def test_a_tool_receives_what_the_lifespan_yielded() -> None:
    log: list[str] = []

    async with tool_runtime_for(journal_definition(log), journal_lifespan(log)) as tools:
        result = await tools.invoke("read", {})

    assert isinstance(result, Entry)
    assert result.seen == "journal"
    assert log == ["acquired", "invoked", "released"]


async def test_two_windows_enter_two_lifespans() -> None:
    log: list[str] = []
    definition = journal_definition(log)

    async with tool_runtime_for(definition, journal_lifespan(log)) as first:
        async with tool_runtime_for(definition, journal_lifespan(log)) as second:
            first_seen = await first.invoke("read", {})
            second_seen = await second.invoke("read", {})

    assert first is not second
    assert isinstance(first_seen, Entry)
    assert isinstance(second_seen, Entry)
    assert log.count("acquired") == 2
    assert log.count("released") == 2


async def test_a_page_reaches_a_tool_through_the_window() -> None:
    log: list[str] = []

    async with page_runtime_for(journal_definition(log), journal_lifespan(log)) as pages:
        await pages.render("journal")

    assert log == ["acquired", "invoked", "released"]


class Boom(Exception):
    """A failure inside the plugin's own lifespan."""


class FailingAcquire(AbstractAsyncContextManager[Journal]):
    """A lifespan that raises on the way in.

    Written as a class rather than a generator because a generator whose body
    raises before its ``yield`` has an unreachable ``yield``. This is the form
    the retired lifecycle tests already used.
    """

    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def __aenter__(self) -> Journal:
        self._log.append("attempted")
        raise Boom("acquisition failed")

    async def __aexit__(self, *exc_info: object) -> None:
        self._log.append("released")


async def test_a_failing_acquisition_reaches_the_caller() -> None:
    log: list[str] = []

    with pytest.raises(Boom):
        async with tool_runtime_for(journal_definition(log), lambda: FailingAcquire(log)):
            pass  # pragma: no cover - the block is never entered

    assert log == ["attempted"]


async def test_an_earlier_resource_is_released_when_a_later_one_fails() -> None:
    """``__aexit__`` is registered only after ``__aenter__`` returns, so the

    resource that was acquired is released and the one that failed is not.
    """
    log: list[str] = []

    @asynccontextmanager
    async def earlier() -> AsyncGenerator[None]:
        log.append("earlier acquired")
        try:
            yield None
        finally:
            log.append("earlier released")

    @asynccontextmanager
    async def both() -> AsyncGenerator[Journal]:
        async with earlier(), FailingAcquire(log) as journal:
            yield journal

    with pytest.raises(Boom):
        async with tool_runtime_for(journal_definition(log), both):
            pass  # pragma: no cover - the block is never entered

    assert log == ["earlier acquired", "attempted", "earlier released"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_plugin_composition.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'vibepy.plugin'`.

- [ ] **Step 3: Write the declaration**

`src/vibepy/plugin/model.py`:

```python
"""Declaration of a Plugin. A value: it holds no resource and no runtime state."""

from collections.abc import Sequence
from dataclasses import dataclass

from vibepy.page.model import Page
from vibepy.tool.runtime import Tool


@dataclass(frozen=True)
class PluginDefinition[DepsT]:
    """Everything a channel needs to know about a Plugin without running it.

    ``DepsT`` is the plugin's own type for its application-scoped resource. The
    definition declares that its Tools require one of that type; it does not
    declare where one comes from. An entrypoint supplies that at composition
    time, and the type checker rejects a mismatch at that one site. See
    `docs/decisions/ADR-022-a-declaration-holds-no-resource-factory.md`.

    A Plugin whose Tools need no resource declares ``PluginDefinition[None]``.
    """

    plugin_id: str
    name: str
    version: str
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
```

- [ ] **Step 4: Write the composition**

`src/vibepy/plugin/composition.py`:

```python
"""The window in which one channel of one Plugin is running.

A declaration is paired with a lifespan here and nowhere else. What the pairing
produces exists for the duration of an ``async with`` block and cannot be reached
outside it, so the framework needs no lifecycle state and no error for a runtime
that is not running. See
`docs/decisions/ADR-021-the-channel-host-owns-the-runtime-lifecycle.md`.

Each function yields the one runtime its channel needs. Registries are built from
declarations alone, so they are made once, before the resource is acquired.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from vibepy.page.registry import PageRegistry
from vibepy.page.runtime import PageRuntime
from vibepy.plugin.model import PluginDefinition
from vibepy.tool.registry import ToolRegistry
from vibepy.tool.runtime import ToolRuntime

type Lifespan[DepsT] = Callable[[], AbstractAsyncContextManager[DepsT]]
"""A factory returning the plugin's resource for the life of one window.

What precedes the ``yield`` runs as the window opens and what follows runs as it
closes. Acquisition and release cannot be declared apart, which is what lets a
channel release a resource whose type it does not know. See
`docs/decisions/ADR-018-app-scoped-resource-is-an-async-context-manager.md`.
"""


def tool_registry_for[DepsT](definition: PluginDefinition[DepsT], /) -> ToolRegistry[DepsT]:
    """Fill a ToolRegistry from declarations. Reads no resource."""
    registry: ToolRegistry[DepsT] = ToolRegistry()
    for tool in definition.tools:
        registry.register(tool)
    return registry


def page_registry_for[DepsT](definition: PluginDefinition[DepsT], /) -> PageRegistry:
    """Fill a PageRegistry from declarations. Reads no resource."""
    registry = PageRegistry()
    for page in definition.pages:
        registry.register(page)
    return registry


@asynccontextmanager
async def tool_runtime_for[DepsT](
    definition: PluginDefinition[DepsT], lifespan: Lifespan[DepsT], /
) -> AsyncGenerator[ToolRuntime[DepsT]]:
    """The Agent channel's window: one ToolRuntime over one acquired resource."""
    registry = tool_registry_for(definition)
    async with lifespan() as dependencies:
        yield ToolRuntime(
            plugin_id=definition.plugin_id, registry=registry, dependencies=dependencies
        )


@asynccontextmanager
async def page_runtime_for[DepsT](
    definition: PluginDefinition[DepsT], lifespan: Lifespan[DepsT], /
) -> AsyncGenerator[PageRuntime]:
    """The Web channel's window: one PageRuntime over that same invocation path.

    A Page reaches Tools through ToolInvoker, which ToolRuntime satisfies, so the
    Web channel gets the canonical invocation path without seeing the runtime.
    """
    registry = page_registry_for(definition)
    async with tool_runtime_for(definition, lifespan) as tools:
        yield PageRuntime(registry=registry, tools=tools)
```

- [ ] **Step 5: Write the package export**

`src/vibepy/plugin/__init__.py`:

```python
"""The Plugin: one unit of packaging and declaration."""

from vibepy.plugin.composition import (
    Lifespan,
    page_registry_for,
    page_runtime_for,
    tool_registry_for,
    tool_runtime_for,
)
from vibepy.plugin.model import PluginDefinition

__all__ = [
    "Lifespan",
    "PluginDefinition",
    "page_registry_for",
    "page_runtime_for",
    "tool_registry_for",
    "tool_runtime_for",
]
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/test_plugin_composition.py -q`
Expected: PASS, 6 tests.

- [ ] **Step 7: Add the Plugin form of the Todo fixture**

Keep `build_todo_app()` for now; Task 4 removes it. Add to `tests/todo_fixture.py`:

```python
from vibepy.plugin import PluginDefinition

TODO_PLUGIN: PluginDefinition[TodoStore] = PluginDefinition(
    plugin_id=PLUGIN_ID,
    name="Todo",
    version="0.0.0",
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
            definition=PageDefinition(name="todos", route="/todos", title="Todos"),
            handler=todos_page,
        )
    ],
)
```

Rename the module constant `APP_ID = "todo-app"` to `PLUGIN_ID = "todo-app"` and update `build_todo_app()` to use it.

- [ ] **Step 8: Verify**

Run: `make lint typecheck test`
Expected: PASS. The suite grows by 6 tests and loses none.

- [ ] **Step 9: Commit**

```bash
git add src/vibepy/plugin tests/test_plugin_composition.py tests/todo_fixture.py
git commit -m "Compose a channel's running window from a Plugin and a lifespan"
```

---

### Task 4: Move both adapters onto the window

Both adapters change together, because `tests/test_dual_channel.py` and `tests/test_execution_semantics.py` drive both.

**Files:**
- Modify: `src/vibepy/adapters/mcp/server.py`
- Modify: `src/vibepy/adapters/nicegui/web.py`
- Test: `tests/test_mcp_adapter.py`, `tests/test_nicegui_adapter.py`, `tests/test_dual_channel.py`, `tests/test_execution_semantics.py`
- Modify: `tests/todo_fixture.py`

**Interfaces:**
- Consumes: `PluginDefinition`, `Lifespan`, `tool_registry_for`, `tool_runtime_for`, `page_runtime_for` from Task 3.
- Produces: `build_mcp_server(definition, lifespan, /) -> Server[ToolRuntime[DepsT]]`; `register_pages(definition, pages, /) -> None`.

- [ ] **Step 1: Rewrite the MCP adapter**

`src/vibepy/adapters/mcp/server.py`. Replace the module docstring's second paragraph, delete `_no_lifespan`, and replace `build_mcp_server`:

```python
def build_mcp_server[DepsT](
    definition: PluginDefinition[DepsT], lifespan: Lifespan[DepsT], /
) -> Server[ToolRuntime[DepsT]]:
    """Build the MCP projection of one Plugin's Tools.

    Static state is read from the declaration: the registry this enumerates for
    discovery, and the server's name and version. Dynamic state is read from the
    SDK's own request context, which carries whatever the lifespan yielded. The
    adapter therefore holds no running state of its own.

    The SDK enters the lifespan inside ``run()``. Over stdio the client launches
    one process per server, so that window is the process. See
    `docs/decisions/ADR-021-the-channel-host-owns-the-runtime-lifecycle.md`.
    """
    registry = tool_registry_for(definition)

    @asynccontextmanager
    async def server_lifespan(
        server: Server[ToolRuntime[DepsT]],
    ) -> AsyncGenerator[ToolRuntime[DepsT]]:
        async with tool_runtime_for(definition, lifespan) as runtime:
            yield runtime

    async def list_tools(
        ctx: ServerRequestContext[ToolRuntime[DepsT]],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[to_mcp_tool(declared) for declared in registry.definitions()]
        )

    async def call_tool(
        ctx: ServerRequestContext[ToolRuntime[DepsT]], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        try:
            result = await ctx.lifespan_context.invoke(params.name, params.arguments or {})
        except ToolNotFoundError as error:
            raise MCPError(types.INVALID_PARAMS, str(error), _payload(error)) from error
        except ToolInputValidationError as error:
            return _failure(error)
        except ToolOutputValidationError as error:
            logger.error("Tool %r returned output its own model rejected", params.name)
            return _failure(error)
        # Broad on purpose: a plugin defect must not surface as a protocol error.
        except Exception as error:
            logger.exception("Tool %r raised", params.name)
            return _failure(error)
        data = result.model_dump(by_alias=True, mode="json")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(data))],
            structured_content=data,
        )

    return Server(
        definition.plugin_id,
        version=definition.version,
        lifespan=server_lifespan,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
```

Imports become:

```python
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.shared.exceptions import MCPError

from vibepy.adapters.mcp.projection import to_mcp_tool
from vibepy.errors import (
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    to_error_info,
)
from vibepy.plugin.composition import Lifespan, tool_registry_for, tool_runtime_for
from vibepy.plugin.model import PluginDefinition
from vibepy.tool.runtime import ToolRuntime
```

- [ ] **Step 2: Rewrite the NiceGUI adapter**

`src/vibepy/adapters/nicegui/web.py`:

```python
"""The Web routes a human reaches, and the single render path behind them.

Route validation reads the declaration; the builders close over the PageRuntime
the caller's window yielded. Registration therefore happens inside that window,
and a builder holds its runtime for exactly as long as the window lasts.

NiceGUI documents no lifespan and mounts as a sub-application, and Starlette does
not document lifespan state reaching one, so nothing here reads request state. See
`docs/decisions/ADR-021-the-channel-host-owns-the-runtime-lifecycle.md`.

Registering routes is not running a server.
"""

from collections.abc import Awaitable, Callable

from nicegui import ui

from vibepy.errors import PageRouteConflictError, PageRouteInvalidError
from vibepy.page.runtime import PageRuntime
from vibepy.plugin.model import PluginDefinition


def register_pages[DepsT](definition: PluginDefinition[DepsT], pages: PageRuntime, /) -> None:
    """Project every declared Page of one Plugin onto a NiceGUI route.

    Every declaration is validated before any route is registered, so a rejected
    Plugin leaves no half-registered application behind.
    """
    claimed: dict[str, str] = {}
    for page in definition.pages:
        declared = page.definition
        if not declared.route.startswith("/"):
            raise PageRouteInvalidError(declared.name, declared.route)
        owner = claimed.get(declared.route)
        if owner is not None:
            raise PageRouteConflictError(declared.route, owner, declared.name)
        claimed[declared.route] = declared.name

    for page in definition.pages:
        declared = page.definition
        ui.page(declared.route, title=declared.title)(_builder(pages, declared.name))


def _builder(runtime: PageRuntime, name: str) -> Callable[[], Awaitable[None]]:
    """The page builder NiceGUI calls per visitor.

    Addressed by name rather than by route, so a route change never reaches
    PageRuntime.
    """

    async def build() -> None:
        await runtime.render(name)

    return build
```

- [ ] **Step 3: Move the MCP adapter tests onto the window**

In `tests/test_mcp_adapter.py` replace `server_for` and drop the `AppRuntime`/`started` imports:

```python
@asynccontextmanager
async def server_for(tools: list[Tool[None]]) -> AsyncGenerator[Server[ToolRuntime[None]]]:
    """One Plugin with no application-scoped resource: these fixtures hold their own."""
    yield build_mcp_server(
        PluginDefinition(
            plugin_id=PLUGIN_ID,
            name="Test",
            version="0.0.0",
            tools=tools,
            pages=[],
        ),
        no_dependencies,
    )
```

Rename `APP_ID` to `PLUGIN_ID` and `first.app_id`/`second.app_id` to `first.plugin_id`/`second.plugin_id`. In `test_the_core_packages_do_not_import_mcp`, replace `package / "app"` with `package / "plugin"`.

- [ ] **Step 4: Move the NiceGUI adapter tests onto the window**

In `tests/test_nicegui_adapter.py`, replace `build_web_app` with a definition builder and each test's `async with started(...)` with `async with page_runtime_for(definition, no_dependencies) as pages: register_pages(definition, pages)`:

```python
def web_definition(pages: list[Page]) -> PluginDefinition[None]:
    return PluginDefinition(
        plugin_id=PLUGIN_ID,
        name="Test",
        version="0.0.0",
        tools=[],
        pages=pages,
    )
```

The route-validation tests call `register_pages(definition, pages)` inside the window and assert the same exceptions as before.

- [ ] **Step 5: Move the execution-semantics test onto the window**

In `tests/test_execution_semantics.py`, replace `build_app()` returning an `AppRuntime` with `rendezvous_definition()` returning a `PluginDefinition[Rendezvous]` plus a `rendezvous_lifespan`, and replace each `async with started(build_app()) as app` with `async with tool_runtime_for(...) as tools` or `page_runtime_for(...) as pages`. The barrier proof is unchanged: it still opens only once two invocations are inside it, reached through `ToolContext.dependencies`.

For the Agent-channel case:

```python
async with Client(build_mcp_server(rendezvous_definition(), rendezvous_lifespan)) as agent:
```

- [ ] **Step 6: Restate the dual-channel contract**

`tests/test_dual_channel.py`. The claim changes; the mechanics barely do.

```python
"""The dual-channel contract from docs/architecture/runtime.md.

Both channels reach one Tool implementation over one resource, so neither keeps a
backend of its own. This test is constitutional: it stays for the life of the
project.

What it does not claim is that a deployed Plugin shares one resource across its
channels. ADR-017 puts each channel in its own process, so sharing is a property
of the composition a test or an entrypoint arranges, never a framework guarantee.
Here one lifespan is composed into both channels precisely so that any private
backend would show up as a divergence.

It does not assert that every Tool belongs on every channel. Deciding that a Tool
is hidden from a channel is M14.
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
from vibepy.plugin import page_runtime_for


def titles(result: object) -> list[str]:
    """Read the titles back through the Tool's own output model.

    Digging through the raw mapping would assert against a shape no contract
    guarantees; the output model is the contract.
    """
    return [todo.title for todo in TodoList.model_validate(result).todos]


async def test_both_channels_reach_one_backend(user: User) -> None:
    store = TodoStore()

    @asynccontextmanager
    async def shared() -> AsyncGenerator[TodoStore]:
        """One resource composed into both channels, so a private backend shows."""
        yield store

    async with page_runtime_for(TODO_PLUGIN, shared) as pages:
        register_pages(TODO_PLUGIN, pages)

        async with Client(build_mcp_server(TODO_PLUGIN, shared)) as agent:
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

- [ ] **Step 7: Delete the superseded fixture entrypoint**

Remove `build_todo_app()` and the `AppDefinition`/`AppRuntime` imports from `tests/todo_fixture.py`. `TODO_PLUGIN` and `todo_lifespan` are what remains.

- [ ] **Step 8: Verify**

Run: `make lint typecheck test`
Expected: PASS. `tests/test_app_lifecycle.py` and `tests/test_app_runtime.py` still exist and still pass against the old `AppRuntime`; Task 5 removes them.

- [ ] **Step 9: Commit**

```bash
git add src/vibepy/adapters tests
git commit -m "Build both channel adapters from a Plugin and a lifespan"
```

---

### Task 5: Remove the runtime object and its errors

**Files:**
- Delete: `src/vibepy/app/__init__.py`, `src/vibepy/app/model.py`, `src/vibepy/app/runtime.py`, `src/vibepy/lifecycle.py`
- Delete: `tests/test_app_lifecycle.py`, `tests/test_app_runtime.py`
- Modify: `src/vibepy/errors.py`, `src/vibepy/__init__.py`, `tests/lifecycle.py`, `tests/test_errors.py`, `tests/test_package.py`

**Interfaces:**
- Consumes: everything from Tasks 3 and 4; nothing outside `tests/test_app_*.py` still imports `vibepy.app`.
- Produces: a public API with six error codes and no lifecycle vocabulary.

- [ ] **Step 1: Confirm nothing depends on what is about to go**

Run: `grep -rn "vibepy.app\|AppRuntime\|AppDefinition\|vibepy.lifecycle" src tests | grep -v __pycache__ | grep -v "tests/test_app_"`
Expected: no output.

- [ ] **Step 2: Delete the modules and their tests**

```bash
git rm -r src/vibepy/app src/vibepy/lifecycle.py tests/test_app_lifecycle.py tests/test_app_runtime.py
```

- [ ] **Step 3: Retire the lifecycle errors and rename the unhandled code**

In `src/vibepy/errors.py`: delete the `from vibepy.lifecycle import AppRuntimeState` import, the `AppRuntimeTransitionError` and `AppRuntimeNotRunningError` classes, their two rows in `_CATEGORIES`, and `ErrorCategory.LIFECYCLE`. Change the module constant:

```python
UNHANDLED_CODE = "plugin.unhandled"
"""The code for a failure the framework did not define. It belongs to no exception."""
```

and the docstring of `ErrorCategory.LIFECYCLE`'s neighbours stays as written. The remaining categories are `CALLER`, `EXECUTION` and `DECLARATION`.

- [ ] **Step 4: Trim the package exports**

In `src/vibepy/__init__.py` remove the `vibepy.app` and `vibepy.lifecycle` imports and the five names `AppDefinition`, `AppRuntime`, `AppRuntimeNotRunningError`, `AppRuntimeState`, `AppRuntimeTransitionError` from `__all__`; add `PluginDefinition`, `Lifespan`, `page_runtime_for` and `tool_runtime_for` from `vibepy.plugin`, keeping `__all__` alphabetically sorted.

- [ ] **Step 5: Trim the shared test helper**

`tests/lifecycle.py` keeps only `no_dependencies`; `started` is deleted with the object it started. Update the module docstring to say what remains.

- [ ] **Step 6: Update the error catalogue tests**

In `tests/test_errors.py` remove the two `CASES` entries and the `AppRuntimeState` import. The catalogue test that walks `VibepyError.__subclasses__()` needs no change: it discovers six descendants instead of eight.

- [ ] **Step 7: Update the public-API test**

In `tests/test_package.py` remove the five names and add the four new ones, matching `__all__`.

- [ ] **Step 8: Verify**

Run: `grep -rn "app\." src/vibepy/errors.py`
Expected: no output — `app.unhandled` is gone.

Run: `make lint typecheck test`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "Remove AppRuntime, its state machine and its errors"
```

---

### Task 6: Bring the documents to the new truth

**Files:**
- Rename: `docs/architecture/app-model.md` to `docs/architecture/plugin-model.md`
- Modify: `docs/architecture.md`, `docs/architecture/lifecycle.md`, `docs/architecture/runtime.md`, `docs/architecture/adapters.md`, `docs/architecture/errors.md`, `docs/architecture/tool-model.md`, `docs/architecture/page-model.md`, `docs/architecture/authoring.md`, `AGENTS.md`

**Interfaces:**
- Consumes: ADR-020, ADR-021 and ADR-022 from Task 1, cited by name from the documents that carry their consequences.
- Produces: nothing code depends on.

- [ ] **Step 1: Rewrite the model document**

`git mv docs/architecture/app-model.md docs/architecture/plugin-model.md`. Rewrite it around `PluginDefinition` and the two windows. Keep the three state scopes; application scope is owned by the channel's window rather than by an object. Delete the `AppRuntime` section and the invariants that name it. Keep the share-nothing paragraph ADR-017 put there.

- [ ] **Step 2: Rewrite the lifecycle document**

`docs/architecture/lifecycle.md`. Delete the state diagram, `AppRuntime.state`, the transition rules, the two framework errors, and the Startup/Shutdown/Cleanup sections that describe them. What survives: the lifespan's `yield` as the boundary between opening and closing, the cleanup discipline as a property of `async with` and `AsyncExitStack` rather than of framework code, and the Package lifecycle section unchanged.

- [ ] **Step 3: Correct the runtime document**

`docs/architecture/runtime.md`. `ToolContext` carries `plugin_id`. The Dependency ownership section points at the window instead of `AppRuntime`. Rewrite the Dual-channel contract section to the claim Task 4 Step 6 gives the test, and say explicitly that sharing is a property of the composition and not a framework guarantee. Leave the concurrency sections and their sources untouched.

- [ ] **Step 4: Correct the adapter document**

`docs/architecture/adapters.md`. The Principle paragraph: an adapter is built from a declaration and a lifespan, and reads its runtime from its own host's window. Update the two signatures. Add why the two channels differ, citing ADR-021. Keep the ADR-010 and ADR-012 paragraphs, which are unaffected.

- [ ] **Step 5: Correct the error document**

`docs/architecture/errors.md`. Remove the two `lifecycle.*` rows from the code table and the `lifecycle` row from the category table. Replace `app.unhandled` with `plugin.unhandled`. Add a short paragraph recording that the two codes and the category are retired and never reused, citing ADR-021.

- [ ] **Step 6: Correct the three remaining architecture documents**

- `docs/architecture/tool-model.md`: the ToolRuntime section is constructed from a plugin id, a ToolRegistry and the resource the window acquired.
- `docs/architecture/page-model.md`: the PageRuntime section takes its ToolInvoker from the window, not from `AppRuntime`.
- `docs/architecture/authoring.md`: `start_app`/`stop_app`/`app_status` become `start_plugin`/`stop_plugin`/`plugin_status`, describing the Web channel runtime the Hub owns, per ADR-017.

- [ ] **Step 7: Correct the overview**

`docs/architecture.md`. The Core model tree is rooted at `Plugin`. Remove "The framework runtime composes these into an executable AppRuntime". In Framework ownership, "runtime lifecycle" becomes the composition of a channel window. In Key distinctions, replace the two `AppRuntime` lines with: a PluginDefinition is not a running channel, and a channel window is not a package installation. Update the Documents list for the rename.

- [ ] **Step 8: Correct the invariants**

`AGENTS.md`, four lines:

```text
L13  "operations of an App"                                -> "operations of a Plugin"
L16  "App is the unit of application definition and         -> "Plugin is the unit of packaging and declaration;
      runtime composition."                                     a channel process is the unit of execution."
L27  "AppDefinition and AppRuntime are different concepts." -> "A declaration is not a running channel."
L29  "App-scoped state belongs to AppRuntime."              -> "Application-scoped state belongs to the channel's
                                                                 running window and reaches a handler only through
                                                                 ToolContext."
```

Leave every other invariant untouched.

- [ ] **Step 9: Verify**

Run: `grep -rn "AppRuntime\|AppDefinition\|app-model" docs AGENTS.md | grep -v "docs/decisions/ADR-0" | grep -v docs/roadmap.md | grep -v docs/milestones`
Expected: no output. ADRs keep their historical wording; the roadmap is never edited; the milestone folder is deleted at integration.

Run: `make lint typecheck test`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "Describe the Plugin model and the channel window"
```

---

## Integration

After Task 6, use superpowers:finishing-a-development-branch. Before merging, promote nothing out of `docs/milestones/plugin-model/` — Tasks 1 and 6 have already placed every durable statement in an ADR or an architecture document — then delete the folder, as `AGENTS.md` requires.
