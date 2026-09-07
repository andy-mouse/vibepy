# M6 Runtime Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `AppRuntime` the lifecycle `CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED`, acquiring the app-scoped resource through a lifespan async context manager and unwinding it deterministically.

**Architecture:** `AppDefinition.create_dependencies` becomes `lifespan`, a factory returning an `AbstractAsyncContextManager[DepsT]`. `AppRuntime.start()` enters it through an `AsyncExitStack` and builds `ToolRuntime`/`PageRuntime` over the value it yields; `stop()` unwinds the stack. The runtimes therefore exist only while `RUNNING`, and channel adapters are built from a started AppRuntime.

**Tech Stack:** Python 3.12+, `contextlib.AsyncExitStack`, pydantic 2, pytest with `asyncio_mode = "auto"`, pyright strict, ruff.

**Spec:** `docs/milestones/M6/spec.md`. Read it before starting. It carries the reasoning, the sources, and the owner's approval to depart from the roadmap's `on_start`/`on_stop` wording.

## Global Constraints

- `make lint typecheck test` must pass. That is the definition of done for every task.
- `docs/roadmap.md` is never edited.
- `Any` and `cast` are not acceptable in the public API. Use `Protocol`, `TypedDict`, dataclass, or `TypeVar`.
- Optional and configuration parameters are keyword-only.
- Framework exceptions derive from `VibepyError`. Exception types are the contract, not message strings.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- Tests verify public contracts, not internals.
- ruff: `line-length = 100`, rules `E, F, I, UP, B, ASYNC, RUF`.
- pyright: `typeCheckingMode = "strict"`, `pythonVersion = "3.12"`.
- `contextlib.AbstractAsyncContextManager` is the type to use. `typing.AsyncContextManager` is a deprecated alias and must not appear.
- Do not build ahead: no adapter startup (`ui.run()`), no timeouts, no cancellation, no error codes, no config model, no Hub.

---

### Task 1: The lifecycle and the lifespan

The state machine and the resource move land together. The field rename breaks every construction site at once, and the runtimes cannot be built before the resource exists, so there is no smaller change that leaves the suite green.

**Files:**
- Create: `src/vibepy/lifecycle.py`
- Create: `tests/test_app_lifecycle.py`
- Create: `tests/lifecycle.py`
- Modify: `src/vibepy/errors.py`
- Modify: `src/vibepy/app/model.py`
- Modify: `src/vibepy/app/runtime.py`
- Modify: `src/vibepy/__init__.py`
- Modify: `tests/test_package.py`
- Modify: `tests/todo_fixture.py`
- Modify: `tests/test_app_runtime.py`
- Modify: `tests/test_execution_semantics.py`
- Modify: `tests/test_dual_channel.py`
- Modify: `tests/test_nicegui_adapter.py`
- Modify: `tests/test_mcp_adapter.py`

**Interfaces:**
- Produces: `vibepy.lifecycle.AppRuntimeState` (`StrEnum` with `CREATED`, `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`); `vibepy.errors.AppRuntimeTransitionError(app_id: str, state: AppRuntimeState, transition: str)` with attributes `app_id`, `state`, `transition`; `vibepy.errors.AppRuntimeNotRunningError(app_id: str, state: AppRuntimeState)` with attributes `app_id`, `state`; `AppDefinition.lifespan: Callable[[], AbstractAsyncContextManager[DepsT]]`; `AppRuntime.state`, `AppRuntime.start()`, `AppRuntime.stop()`; test helpers `tests.lifecycle.started(app)` and `tests.lifecycle.no_dependencies()`.

- [ ] **Step 1: Write the failing lifecycle test**

Create `tests/test_app_lifecycle.py`:

```python
"""The runtime lifecycle contract from docs/architecture/lifecycle.md.

The resource is acquired by a lifespan, so the tests observe the boundaries the
way an app does: what the lifespan recorded, read back through a Tool or through
the list the lifespan wrote into.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from pydantic import BaseModel

from vibepy.app import AppDefinition, AppRuntime
from vibepy.errors import AppRuntimeNotRunningError, AppRuntimeTransitionError
from vibepy.lifecycle import AppRuntimeState
from vibepy.tool import Tool, ToolContext, ToolDefinition


class Journal:
    """The app's application-scoped resource: what its lifespan recorded."""

    def __init__(self, entries: list[str]) -> None:
        self.entries = entries


class EmptyInput(BaseModel):
    pass


class Entries(BaseModel):
    entries: list[str]


async def read_entries(ctx: ToolContext[Journal], _payload: EmptyInput) -> Entries:
    return Entries(entries=list(ctx.dependencies.entries))


READ_ENTRIES = Tool(
    definition=ToolDefinition(
        name="read_entries",
        description="Report what the lifespan recorded",
        input_model=EmptyInput,
        output_model=Entries,
    ),
    handler=read_entries,
)


def journal_app(entries: list[str]) -> AppRuntime[Journal]:
    """An App whose lifespan writes into a list the caller keeps."""

    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[Journal]:
        entries.append("acquired")
        yield Journal(entries)
        entries.append("released")

    return AppRuntime(
        AppDefinition(
            app_id="journal-app",
            name="Journal",
            version="0.0.0",
            lifespan=lifespan,
            tools=[READ_ENTRIES],
            pages=[],
        )
    )


def test_a_constructed_runtime_is_created() -> None:
    assert journal_app([]).state is AppRuntimeState.CREATED


def test_construction_acquires_nothing() -> None:
    entries: list[str] = []

    journal_app(entries)

    assert entries == []


async def test_start_reaches_running() -> None:
    app = journal_app([])

    await app.start()

    assert app.state is AppRuntimeState.RUNNING


async def test_stop_reaches_stopped() -> None:
    app = journal_app([])
    await app.start()

    await app.stop()

    assert app.state is AppRuntimeState.STOPPED


async def test_the_lifespan_runs_on_both_sides_of_the_running_window() -> None:
    entries: list[str] = []
    app = journal_app(entries)

    await app.start()
    acquired = list(entries)
    await app.stop()

    assert acquired == ["acquired"]
    assert entries == ["acquired", "released"]


async def test_a_tool_receives_what_the_lifespan_yielded() -> None:
    app = journal_app([])
    await app.start()

    result = await app.tool_runtime.invoke("read_entries", {})

    await app.stop()
    assert result == Entries(entries=["acquired"])


async def test_two_runtimes_enter_two_lifespans() -> None:
    first_entries: list[str] = []
    second_entries: list[str] = []
    first = journal_app(first_entries)
    second = journal_app(second_entries)

    await first.start()

    assert first_entries == ["acquired"]
    assert second_entries == []
    await first.stop()


async def test_the_pre_yield_body_runs_while_starting() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[None]:
        entered.set()
        await release.wait()
        yield None

    app = AppRuntime(
        AppDefinition(
            app_id="slow-app",
            name="Slow",
            version="0.0.0",
            lifespan=lifespan,
            tools=[],
            pages=[],
        )
    )

    starting = asyncio.create_task(app.start())
    await entered.wait()
    assert app.state is AppRuntimeState.STARTING

    release.set()
    await starting
    assert app.state is AppRuntimeState.RUNNING
    await app.stop()


async def test_the_post_yield_body_runs_while_stopping() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[None]:
        yield None
        entered.set()
        await release.wait()

    app = AppRuntime(
        AppDefinition(
            app_id="slow-app",
            name="Slow",
            version="0.0.0",
            lifespan=lifespan,
            tools=[],
            pages=[],
        )
    )
    await app.start()

    stopping = asyncio.create_task(app.stop())
    await entered.wait()
    assert app.state is AppRuntimeState.STOPPING

    release.set()
    await stopping
    assert app.state is AppRuntimeState.STOPPED


async def test_starting_a_running_runtime_is_refused() -> None:
    app = journal_app([])
    await app.start()

    with pytest.raises(AppRuntimeTransitionError) as raised:
        await app.start()

    assert raised.value.app_id == "journal-app"
    assert raised.value.state is AppRuntimeState.RUNNING
    assert app.state is AppRuntimeState.RUNNING
    await app.stop()


async def test_stopped_is_terminal() -> None:
    app = journal_app([])
    await app.start()
    await app.stop()

    with pytest.raises(AppRuntimeTransitionError):
        await app.start()

    assert app.state is AppRuntimeState.STOPPED


async def test_stopping_before_starting_is_refused() -> None:
    app = journal_app([])

    with pytest.raises(AppRuntimeTransitionError) as raised:
        await app.stop()

    assert raised.value.state is AppRuntimeState.CREATED


async def test_concurrent_starts_admit_exactly_one() -> None:
    entries: list[str] = []
    app = journal_app(entries)

    outcomes = await asyncio.gather(app.start(), app.start(), return_exceptions=True)

    failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    assert len(failures) == 1
    assert isinstance(failures[0], AppRuntimeTransitionError)
    assert entries == ["acquired"]
    assert app.state is AppRuntimeState.RUNNING
    await app.stop()


def test_the_registries_are_readable_before_start() -> None:
    app = journal_app([])

    names = [definition.name for definition in app.tool_registry.definitions()]

    assert names == ["read_entries"]


def test_the_tool_runtime_is_unavailable_before_start() -> None:
    app = journal_app([])

    with pytest.raises(AppRuntimeNotRunningError) as raised:
        _ = app.tool_runtime

    assert raised.value.app_id == "journal-app"
    assert raised.value.state is AppRuntimeState.CREATED


def test_the_page_runtime_is_unavailable_before_start() -> None:
    app = journal_app([])

    with pytest.raises(AppRuntimeNotRunningError):
        _ = app.page_runtime


async def test_the_tool_runtime_is_unavailable_after_stop() -> None:
    app = journal_app([])
    await app.start()
    await app.stop()

    with pytest.raises(AppRuntimeNotRunningError) as raised:
        _ = app.tool_runtime

    assert raised.value.state is AppRuntimeState.STOPPED


async def test_one_running_window_has_one_tool_runtime() -> None:
    app = journal_app([])
    await app.start()

    assert app.tool_runtime is app.tool_runtime

    await app.stop()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_app_lifecycle.py -x -q`

Expected: collection error — `ImportError: cannot import name 'AppRuntimeState' from 'vibepy.lifecycle'` (the module does not exist).

- [ ] **Step 3: Create the state enum**

Create `src/vibepy/lifecycle.py`. It is a top-level module rather than part of `vibepy.app` so that `vibepy.errors` can import it without a cycle: `vibepy.app.__init__` imports the runtime, which imports the errors.

```python
"""The states an AppRuntime passes through.

These are the framework's runtime states. Install, upgrade and uninstall belong
to the package control plane and are deliberately absent. See
`docs/decisions/ADR-006-runtime-vs-package-lifecycle.md`.
"""

from enum import StrEnum


class AppRuntimeState(StrEnum):
    """``CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED``.

    A string enum because the value is what an operator reads in a log and what
    a control plane reports.

    STOPPED is terminal. An unwound runtime holds no resource to re-enter, so a
    restart is a new AppRuntime, isolated from its predecessor by default.
    """

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
```

- [ ] **Step 4: Add the two exceptions**

Append to `src/vibepy/errors.py`, and add the import at the top of the file:

```python
from vibepy.lifecycle import AppRuntimeState
```

```python
class AppRuntimeTransitionError(VibepyError):
    """A lifecycle transition the runtime's current state forbids."""

    def __init__(self, app_id: str, state: AppRuntimeState, transition: str) -> None:
        super().__init__(f"App {app_id!r} cannot {transition} while {state.value}")
        self.app_id = app_id
        self.state = state
        self.transition = transition


class AppRuntimeNotRunningError(VibepyError):
    """A runtime that exists only while RUNNING was reached outside that window."""

    def __init__(self, app_id: str, state: AppRuntimeState) -> None:
        super().__init__(f"App {app_id!r} is {state.value}, not running")
        self.app_id = app_id
        self.state = state
```

Two types because they are two failures: one is a caller driving the lifecycle wrongly, the other is a caller using the App outside its running window.

- [ ] **Step 5: Replace the factory with the lifespan on AppDefinition**

In `src/vibepy/app/model.py`, change the import line and the field, and rewrite the paragraph that describes it:

```python
"""Declaration of an App. Static: it holds no live resource and no runtime state."""

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from vibepy.page.model import Page
from vibepy.tool.runtime import Tool


@dataclass(frozen=True)
class AppDefinition[DepsT]:
    """Everything AppRuntime needs to compose one running App.

    ``lifespan`` is a factory returning an async context manager rather than a
    live one. A definition that held a live resource could not be a declaration,
    and one definition would yield runtimes that shared state; a factory yields
    runtimes isolated from one another by default.

    What precedes the context manager's ``yield`` runs while the runtime is
    STARTING, what follows runs while it is STOPPING. Acquisition and release
    cannot be declared apart, which is what lets the framework release a resource
    whose type it does not know. See
    `docs/decisions/ADR-018-the-app-scoped-resource-is-an-async-context-manager.md`.

    ``DepsT`` is the app's own type for its application-scoped resource. An App
    that has none declares ``AppDefinition[None]`` with a lifespan yielding
    ``None``; no default is provided, because the framework does not guess that an
    App is stateless.
    """

    app_id: str
    name: str
    version: str
    lifespan: Callable[[], AbstractAsyncContextManager[DepsT]]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
```

- [ ] **Step 6: Give AppRuntime the lifecycle**

Replace `src/vibepy/app/runtime.py` entirely:

```python
"""The executable instance of an AppDefinition.

AppRuntime owns application-scoped state: the resource its definition's lifespan
yields, the two registries filled from that definition, and the two runtimes over
them. Both channel adapters of one App are built from one AppRuntime, so both
reach that one resource.

The registries are filled at construction because they are made of declarations.
The resource is acquired at startup, which is where
`docs/architecture/lifecycle.md` places it, so the runtimes over it exist only
while the App is RUNNING.
"""

from contextlib import AsyncExitStack

from vibepy.app.model import AppDefinition
from vibepy.errors import AppRuntimeNotRunningError, AppRuntimeTransitionError
from vibepy.lifecycle import AppRuntimeState
from vibepy.page.registry import PageRegistry
from vibepy.page.runtime import PageRuntime
from vibepy.tool.registry import ToolRegistry
from vibepy.tool.runtime import ToolRuntime


class AppRuntime[DepsT]:
    """Composes one AppDefinition into a running App.

    Constructing an AppRuntime acquires nothing, starts no server and no adapter.
    A channel adapter is built from a started AppRuntime, because it reads the
    runtimes startup produced.

    The application-scoped resource is not exposed. A Tool handler receives it
    through its ToolContext, and nothing else needs it.

    Startup and shutdown unwind through one AsyncExitStack, so a step that did not
    complete has nothing to unwind and later steps register themselves the same
    way.
    """

    def __init__(self, definition: AppDefinition[DepsT]) -> None:
        self._definition = definition
        self._state = AppRuntimeState.CREATED
        self._stack = AsyncExitStack()
        self._tool_runtime: ToolRuntime[DepsT] | None = None
        self._page_runtime: PageRuntime | None = None

        tool_registry: ToolRegistry[DepsT] = ToolRegistry()
        for tool in definition.tools:
            tool_registry.register(tool)
        self._tool_registry = tool_registry

        page_registry = PageRegistry()
        for page in definition.pages:
            page_registry.register(page)
        self._page_registry = page_registry

    @property
    def state(self) -> AppRuntimeState:
        return self._state

    async def start(self) -> None:
        """Acquire the app-scoped resource and build the runtimes over it.

        The transition to STARTING is synchronous and precedes the first await, so
        a second caller observes a state that forbids starting rather than
        entering a second lifespan.
        """
        if self._state is not AppRuntimeState.CREATED:
            raise AppRuntimeTransitionError(self._definition.app_id, self._state, "start")
        self._state = AppRuntimeState.STARTING

        dependencies = await self._stack.enter_async_context(self._definition.lifespan())

        tool_runtime = ToolRuntime(
            app_id=self._definition.app_id,
            registry=self._tool_registry,
            dependencies=dependencies,
        )
        self._tool_runtime = tool_runtime
        self._page_runtime = PageRuntime(registry=self._page_registry, tools=tool_runtime)
        self._state = AppRuntimeState.RUNNING

    async def stop(self) -> None:
        """Unwind what startup acquired, in reverse."""
        if self._state is not AppRuntimeState.RUNNING:
            raise AppRuntimeTransitionError(self._definition.app_id, self._state, "stop")
        self._state = AppRuntimeState.STOPPING

        await self._stack.aclose()

        self._tool_runtime = None
        self._page_runtime = None
        self._state = AppRuntimeState.STOPPED

    @property
    def definition(self) -> AppDefinition[DepsT]:
        return self._definition

    @property
    def tool_registry(self) -> ToolRegistry[DepsT]:
        return self._tool_registry

    @property
    def page_registry(self) -> PageRegistry:
        return self._page_registry

    @property
    def tool_runtime(self) -> ToolRuntime[DepsT]:
        if self._tool_runtime is None:
            raise AppRuntimeNotRunningError(self._definition.app_id, self._state)
        return self._tool_runtime

    @property
    def page_runtime(self) -> PageRuntime:
        if self._page_runtime is None:
            raise AppRuntimeNotRunningError(self._definition.app_id, self._state)
        return self._page_runtime
```

Failure handling is Task 2. Leave `start()` and `stop()` exactly as written here.

- [ ] **Step 7: Export the new names**

In `src/vibepy/__init__.py`, add the imports and the `__all__` entries:

```python
from vibepy.errors import (
    AppRuntimeNotRunningError,
    AppRuntimeTransitionError,
    PageNotFoundError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    VibepyError,
)
from vibepy.lifecycle import AppRuntimeState
```

`__all__` stays alphabetically sorted; the three new names go after `"AppRuntime"`:

```python
    "AppDefinition",
    "AppRuntime",
    "AppRuntimeNotRunningError",
    "AppRuntimeState",
    "AppRuntimeTransitionError",
    "Page",
```

- [ ] **Step 8: Update the exported-API test**

In `tests/test_package.py`, add the same three names in the same positions to the expected `__all__` list.

- [ ] **Step 9: Run the lifecycle test to verify it passes**

Run: `uv run pytest tests/test_app_lifecycle.py tests/test_package.py -q`

Expected: PASS.

- [ ] **Step 10: Run the whole suite to see what the rename broke**

Run: `uv run pytest -q`

Expected: FAIL. Every `AppDefinition(...)` call site still passes `create_dependencies`, which is now an unexpected keyword argument.

- [ ] **Step 11: Add the shared test helpers**

Create `tests/lifecycle.py`:

```python
"""Lifecycle helpers the test suite shares.

The framework offers no ``async with`` over an AppRuntime, so tests that need a
started App pair start with stop themselves. This is that pairing, written once.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from vibepy.app import AppRuntime


@asynccontextmanager
async def started[DepsT](app: AppRuntime[DepsT]) -> AsyncGenerator[AppRuntime[DepsT]]:
    """Start an App for the duration of the block and stop it afterwards."""
    await app.start()
    try:
        yield app
    finally:
        await app.stop()


@asynccontextmanager
async def no_dependencies() -> AsyncGenerator[None]:
    """The lifespan of an App with no application-scoped resource."""
    yield None
```

- [ ] **Step 12: Convert the Todo fixture to a lifespan**

In `tests/todo_fixture.py`, add the imports:

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
```

Use `AsyncGenerator` rather than `AsyncIterator` for every `@asynccontextmanager` return annotation: pyright reports the `AsyncIterator` form as deprecated.

Add the lifespan next to `TodoStore`:

```python
@asynccontextmanager
async def todo_lifespan() -> AsyncGenerator[TodoStore]:
    """The Todo App's resource, acquired at startup and dropped at shutdown."""
    yield TodoStore()
```

and in `build_todo_app`, replace `create_dependencies=TodoStore,` with `lifespan=todo_lifespan,`.

`TodoStore` holds only a list, so there is nothing to close after the `yield`. Do not invent a `close()` for it.

- [ ] **Step 13: Update the M5A app-runtime tests**

In `tests/test_app_runtime.py`:

Add the imports:

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from tests.lifecycle import started
```

Add the lifespan below `Counter`:

```python
@asynccontextmanager
async def counter_lifespan() -> AsyncGenerator[Counter]:
    yield Counter()
```

In `build_definition`, replace `create_dependencies=Counter,` with `lifespan=counter_lifespan,`.

Wrap every test that reaches `tool_runtime` or `page_runtime` in `started(...)`. The five affected tests become:

```python
async def test_calls_through_one_runtime_share_app_scoped_state() -> None:
    async with started(AppRuntime(build_definition())) as app:
        await app.tool_runtime.invoke("increment", {})
        await app.tool_runtime.invoke("increment", {})

        assert await app.tool_runtime.invoke("read", {}) == Count(value=2)


async def test_a_second_runtime_is_isolated_by_default() -> None:
    definition = build_definition()

    async with started(AppRuntime(definition)) as first:
        await first.tool_runtime.invoke("increment", {})

        async with started(AppRuntime(definition)) as second:
            assert await second.tool_runtime.invoke("read", {}) == Count(value=0)


async def test_every_invocation_receives_the_same_dependency_instance() -> None:
    async with started(AppRuntime(build_definition())) as app:
        first = await app.tool_runtime.invoke("identify", {})
        second = await app.tool_runtime.invoke("identify", {})

    assert isinstance(first, Identity)
    assert isinstance(second, Identity)
    assert first.dependency_id == second.dependency_id
    assert first.app_id == "counter-app"


async def test_a_declared_page_reaches_a_tool_through_the_runtime() -> None:
    async with started(AppRuntime(build_definition())) as app:
        await app.page_runtime.render("counter")

        assert await app.tool_runtime.invoke("read", {}) == Count(value=1)


async def test_an_unknown_tool_name_still_raises_through_the_app_runtime() -> None:
    async with started(AppRuntime(build_definition())) as app:
        with pytest.raises(ToolNotFoundError) as raised:
            await app.tool_runtime.invoke("nope", {})

    assert raised.value.tool_name == "nope"
```

The three tests that read only `definition`, `tool_registry` or `page_registry` are unchanged: those are readable without starting.

- [ ] **Step 14: Update the execution-semantics test**

In `tests/test_execution_semantics.py`:

Add the imports:

```python
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from tests.lifecycle import started
```

Add the lifespan below `Rendezvous` and change the definition:

```python
@asynccontextmanager
async def rendezvous_lifespan() -> AsyncGenerator[Rendezvous]:
    yield Rendezvous()
```

In `build_app`, replace `create_dependencies=Rendezvous,` with `lifespan=rendezvous_lifespan,`.

Update the module docstring's last paragraph, which names the factory:

```text
``lifespan`` is the App's real resource declaration, and the log is read back
through a Tool rather than by holding the resource, so the test observes
app-scoped state only through the App's public surface.
```

`overlap()` returns the App to its callers, which then read the log, so it must not stop it. Start it and leave the stopping to the tests:

```python
async def overlap() -> tuple[AppRuntime[Rendezvous], Meeting, Meeting]:
    """Invoke one started App's Tool twice concurrently and return it with both reports."""
    app = build_app()
    await app.start()

    async with asyncio.timeout(DEADLOCK_TIMEOUT_SECONDS):
        first, second = await asyncio.gather(
            app.tool_runtime.invoke("meet", {}),
            app.tool_runtime.invoke("meet", {}),
        )

    assert isinstance(first, Meeting)
    assert isinstance(second, Meeting)
    return app, first, second
```

and each of the three tests that call it ends with `await app.stop()`:

```python
async def test_two_invocations_are_in_flight_at_once() -> None:
    app, _first, _second = await overlap()

    assert await logged(app) == ARRIVALS_THEN_DEPARTURES
    await app.stop()


async def test_concurrent_invocations_receive_independent_contexts() -> None:
    app, first, second = await overlap()

    assert first.invocation_id != second.invocation_id
    await app.stop()


async def test_concurrent_invocations_share_app_scoped_dependencies() -> None:
    app, first, second = await overlap()

    assert first.dependency_id == second.dependency_id
    await app.stop()
```

The remaining three tests build their own App and use `started`:

```python
async def test_two_page_renders_are_in_flight_at_once() -> None:
    """PageRuntime's docstring claims it does not serialize renders; this holds it to that."""
    async with started(build_app()) as app:
        async with asyncio.timeout(DEADLOCK_TIMEOUT_SECONDS):
            await asyncio.gather(
                app.page_runtime.render("meeting"),
                app.page_runtime.render("meeting"),
            )

        assert await logged(app) == ARRIVALS_THEN_DEPARTURES
```

```python
async def test_two_agent_channel_calls_are_in_flight_at_once() -> None:
    async with started(build_app()) as app, Client(build_mcp_server(app)) as agent:
        async with asyncio.timeout(DEADLOCK_TIMEOUT_SECONDS):
            first, second = await asyncio.gather(
                agent.call_tool("meet", {}),
                agent.call_tool("meet", {}),
            )
        listed = await agent.call_tool("read_log", {})

    assert not first.is_error
    assert not second.is_error
    assert LogSnapshot.model_validate(listed.structured_content).entries == ARRIVALS_THEN_DEPARTURES
```

Keep that test's existing docstring unchanged.

```python
async def test_two_web_channel_interactions_are_in_flight_at_once(
    create_user: Callable[[], User],
) -> None:
    async with started(build_app()) as app:
        register_pages(app)

        first = create_user()
        second = create_user()
        await first.open("/meeting-button")
        await second.open("/meeting-button")

        first.find("Meet").click()
        second.find("Meet").click()

        await first.should_see("met")
        await second.should_see("met")

        assert await logged(app) == ARRIVALS_THEN_DEPARTURES
```

Keep that test's existing docstring unchanged.

- [ ] **Step 15: Update the dual-channel test**

In `tests/test_dual_channel.py`, add `from tests.lifecycle import started` and wrap the body:

```python
async def test_both_channels_share_one_backend_state(user: User) -> None:
    async with started(build_todo_app()) as app_under_test:
        register_pages(app_under_test)

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

- [ ] **Step 16: Update the NiceGUI adapter test**

In `tests/test_nicegui_adapter.py`, add `from tests.lifecycle import no_dependencies, started`, and in `build_web_app` replace `create_dependencies=lambda: None,` with `lifespan=no_dependencies,`.

`register_pages` reads `page_runtime`, so every test that calls it needs a started App. The six call sites become:

```python
async def test_a_page_definition_becomes_a_web_route(user: User) -> None:
    async def handler(ctx: PageContext) -> None:
        ui.label("Todos")

    async with started(
        build_web_app(
            [
                Page(
                    definition=PageDefinition(name="todos", route="/todos", title="Todos"),
                    handler=handler,
                )
            ]
        )
    ) as app_under_test:
        register_pages(app_under_test)

        assert "/todos" in registered_paths()
        await user.open("/todos")
        await user.should_see("Todos")


async def test_the_handler_receives_a_page_context(user: User) -> None:
    seen: list[PageContext] = []

    async def handler(ctx: PageContext) -> None:
        seen.append(ctx)
        ui.label("Todos")

    async with started(
        build_web_app(
            [
                Page(
                    definition=PageDefinition(name="todos", route="/todos", title="Todos"),
                    handler=handler,
                )
            ]
        )
    ) as app_under_test:
        register_pages(app_under_test)
        await user.open("/todos")

    assert len(seen) == 1
    assert callable(seen[0].tools.invoke)


async def test_a_route_that_is_not_a_path_is_rejected(user: User) -> None:
    async with started(build_web_app([page("todos", "todos")])) as app_under_test:
        with pytest.raises(PageRouteInvalidError) as error:
            register_pages(app_under_test)

    assert error.value.page_name == "todos"
    assert error.value.route == "todos"


async def test_two_pages_may_not_claim_one_route(user: User) -> None:
    pages = [page("todos", "/todos"), page("archive", "/todos")]

    async with started(build_web_app(pages)) as app_under_test:
        with pytest.raises(PageRouteConflictError) as error:
            register_pages(app_under_test)

    assert error.value.route == "/todos"
    assert {error.value.page_name, error.value.conflicting_page_name} == {"todos", "archive"}


async def test_a_rejected_registry_registers_nothing(user: User) -> None:
    pages = [page("todos", "/todos"), page("archive", "archive")]

    async with started(build_web_app(pages)) as app_under_test:
        with pytest.raises(PageRouteInvalidError):
            register_pages(app_under_test)

    assert "/todos" not in registered_paths()


async def test_page_interaction_invokes_a_tool(user: User) -> None:
    async with started(build_todo_app()) as app_under_test:
        register_pages(app_under_test)
        await user.open("/todos")
        user.find("title").type("write the spec")
        user.find("Add").click()
        await user.should_see("todo: write the spec")
```

`test_the_core_packages_do_not_import_nicegui` is unchanged.

This is the change ADR-018 records as a consequence: route validation now runs behind startup.

- [ ] **Step 17: Update the MCP adapter test**

In `tests/test_mcp_adapter.py`, add:

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from tests.lifecycle import no_dependencies, started
```

Replace `build_server` with a context manager that owns the App's running window:

```python
@asynccontextmanager
async def server_for(tools: list[Tool[None]]) -> AsyncGenerator[Server[None]]:
    """One started App with no application-scoped resource: these fixtures hold their own."""
    async with started(
        AppRuntime(
            AppDefinition(
                app_id=APP_ID,
                name="Test",
                version="0.0.0",
                lifespan=no_dependencies,
                tools=tools,
                pages=[],
            )
        )
    ) as app:
        yield build_mcp_server(app)
```

Every call site changes from

```python
    async with Client(build_server(fixture.tools())) as client:
```

to

```python
    async with server_for(fixture.tools()) as server, Client(server) as client:
```

There are ten such call sites, including the two that pass `BrokenFixture().tools()`. The three projection tests at the top of the file and `test_the_core_packages_do_not_import_mcp` do not build a server and are unchanged.

- [ ] **Step 18: Run the whole suite**

Run: `uv run pytest -q`

Expected: PASS.

- [ ] **Step 19: Lint and typecheck**

Run: `make lint typecheck`

Expected: clean. If pyright reports that `enter_async_context` returns `DepsT | None` or similar, check that `AppDefinition.lifespan` is typed `Callable[[], AbstractAsyncContextManager[DepsT]]` and not the deprecated `typing` alias.

- [ ] **Step 20: Commit**

```bash
git add src/vibepy tests
git commit -m "$(cat <<'EOF'
Give AppRuntime a lifecycle and acquire its resource from a lifespan

The resource moves out of the constructor to the start boundary the
lifecycle document places it at, so ToolRuntime and PageRuntime exist only
while the App is RUNNING and an adapter is built from a started AppRuntime.

The transition to STARTING precedes the first await, so concurrent start
calls need no lock: the second observes a state that forbids starting.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Deterministic cleanup on failure

**Files:**
- Modify: `src/vibepy/app/runtime.py`
- Test: `tests/test_app_lifecycle.py`

**Interfaces:**
- Consumes: `AppRuntime.start()`, `AppRuntime.stop()`, `AppRuntimeState` from Task 1.
- Produces: no new names. `start()` and `stop()` gain the guarantee that the runtime reaches `STOPPED` whenever they fail.

- [ ] **Step 1: Write the failing cleanup tests**

Append to `tests/test_app_lifecycle.py`, after widening the file's imports to:

```python
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from types import TracebackType
```

```python
class FailingAcquire(AbstractAsyncContextManager[None]):
    """A context manager whose acquisition raises.

    Written by hand rather than with ``@asynccontextmanager`` so that the release
    can assert it is never reached: the language reference places the acquisition
    outside the ``try`` of the ``async with`` expansion, so a failed ``__aenter__``
    never reaches ``__aexit__``. It subclasses the ABC rather than relying on a
    structural match, so the declaration type-checks regardless of how the stubs
    define it.
    """

    async def __aenter__(self) -> None:
        raise RuntimeError("the resource could not be acquired")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        raise AssertionError("release must not run when acquisition failed")


def app_with(lifespan: Callable[[], AbstractAsyncContextManager[None]]) -> AppRuntime[None]:
    return AppRuntime(
        AppDefinition(
            app_id="failing-app",
            name="Failing",
            version="0.0.0",
            lifespan=lifespan,
            tools=[],
            pages=[],
        )
    )


async def test_a_failed_acquisition_leaves_the_runtime_stopped() -> None:
    app = app_with(FailingAcquire)

    with pytest.raises(RuntimeError):
        await app.start()

    assert app.state is AppRuntimeState.STOPPED


async def test_a_failed_start_leaves_no_usable_runtime() -> None:
    app = app_with(FailingAcquire)

    with pytest.raises(RuntimeError):
        await app.start()

    with pytest.raises(AppRuntimeNotRunningError):
        _ = app.tool_runtime


async def test_an_earlier_resource_is_released_when_a_later_one_fails() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def first() -> AsyncGenerator[None]:
        events.append("first acquired")
        try:
            yield None
        finally:
            events.append("first released")

    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[None]:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(first())
            await stack.enter_async_context(FailingAcquire())
            yield None

    app = app_with(lifespan)

    with pytest.raises(RuntimeError):
        await app.start()

    assert events == ["first acquired", "first released"]
    assert app.state is AppRuntimeState.STOPPED


async def test_a_failed_release_still_reaches_stopped() -> None:
    @asynccontextmanager
    async def lifespan() -> AsyncGenerator[None]:
        yield None
        raise RuntimeError("the resource could not be released")

    app = app_with(lifespan)
    await app.start()

    with pytest.raises(RuntimeError):
        await app.stop()

    assert app.state is AppRuntimeState.STOPPED
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_app_lifecycle.py -q -k "failed or earlier"`

Expected: FAIL. The `RuntimeError` propagates, but `app.state` is `STARTING` or `STOPPING`, so the state assertions fail.

- [ ] **Step 3: Unwind on a failed start**

In `src/vibepy/app/runtime.py`, replace the acquisition line in `start()`:

```python
        try:
            dependencies = await self._stack.enter_async_context(self._definition.lifespan())
        except BaseException:
            await self._stack.aclose()
            self._state = AppRuntimeState.STOPPED
            raise
```

`BaseException` on purpose: a cancelled startup must clean up too. The stack is closed rather than ignored because a lifespan may have acquired and registered nested resources of its own before failing. Nothing is caught and swallowed — the error reaches the caller of `start()`, and `state` is accurate when it does.

- [ ] **Step 4: Reach STOPPED whatever happens on the stop path**

In `stop()`, wrap the unwinding:

```python
        try:
            await self._stack.aclose()
        finally:
            self._tool_runtime = None
            self._page_runtime = None
            self._state = AppRuntimeState.STOPPED
```

A runtime left in `STOPPING` is one a control plane can never finish cleaning up.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_app_lifecycle.py -q`

Expected: PASS.

- [ ] **Step 6: Run the whole suite, lint and typecheck**

Run: `make lint typecheck test`

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/vibepy/app/runtime.py tests/test_app_lifecycle.py
git commit -m "$(cat <<'EOF'
Reach STOPPED whenever startup or shutdown fails

A partly started runtime unwinds what it acquired and a failing shutdown
still finishes, so no runtime is left in STARTING or STOPPING for a control
plane to wait on. Errors are not swallowed: they reach the caller, and the
state is accurate when they do.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Documentation and the ADR

**Files:**
- Create: `docs/decisions/ADR-018-the-app-scoped-resource-is-an-async-context-manager.md`
- Modify: `docs/architecture/lifecycle.md`
- Modify: `docs/architecture/app-model.md`
- Modify: `docs/architecture/adapters.md`

**Interfaces:**
- Consumes: the public API from Tasks 1 and 2. No code changes.

Do not edit `docs/roadmap.md`. Do not rewrite ADR-013, ADR-015 or any other `Accepted` ADR: their decisions stand, and their Context sections record what was true when they were taken.

- [ ] **Step 1: Write ADR-018**

Create `docs/decisions/ADR-018-the-app-scoped-resource-is-an-async-context-manager.md`:

```markdown
# ADR-018: The app-scoped resource is declared as an async context manager

Status: Accepted

## Context

AppRuntime acquires an App's shared resource and must release it. It cannot close
that resource itself: `DepsT` is a type the app declared and the framework only
carries it.

The startup order in `docs/architecture/lifecycle.md` is a stack, and shutdown
pops it. Deterministic cleanup under that reading means unwinding the steps that
completed, in reverse; a step that did not complete has nothing to unwind.

The standard library already implements that discipline.
`AsyncExitStack.enter_async_context` registers a context manager's `__aexit__`
only after `__aenter__` has returned, `close()` unwinds in reverse registration
order, and the documented example releases connections already opened when a later
one fails. The semantic expansion of `async with` in the language reference places
the acquisition outside the `try`, so an acquisition that raises never reaches its
release, and an acquisition is therefore responsible for leaving nothing behind
when it fails.

Paired `on_start`/`on_stop` hooks over a plain dependency factory cannot express
this. Release has nowhere to live but `on_stop`, which makes `on_stop` the pop of
two steps at once. When the resource was acquired and `on_start` raised, `on_stop`
must not run, because its own step never completed, and must run, because nothing
else can release the resource. The resource leaks under either reading.

A third declaration beside the factory — `release_dependencies` — restores the
pairing but does not enforce it. Nothing binds the two, so an app that declares a
factory and no release type-checks. Hooks that receive the AppRuntime instead are
ruled out by ADR-013, which keeps unrestricted access to runtime internals away
from app-supplied code.

Starlette solved the same problem for ASGI applications. Its lifespan handler is
an async context manager that yields the application-scoped state, and version
1.0.0 removed the paired hooks that preceded it: "Remove `on_startup` and
`on_shutdown` parameters from `Starlette` and `Router`. Use the `lifespan`
parameter instead".

## Decision

AppDefinition declares `lifespan: Callable[[], AbstractAsyncContextManager[DepsT]]`.
What precedes the `yield` runs while the runtime is STARTING, what follows runs
while it is STOPPING. No `on_start` or `on_stop` field is introduced.

AppRuntime enters the lifespan through an AsyncExitStack at startup and closes
that stack at shutdown.

## Consequences

- acquisition and release cannot be declared apart, so an App cannot declare a
  resource it never releases
- the resource is acquired at startup rather than at construction, so ToolRuntime
  and PageRuntime exist only while the App is RUNNING and a channel adapter is
  built from a started AppRuntime; ADR-015's decision is unchanged and gains that
  ordering constraint
- route format and uniqueness validation runs behind startup, because
  `register_pages` reads the AppRuntime. Validating an App without running it
  needs a path that reads PageRegistry alone, which no milestone has required yet
- STOPPED is terminal. An unwound runtime holds no resource to re-enter, so a
  restart is a new AppRuntime, which M5A already made isolated by default
- ADR-013's decision is untouched: the resource still reaches a handler through
  ToolContext, typed by a parameter the app supplies. Only the shape of the
  declaration changes
- later startup steps, such as the in-process channel adapters ADR-017 proposes,
  are pushed onto the same stack rather than adding unwinding code of their own
- `docs/roadmap.md` names `on_start` and `on_stop` for this milestone. The
  departure was put to the owner and approved; the roadmap is not edited, and its
  acceptance criterion is met because the `yield` is the transition boundary

Sources:

- <https://github.com/python/cpython/blob/main/Doc/library/contextlib.rst>
- <https://github.com/python/cpython/blob/main/Doc/reference/compound_stmts.rst>
- <https://github.com/kludex/starlette/blob/main/docs/lifespan.md>
- <https://github.com/kludex/starlette/blob/main/docs/release-notes.md>
```

- [ ] **Step 2: Rewrite the runtime lifecycle section**

Replace everything in `docs/architecture/lifecycle.md` from `## Runtime lifecycle` down to the line before `## Package lifecycle`:

```markdown
## Runtime lifecycle

Runtime lifecycle is distinct from package installation lifecycle.

AppRuntime states:

```text
CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED
```

STOPPED is terminal. An unwound runtime holds no resource to re-enter, so a restart
is a new AppRuntime.

`AppRuntime.state` reports the current state. `start()` and `stop()` are the only
transitions, and a transition the current state forbids raises rather than being
ignored. The move into STARTING and STOPPING precedes the first await, so
concurrent calls need no lock: the second caller observes a state that forbids the
transition.

The framework owns state transition validation and cleanup behavior.

## The lifespan

An App declares its application-scoped resource as a factory returning an async
context manager. What precedes the `yield` runs while the runtime is STARTING;
what follows runs while it is STOPPING. `docs/architecture/app-model.md` carries
the field.

There are no separate start and stop hooks. Binding acquisition to release is what
lets the framework release a resource whose type it does not know. See
`docs/decisions/ADR-018-the-app-scoped-resource-is-an-async-context-manager.md`.

## Startup

1. validate the state transition
2. enter the lifespan and build the runtimes over what it yields
3. enter RUNNING

Channel adapters are not started. `docs/architecture/adapters.md` describes what
each adapter does instead, and whether an App's own process serves its channels is
open in
`docs/decisions/ADR-017-one-process-serves-both-channels.md`.

## Shutdown

1. validate the state transition
2. unwind what startup acquired, in reverse
3. enter STOPPED

## Cleanup

Startup is a stack and shutdown pops it. Cleanup unwinds the steps that completed,
in reverse; a step that did not complete has nothing to unwind. An acquisition
that fails is responsible for leaving nothing behind, which is the contract
`async with` already places on `__aenter__`.

| Failure | Unwound | Final state |
| --- | --- | --- |
| entering the lifespan raises | nothing was acquired | STOPPED |
| a resource inside the lifespan fails after an earlier one was acquired | the lifespan releases the earlier one | STOPPED |
| the lifespan raises on exit | nothing further is owned | STOPPED |

The error reaches the caller of `start()` or `stop()` in every row. The framework
does not swallow it, and `state` is accurate when the caller sees it. A runtime
left in STARTING or STOPPING is one a control plane could never finish cleaning up.
```

- [ ] **Step 3: Update the App model document**

In `docs/architecture/app-model.md`:

Replace the `AppDefinition` code block's `create_dependencies` line with `lifespan: Callable[[], AbstractAsyncContextManager[DepsT]]`, and replace the paragraph beginning "`create_dependencies` is a factory, not a resource." with:

```markdown
`lifespan` is a factory returning an async context manager, not a live one. A
definition holding a live resource would not be a declaration, and one definition
would yield runtimes that shared state. What precedes the `yield` runs at startup
and what follows runs at shutdown; `docs/architecture/lifecycle.md` owns those
boundaries.
```

In the sentence about an App with no resource, change "with a factory returning `None`" to "with a lifespan yielding `None`".

Replace the line "A future version may add an optional config model (M8) and optional lifecycle hooks (M6)." with "A future version may add an optional config model (M8)."

In the `AppRuntime` section, replace the paragraph beginning "The constructor calls `create_dependencies()` once" with:

```markdown
The constructor fills a ToolRegistry and a PageRegistry from the declarations and
nothing else; it acquires no resource. `start()` enters the lifespan and builds a
ToolRuntime and a PageRuntime over the value it yields. Two AppRuntimes built from
one AppDefinition are isolated by default: each enters its own lifespan.
```

Add `start`, `stop` and `state` to the code block:

```python
class AppRuntime[DepsT]:
    def __init__(self, definition: AppDefinition[DepsT]) -> None: ...

    @property
    def state(self) -> AppRuntimeState: ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

In the owned-state list, replace "lifecycle state, when M6 introduces it" with "lifecycle state".

Replace the paragraph about which properties an adapter consumes with:

```markdown
`definition`, `tool_registry` and `page_registry` are readable at any time: they
are built from declarations. `tool_runtime` and `page_runtime` exist only while the
App is RUNNING, because they are built over the resource, and reaching them outside
that window raises. The resource itself is not exposed: a Tool handler receives it
through its ToolContext, and nothing else needs it.
```

Delete the paragraph beginning "The resource is created in the constructor." — `docs/architecture/lifecycle.md` now owns that fact.

- [ ] **Step 4: Update the adapter document**

In `docs/architecture/adapters.md`, add one line to the `## Principle` section, after the existing sentence:

```markdown
An adapter reads the runtimes an App produced at startup, so it is built from a
started AppRuntime.
```

State it once. Do not repeat it in the MCP and NiceGUI sections.

- [ ] **Step 5: Verify the documents agree with the code**

Run: `grep -rn "create_dependencies\|on_start\|on_stop" docs src tests`

Expected: matches only in `docs/roadmap.md` (never edited), in `docs/milestones/M6/`, and in ADR-018's Context, where they are quoted as the alternative that was rejected. No match in `src` or `tests`.

- [ ] **Step 6: Run the full check**

Run: `make lint typecheck test`

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add docs/architecture docs/decisions
git commit -m "$(cat <<'EOF'
Document the runtime lifecycle and record the lifespan decision

The lifecycle document owns the states, the lifespan boundary and the
unwinding rule. ADR-018 records why paired start and stop hooks cannot
express deterministic cleanup over a resource whose type the framework does
not know.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Integration

When the three tasks are green, the milestone is ready to merge. Per AGENTS.md, promote what is still true out of `docs/milestones/M6/` and delete the folder, then merge the branch into `main` with `--no-ff`. Do not push until the owner asks.
