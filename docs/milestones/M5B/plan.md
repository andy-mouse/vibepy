# M5B Execution Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn ADR-005's async-first concurrency decision into a tested contract at every layer this framework owns, and record in `docs/architecture/runtime.md` which layer owns which part of concurrency.

**Architecture:** No production code changes. One fixture App proves overlap at four layers: `ToolRuntime` directly, `PageRuntime`, the Agent channel through the MCP SDK, and the Web channel through NiceGUI. The mechanism is an `asyncio.Barrier(2)` held in the App's application-scoped resource and reached through `ToolContext.dependencies`, so overlap and dependency sharing are proven by the same event and no assertion depends on wall-clock duration.

**Tech Stack:** Python 3.12, pytest with `pytest-asyncio` in auto mode, pydantic v2, `asyncio.Barrier`, `asyncio.timeout`, the MCP SDK's in-process `Client`, NiceGUI's `create_user` fixture.

## Global Constraints

- `pyproject.toml` is the only project config. Do not add `setup.py` or `requirements.txt`.
- `requires-python = ">=3.12"`. `asyncio.Barrier` (3.11+) and `asyncio.timeout` (3.11+) are available.
- ruff `line-length = 100`, lint rules `["E", "F", "I", "UP", "B", "ASYNC", "RUF"]`. Import groups: stdlib, third party (`mcp`, `nicegui`, `pydantic`), then `vibepy`.
- pyright `typeCheckingMode = "strict"` over `src` and `tests`.
- `Any` and `cast` are not acceptable. Narrow with `isinstance` or `model_validate`, as the existing tests do.
- pytest `asyncio_mode = "auto"`. An `async def test_*` needs no decorator.
- Tests verify public contracts, not internals.
- Standard `logging` only. No `print`.
- A change is done when `make lint typecheck test` passes.
- `docs/roadmap.md` is never edited.
- **Drive an external library only the way that library documents.** Do not add a test-only gate, patch, sleep or completion flag that stands in for a mechanism the library already provides. If a documented mechanism seems not to work, stop and report rather than working around it.
- No seam is added to `src/` for a test's benefit, and no test holds an App's application-scoped resource directly. Observe app-scoped state through a Tool, the way `tests/test_app_runtime.py` observes `id(ctx.dependencies)` through its `identify` Tool.
- Do not implement ahead of M5B. Timeouts, cancellation, sync handler support and fan-out helpers are out of scope; see `docs/milestones/M5B/spec.md`.
- Every task appends to one test file and reuses its fixture. Do not duplicate the fixture.

## File Structure

| File | Responsibility |
| --- | --- |
| `tests/test_execution_semantics.py` (create in Task 1, extend in Tasks 2 to 4) | The execution-semantics contract at every layer the framework owns. Constitutional, like `tests/test_dual_channel.py`. |
| `docs/architecture/runtime.md` (modify in Task 5) | Current truth for runtime execution. Gains concurrency ownership per layer, the cited behaviour of both channel technologies, and the contract the tests guarantee. |
| `docs/milestones/M5B/` (delete in Task 6) | Retired on integration per AGENTS.md. |

No file under `src/` changes. `ToolRuntime.invoke` already holds no lock and already builds a
fresh `ToolContext` per invocation over one shared `dependencies`; `PageRuntime.render` holds
no per-render state; both adapters reduce a request to a single `await`.

## Verified before planning

Every fact below was confirmed against the installed version and the library's official
documentation, and the whole test file was run green before this plan was written. Ruff and
pyright are clean on it.

- The MCP SDK awaits *inline methods* in the read loop before dequeuing the next message and
  spawns every other request into a task group. Only `initialize` is inline, so `tools/call`
  is spawned. <https://py.sdk.modelcontextprotocol.io/v2/api/mcp/shared/jsonrpc_dispatcher>,
  <https://py.sdk.modelcontextprotocol.io/v2/api/mcp/server/runner>
- `Client` accepts a `Server` instance directly for an in-process connection; the SDK
  documents this as its in-memory transport and names it the testing path.
  <https://py.sdk.modelcontextprotocol.io/v2/client/transports>,
  <https://py.sdk.modelcontextprotocol.io/v2/api/mcp/client/client>
- NiceGUI runs one shared asyncio event loop, and blocking it freezes the app for every
  user. <https://github.com/zauberzeug/nicegui/blob/main/nicegui/llms.md>,
  <https://github.com/zauberzeug/nicegui/wiki/FAQs>
- `nicegui.events.handle_event`: "If the handler returns an awaitable, it is scheduled as a
  background task." So a click returns before its async handler finishes.
  <https://github.com/zauberzeug/nicegui/blob/main/nicegui/events.py>
- NiceGUI documents the `create_user` factory fixture for simultaneous users — "the `User`
  instances are independent from each other and can interact with the UI in parallel" — with
  the shape `create_user()`, `await user.open(...)`, `user.find(...)` plus an interaction,
  `await user.should_see(...)`. <https://nicegui.io/documentation/user>
- Against `mcp==2.1.1` and `nicegui==3.16.0`, all six tests in this plan pass and produce the
  log `['arrived', 'arrived', 'departed', 'departed']`.

---

### Task 1: The ToolRuntime execution-semantics contract

**Files:**
- Create: `tests/test_execution_semantics.py`
- Temporarily modify, then revert: `src/vibepy/tool/runtime.py`

**Interfaces:**
- Consumes: `AppDefinition(app_id, name, version, create_dependencies, tools, pages)` and `AppRuntime(definition)` from `vibepy.app`; `Tool(definition=..., handler=...)`, `ToolDefinition(name, description, input_model, output_model)` and `ToolContext[DepsT]` with fields `app_id`, `invocation_id`, `dependencies` from `vibepy.tool`; `AppRuntime.tool_runtime.invoke(name, raw_input) -> Awaitable[BaseModel]`.
- Produces, for Tasks 2 to 4: `PARTIES: int`, `DEADLOCK_TIMEOUT_SECONDS: int`, `ARRIVALS_THEN_DEPARTURES: list[str]`, `EmptyInput`, `Meeting(invocation_id: str, dependency_id: int)`, `LogSnapshot(entries: list[str])`, `Rendezvous` with attributes `barrier` and `log`, the handlers `meet` and `read_log`, the Tool constants `MEET` and `READ_LOG`, `build_app() -> AppRuntime[Rendezvous]`, `logged(app) -> list[str]`, and `overlap() -> tuple[AppRuntime[Rendezvous], Meeting, Meeting]`.

- [ ] **Step 1: Write the test file**

Create `tests/test_execution_semantics.py` with exactly this content:

```python
"""The execution-semantics contract from docs/architecture/runtime.md.

Two invocations of one App overlap, each with its own ToolContext, over one
application-scoped resource. This test is constitutional: it stays for the life
of the project.

The proof is a barrier rather than a duration. An ``asyncio.Barrier(2)`` opens
only once two waiters are inside it, and it is reached through
``ctx.dependencies``, so it opens only if the two invocations overlap and also
received the same resource. The handler logs on both sides of the barrier, so
overlap is asserted as an order of events rather than as the absence of a
failure. A passing run asserts nothing about elapsed time; ``asyncio.timeout``
exists only to turn the deadlock of a serialized runtime into a failure.

``create_dependencies`` is the real factory, and the log is read back through a
Tool rather than by holding the resource, so the test observes app-scoped state
only through the App's public surface. ``tests/test_app_runtime.py`` observes
``id(ctx.dependencies)`` the same way.
"""

import asyncio

from pydantic import BaseModel

from vibepy.app import AppDefinition, AppRuntime
from vibepy.tool import Tool, ToolContext, ToolDefinition

PARTIES = 2
DEADLOCK_TIMEOUT_SECONDS = 5
ARRIVALS_THEN_DEPARTURES = ["arrived", "arrived", "departed", "departed"]


class EmptyInput(BaseModel):
    pass


class Meeting(BaseModel):
    """What one invocation reports about itself once the barrier opens."""

    invocation_id: str
    dependency_id: int


class LogSnapshot(BaseModel):
    entries: list[str]


class Rendezvous:
    """The app's application-scoped resource: one barrier and one arrival log."""

    def __init__(self) -> None:
        self.barrier = asyncio.Barrier(PARTIES)
        self.log: list[str] = []


async def meet(ctx: ToolContext[Rendezvous], _payload: EmptyInput) -> Meeting:
    """Return only once a second invocation is inside the same barrier."""
    ctx.dependencies.log.append("arrived")
    await ctx.dependencies.barrier.wait()
    ctx.dependencies.log.append("departed")
    return Meeting(invocation_id=ctx.invocation_id, dependency_id=id(ctx.dependencies))


async def read_log(ctx: ToolContext[Rendezvous], _payload: EmptyInput) -> LogSnapshot:
    return LogSnapshot(entries=list(ctx.dependencies.log))


MEET = Tool(
    definition=ToolDefinition(
        name="meet",
        description="Wait for a concurrent invocation, then report this one's identity",
        input_model=EmptyInput,
        output_model=Meeting,
    ),
    handler=meet,
)

READ_LOG = Tool(
    definition=ToolDefinition(
        name="read_log",
        description="Report the arrival and departure log",
        input_model=EmptyInput,
        output_model=LogSnapshot,
    ),
    handler=read_log,
)


def build_app() -> AppRuntime[Rendezvous]:
    return AppRuntime(
        AppDefinition(
            app_id="rendezvous-app",
            name="Rendezvous",
            version="0.0.0",
            create_dependencies=Rendezvous,
            tools=[MEET, READ_LOG],
            pages=[],
        )
    )


async def logged(app: AppRuntime[Rendezvous]) -> list[str]:
    snapshot = await app.tool_runtime.invoke("read_log", {})
    assert isinstance(snapshot, LogSnapshot)
    return snapshot.entries


async def overlap() -> tuple[AppRuntime[Rendezvous], Meeting, Meeting]:
    """Invoke one App's Tool twice concurrently and return the App and both reports."""
    app = build_app()

    async with asyncio.timeout(DEADLOCK_TIMEOUT_SECONDS):
        first, second = await asyncio.gather(
            app.tool_runtime.invoke("meet", {}),
            app.tool_runtime.invoke("meet", {}),
        )

    assert isinstance(first, Meeting)
    assert isinstance(second, Meeting)
    return app, first, second


async def test_two_invocations_are_in_flight_at_once() -> None:
    app, _first, _second = await overlap()

    assert await logged(app) == ARRIVALS_THEN_DEPARTURES


async def test_concurrent_invocations_receive_independent_contexts() -> None:
    _app, first, second = await overlap()

    assert first.invocation_id != second.invocation_id


async def test_concurrent_invocations_share_app_scoped_dependencies() -> None:
    _app, first, second = await overlap()

    assert first.dependency_id == second.dependency_id
```

- [ ] **Step 2: Run the tests and expect them to pass on the first run**

Run: `uv run pytest tests/test_execution_semantics.py -v`

Expected: 3 passed.

This is the milestone's finding, not a mistake. `ToolRuntime.invoke` already satisfies all
three acceptance criteria, so there is no red phase to reach by writing production code. A
test that has never failed proves nothing, so the next three steps make each assertion fail
on purpose.

- [ ] **Step 3: Negative control A — prove the tests detect serialization**

Edit `src/vibepy/tool/runtime.py`. Add `import asyncio` to the import block, then give
`ToolRuntime` a global lock:

```python
    def __init__(
        self, *, app_id: str, registry: "ToolRegistry[DepsT]", dependencies: DepsT
    ) -> None:
        self._app_id = app_id
        self._registry = registry
        self._dependencies = dependencies
        self._lock = asyncio.Lock()

    async def invoke(self, name: str, raw_input: Mapping[str, object]) -> BaseModel:
        async with self._lock:
            tool = self._registry.resolve(name)
            ctx = ToolContext(
                app_id=self._app_id,
                invocation_id=str(uuid4()),
                dependencies=self._dependencies,
            )
            return await tool.bound(ctx, raw_input)
```

Run: `uv run pytest tests/test_execution_semantics.py -v`

Expected: all 3 tests FAIL with `TimeoutError` after about 5 seconds each. The first
invocation holds the lock while waiting for a second waiter the lock will never admit.

Revert:

```bash
git checkout src/vibepy/tool/runtime.py
```

- [ ] **Step 4: Negative control B — prove the independence test detects a reused context**

Edit `src/vibepy/tool/runtime.py` and replace `invocation_id=str(uuid4())` with a constant:

```python
            invocation_id="fixed",
```

Run: `uv run pytest tests/test_execution_semantics.py -v`

Expected: `test_concurrent_invocations_receive_independent_contexts` FAILS on
`'fixed' != 'fixed'`. The other two tests still pass, which is what makes this a control
rather than a broad break.

Revert:

```bash
git checkout src/vibepy/tool/runtime.py
```

- [ ] **Step 5: Negative control C — prove the barrier depends on a shared resource**

This control edits the test, not the runtime, because no small change to `ToolRuntime`
produces a per-invocation resource. In `tests/test_execution_semantics.py`, inside
`overlap()`, add a second App:

```python
    app = build_app()
    other = build_app()
```

and change the second invocation inside the `gather` call from:

```python
            app.tool_runtime.invoke("meet", {}),
```

to:

```python
            other.tool_runtime.invoke("meet", {}),
```

Run: `uv run pytest tests/test_execution_semantics.py -v`

Expected: all 3 tests FAIL with `TimeoutError`. Two invocations that do not share a resource
do not share its barrier, so it never opens. This is what makes the barrier a proof of
sharing and not only of overlap.

Restore by hand — the file is untracked, so `git checkout` cannot help. Delete the
`other = build_app()` line and change `other.tool_runtime.invoke("meet", {}),` back to
`app.tool_runtime.invoke("meet", {}),`, leaving two identical lines inside `gather`.

- [ ] **Step 6: Confirm the working tree holds only the new test**

Run: `git status --short`

Expected: exactly one line, `?? tests/test_execution_semantics.py`. If
`src/vibepy/tool/runtime.py` appears, a revert was missed; run
`git checkout src/vibepy/tool/runtime.py`.

Run: `grep -c "app.tool_runtime.invoke" tests/test_execution_semantics.py`

Expected: `3` — two inside `gather`, one inside `logged`. A `2` means Control C's edit is
still in place.

- [ ] **Step 7: Run the full verification**

Run: `make lint typecheck test`

Expected: ruff clean, pyright clean, every test passes including the 3 new ones and all
pre-existing tests unchanged.

- [ ] **Step 8: Commit**

```bash
git add tests/test_execution_semantics.py
git commit -m "Prove two Tool invocations of one App overlap

ToolRuntime already held no lock and already built a fresh ToolContext per
invocation over one shared resource, so this adds no production code. The
contract was asserted in ADR-005 and untested; now a test holds it.

The proof is an asyncio.Barrier(2) reached through ToolContext.dependencies. It
opens only when two invocations are inside it, so overlap and dependency
sharing are proven by one event, and the handler logs on both sides so overlap
is an order of events rather than an absence of failure. A passing run asserts
nothing about elapsed time; asyncio.timeout only turns a serialized runtime's
deadlock into a failure.

The fixture uses the real dependency factory and reads the log back through a
read_log Tool, so the test never holds the App's resource and src/ gains no
seam. test_app_runtime.py observes id(ctx.dependencies) the same way.

Verified against three deliberate breaks: a global lock times all three tests
out, a constant invocation id fails only the independence test, and two Apps
with separate resources never open the barrier at all."
```

---

### Task 2: Prove PageRuntime does not serialize renders

`src/vibepy/page/runtime.py` states "Holds no per-Page state and does not serialize
renders." That claim has been untested since M2.

**Files:**
- Modify: `tests/test_execution_semantics.py`
- Temporarily modify, then revert: `src/vibepy/page/runtime.py`

**Interfaces:**
- Consumes from Task 1: `build_app()`, `logged()`, `ARRIVALS_THEN_DEPARTURES`, `DEADLOCK_TIMEOUT_SECONDS`.
- Consumes from the framework: `Page(definition=..., handler=...)`, `PageDefinition(name, route, title)` and `PageContext` with attribute `tools` from `vibepy.page`; `AppRuntime.page_runtime.render(name) -> Awaitable[None]`.
- Produces, for Task 4: the `pages=[...]` list inside `build_app`, which Task 4 appends a second Page to.

- [ ] **Step 1: Add the import**

In `tests/test_execution_semantics.py`, add to the `vibepy` import group, before the
`vibepy.tool` line:

```python
from vibepy.page import Page, PageContext, PageDefinition
```

- [ ] **Step 2: Add the Page handler**

Add after the `READ_LOG` constant:

```python
async def meeting_page(ctx: PageContext) -> None:
    """The render path: a Page reaches the Tool through ToolInvoker."""
    await ctx.tools.invoke("meet", {})
```

- [ ] **Step 3: Declare the Page**

In `build_app`, replace:

```python
            pages=[],
```

with:

```python
            pages=[
                Page(
                    definition=PageDefinition(name="meeting", route="/meeting", title="Meeting"),
                    handler=meeting_page,
                ),
            ],
```

- [ ] **Step 4: Append the test**

Add at the end of the file:

```python
async def test_two_page_renders_are_in_flight_at_once() -> None:
    """PageRuntime's docstring claims it does not serialize renders; this holds it to that."""
    app = build_app()

    async with asyncio.timeout(DEADLOCK_TIMEOUT_SECONDS):
        await asyncio.gather(
            app.page_runtime.render("meeting"),
            app.page_runtime.render("meeting"),
        )

    assert await logged(app) == ARRIVALS_THEN_DEPARTURES
```

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/test_execution_semantics.py::test_two_page_renders_are_in_flight_at_once -v`

Expected: PASS.

- [ ] **Step 6: Negative control — prove the test detects a serialized PageRuntime**

Edit `src/vibepy/page/runtime.py`. Add `import asyncio` to the import block, then give
`PageRuntime` a lock:

```python
    def __init__(self, *, registry: PageRegistry, tools: ToolInvoker) -> None:
        self._registry = registry
        self._tools = tools
        self._lock = asyncio.Lock()

    async def render(self, name: str) -> None:
        async with self._lock:
            page = self._registry.resolve(name)
            ctx = PageContext(tools=self._tools)
            await page.handler(ctx)
```

Run: `uv run pytest tests/test_execution_semantics.py -v`

Expected: `test_two_page_renders_are_in_flight_at_once` FAILS with `TimeoutError`. The other
3 tests still pass, because none of them goes through PageRuntime. That contrast is what
makes this a control for PageRuntime specifically.

Revert:

```bash
git checkout src/vibepy/page/runtime.py
```

- [ ] **Step 7: Run the full verification**

Run: `make lint typecheck test`

Expected: ruff clean, pyright clean, all tests pass — 4 in this file.

- [ ] **Step 8: Commit**

```bash
git add tests/test_execution_semantics.py
git commit -m "Hold PageRuntime to its claim that it does not serialize renders

The docstring has said so since M2 with nothing checking it. Two concurrent
renders now reach one barrier through PageContext and ToolInvoker, and a lock in
PageRuntime.render fails this test while leaving the other three passing."
```

---

### Task 3: Prove the Agent channel does not serialize

This task exists because `pyproject.toml` pins only `mcp>=2.1`. The SDK spawns every request
except `initialize`, which is what makes the Agent channel concurrent, and an upgrade can
change that with nothing failing. The test drives the composition an agent actually
reaches — the adapter on top of the SDK — not the SDK alone.

**Files:**
- Modify: `tests/test_execution_semantics.py`
- Temporarily modify, then revert: `src/vibepy/tool/runtime.py`

**Interfaces:**
- Consumes from Task 1: `build_app()`, `LogSnapshot`, `ARRIVALS_THEN_DEPARTURES`, `DEADLOCK_TIMEOUT_SECONDS`.
- Consumes from the framework: `build_mcp_server[DepsT](app: AppRuntime[DepsT]) -> Server[None]` from `vibepy.adapters.mcp`.
- Consumes from the SDK, per its documented in-memory transport: `Client` from `mcp.client`, used as `async with Client(server) as agent:` with `await agent.call_tool(name, arguments)`, exactly as `tests/test_dual_channel.py` already does.
- Produces: nothing later tasks rely on.

- [ ] **Step 1: Add the imports**

In `tests/test_execution_semantics.py`, add to the third-party group, before `pydantic`:

```python
from mcp.client import Client
```

and to the `vibepy` group, before `vibepy.app`:

```python
from vibepy.adapters.mcp import build_mcp_server
```

- [ ] **Step 2: Append the test**

Add at the end of the file:

```python
async def test_two_agent_channel_calls_are_in_flight_at_once() -> None:
    """The Agent channel's request concurrency is the SDK's, and this pins it.

    ``pyproject.toml`` pins only ``mcp>=2.1``. The SDK awaits inline methods in
    its read loop and spawns everything else, with only ``initialize`` inline,
    so two ``tools/call`` requests on one session overlap. An upgrade that made
    them inline would leave this framework's concurrency guarantee delivering
    nothing to an agent, and would fail here rather than silently.

    Passing a Server straight to Client is the SDK's documented in-memory
    transport, which it names as the testing path.
    """
    app = build_app()

    async with Client(build_mcp_server(app)) as agent:
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

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/test_execution_semantics.py::test_two_agent_channel_calls_are_in_flight_at_once -v`

Expected: PASS.

If it fails with `TimeoutError`, stop. That means the installed MCP SDK serializes
`tools/call`, so the premise of this task and of Task 5's table is false. The correct
response is to report it and correct `docs/architecture/runtime.md` — not to weaken the test
or work around the SDK. Record the version with
`uv run python -c "import importlib.metadata as m; print(m.version('mcp'))"` and raise it
with the owner.

- [ ] **Step 4: Negative control — prove the test reaches through the adapter**

Edit `src/vibepy/tool/runtime.py` and apply the same global lock as Task 1 Step 3: add
`import asyncio`, add `self._lock = asyncio.Lock()` to `__init__`, and wrap the body of
`invoke` in `async with self._lock:`.

Run: `uv run pytest tests/test_execution_semantics.py -v`

Expected: all 5 tests FAIL with `TimeoutError`, the Agent-channel one included. That shows
the Agent-channel test reaches through the adapter to the runtime rather than only
exercising the SDK.

Revert:

```bash
git checkout src/vibepy/tool/runtime.py
```

- [ ] **Step 5: Run the full verification**

Run: `make lint typecheck test`

Expected: ruff clean (import order included), pyright clean, all tests pass — 5 in this file.

- [ ] **Step 6: Commit**

```bash
git add tests/test_execution_semantics.py
git commit -m "Pin the Agent channel's concurrency to the barrier

The framework's claim that two invocations may overlap reaches an agent only if
the MCP SDK spawns tools/call rather than awaiting it in its read loop. The SDK
does spawn it - only initialize is inline - but pyproject.toml pins mcp>=2.1, so
an upgrade could remove that with no test noticing.

This is not a test of the SDK. It drives the composition an agent reaches, the
adapter on top of the SDK, through the SDK's own documented in-memory transport.
A global lock in ToolRuntime fails it, which is how we know it reaches through
the adapter rather than stopping at it.

Sources:
https://py.sdk.modelcontextprotocol.io/v2/api/mcp/shared/jsonrpc_dispatcher
https://py.sdk.modelcontextprotocol.io/v2/api/mcp/server/runner
https://py.sdk.modelcontextprotocol.io/v2/client/transports"
```

---

### Task 4: Prove the Web channel does not serialize

Same reason as Task 3, for the other channel: `pyproject.toml` pins only `nicegui>=3.16`,
and the Web channel is concurrent because NiceGUI dispatches an async event handler as a
background task.

The test follows NiceGUI's documented multi-user shape and uses its own waiting mechanism.
`should_see` retries until the UI reflects the finished handler and raises `AssertionError`
if it never does, so this test needs no `asyncio.timeout` and no completion flag of its own.
Do not add one.

**Files:**
- Modify: `tests/test_execution_semantics.py`
- Temporarily modify, then revert: `src/vibepy/tool/runtime.py`

**Interfaces:**
- Consumes from Task 1: `build_app()`, `logged()`, `ARRIVALS_THEN_DEPARTURES`.
- Consumes from Task 2: the `pages=[...]` list inside `build_app`.
- Consumes from the framework: `register_pages[DepsT](app: AppRuntime[DepsT]) -> None` from `vibepy.adapters.nicegui`.
- Consumes from NiceGUI, per <https://nicegui.io/documentation/user>: the `create_user` fixture typed `Callable[[], User]`, then `await user.open(route)`, `user.find(target).click()`, `await user.should_see(text)`. `tests/conftest.py` already loads `nicegui.testing.user_plugin`, which provides both `user` and `create_user`.
- Produces: nothing later tasks rely on.

- [ ] **Step 1: Add the imports**

In `tests/test_execution_semantics.py`, add to the stdlib group:

```python
from collections.abc import Callable
```

to the third-party group, after `mcp.client` and before `pydantic`:

```python
from nicegui import ui
from nicegui.testing import User
```

and to the `vibepy` group, after `vibepy.adapters.mcp`:

```python
from vibepy.adapters.nicegui import register_pages
```

- [ ] **Step 2: Add the second Page handler**

Add after `meeting_page`:

```python
async def meeting_button_page(ctx: PageContext) -> None:
    """The interaction path: a click invokes the Tool, then the label reflects it.

    The label is what ``should_see`` waits on. NiceGUI dispatches an async event
    handler as a background task, so the click returns before the invocation
    finishes, and the UI is the documented place to observe that it did.
    """
    status = ui.label("waiting")

    async def meet_now() -> None:
        await ctx.tools.invoke("meet", {})
        status.set_text("met")

    ui.button("Meet", on_click=meet_now)
```

- [ ] **Step 3: Declare the Page**

In `build_app`, extend the `pages` list with a second entry, so it reads:

```python
            pages=[
                Page(
                    definition=PageDefinition(name="meeting", route="/meeting", title="Meeting"),
                    handler=meeting_page,
                ),
                Page(
                    definition=PageDefinition(
                        name="meeting_button", route="/meeting-button", title="Meeting"
                    ),
                    handler=meeting_button_page,
                ),
            ],
```

Two Pages rather than one, because `meeting_page` invokes the Tool during render: a single
Page carrying both paths would send the Web test's first `open` into the barrier alone.

- [ ] **Step 4: Append the test**

Add at the end of the file:

```python
async def test_two_web_channel_interactions_are_in_flight_at_once(
    create_user: Callable[[], User],
) -> None:
    """The Web channel's request concurrency is NiceGUI's, and this pins it.

    ``pyproject.toml`` pins only ``nicegui>=3.16``. NiceGUI dispatches an async
    event handler as a background task, so a click does not hold the
    interaction and two of them overlap. The shape here is NiceGUI's documented
    one for simultaneous users: ``create_user()``, ``open``, ``find`` with an
    interaction, then ``should_see``.

    ``should_see`` is also the wait. It retries until the label changes and
    fails if it never does, so nothing in the fixture waits on the invocation.
    """
    app = build_app()
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

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/test_execution_semantics.py::test_two_web_channel_interactions_are_in_flight_at_once -v`

Expected: PASS.

If `should_see` fails, stop and report. Do not add a sleep, a retry count, or a completion
flag to make it pass: a failure here means either NiceGUI no longer dispatches handlers as
background tasks, or something in this framework serializes the Web channel, and both are
findings rather than obstacles.

- [ ] **Step 6: Negative control — prove the test detects serialization below the adapter**

Edit `src/vibepy/tool/runtime.py` and apply the same global lock as Task 1 Step 3.

Run: `uv run pytest tests/test_execution_semantics.py -v`

Expected: all 6 tests FAIL. The Web-channel one fails with an `AssertionError` from
`should_see` rather than a `TimeoutError`, because the barrier never opens, so the label
never changes. That difference is expected: `should_see` is the bound on this test.

Revert:

```bash
git checkout src/vibepy/tool/runtime.py
```

- [ ] **Step 7: Confirm the working tree holds only the test change**

Run: `git status --short`

Expected: one line, ` M tests/test_execution_semantics.py`.

- [ ] **Step 8: Run the full verification**

Run: `make lint typecheck test`

Expected: ruff clean, pyright clean, all tests pass — 6 in this file.

- [ ] **Step 9: Commit**

```bash
git commit -am "Pin the Web channel's concurrency to the barrier

The Web channel is concurrent because NiceGUI dispatches an async event handler
as a background task, so a click does not hold the interaction. pyproject.toml
pins only nicegui>=3.16, so an upgrade could remove that with no test noticing.

Follows NiceGUI's documented shape for simultaneous users - create_user, open,
find with an interaction, should_see - and uses should_see as the wait rather
than a completion flag in the fixture. A global lock in ToolRuntime fails this
test through should_see, since the barrier never opens and the label never
changes.

The App declares two Pages because the render path invokes the Tool during
render; one Page carrying both paths would send the first open into the barrier
alone.

Source: https://nicegui.io/documentation/user"
```

---

### Task 5: Record where concurrency is owned

**Files:**
- Modify: `docs/architecture/runtime.md:72-83` (the `## Concurrency` section)

**Interfaces:**
- Consumes: `tests/test_execution_semantics.py` from Tasks 1 to 4, referenced by path.
- Produces: nothing later tasks rely on.

- [ ] **Step 1: Read the section as it stands**

Run: `sed -n '68,90p' docs/architecture/runtime.md`

Expected: the `## Concurrency` section, then `## Dual-channel contract`.

- [ ] **Step 2: Replace the Concurrency section**

Replace everything from the line `## Concurrency` up to but not including the line
`## Dual-channel contract` with:

````markdown
## Concurrency

Tool handlers are async-first.

ToolRuntime permits concurrent invocations by default.

ToolRuntime must not serialize all calls with a global lock.

Each invocation receives an independent ToolContext while sharing application-scoped
dependencies from AppRuntime.

### Where concurrency is owned

| Layer | Question | Owner |
| --- | --- | --- |
| Channel transport | may two requests be in flight at once? | MCP SDK, uvicorn |
| Framework | may two invocations be in flight at once? | ToolRuntime, PageRuntime |
| Domain | is overlapping mutation correct? | the app's own services and storage |

Only the middle row is a framework contract. The framework guarantees the absence of
serialization it introduces itself. It cannot create request concurrency that its channel
technology does not offer, and it does not make an app's domain state safe under overlap.

A channel adapter reduces a request to a single `await` on a runtime, so it adds no
serialization of its own. See `docs/decisions/ADR-003-channel-adapters-are-thin.md`.

### What the channel technologies do

The MCP SDK awaits *inline methods* in its read loop before dequeuing the next message and
spawns every other request into a task group. Only `initialize` is inline, so `tools/call`
requests on one session overlap.

NiceGUI runs on a single shared asyncio event loop and dispatches an async event handler as
a background task, so an interaction does not hold the request that triggered it and two
interactions overlap. Blocking that loop freezes the application for every user, so blocking
I/O belongs in `run.io_bound` and CPU work in `run.cpu_bound`.

`pyproject.toml` carries only a lower bound on each library, so both behaviours are
assumptions a version upgrade can break. They are held by tests rather than by this section.

Concurrency in this framework is therefore cooperative. Overlap happens at `await` points,
which has one consequence an app author must know: a Tool handler that blocks the event loop
serializes every channel in its process, and that is exactly the case where ToolRuntime's
absence of a lock delivers nothing. Wrap blocking calls in `asyncio.to_thread`.

Sources:

- <https://py.sdk.modelcontextprotocol.io/v2/api/mcp/shared/jsonrpc_dispatcher>
- <https://py.sdk.modelcontextprotocol.io/v2/api/mcp/server/runner>
- <https://github.com/zauberzeug/nicegui/blob/main/nicegui/events.py>
- <https://github.com/zauberzeug/nicegui/blob/main/nicegui/llms.md>
- <https://github.com/zauberzeug/nicegui/wiki/FAQs>

### The execution-semantics contract

The framework must maintain a constitutional integration test proving that two invocations
of one App overlap, each with its own ToolContext, over one application-scoped resource. It
proves this at every layer the framework owns: ToolRuntime, PageRuntime, the Agent channel
through the MCP SDK, and the Web channel through NiceGUI.

The proof is a barrier, not a duration. A barrier reached through
`ToolContext.dependencies` opens only once two invocations are inside it, so overlap and
dependency sharing are proven by the same event, and a passing run asserts nothing about
elapsed time.

Each channel is driven the way its library documents, and each waits on the mechanism that
library provides. A test-only gate standing in for such a mechanism is not acceptable.

This test should remain throughout the project.

Timeouts and cancellation are not yet defined. See
`docs/decisions/ADR-005-tool-handlers-async-first.md`.

````

Note that the sentence "Domain consistency belongs to the app's service/repository/storage
layer." is deliberately gone: the ownership table's third row now owns that fact, and one
fact is not stated in two places.

- [ ] **Step 3: Check the surrounding document still reads correctly**

Run: `sed -n '1,150p' docs/architecture/runtime.md`

Expected: `## ToolRuntime as the execution center`, `## ToolContext`,
`## Dependency ownership`, `## Concurrency` with its three new subsections, then
`## Dual-channel contract` intact and unmodified. No heading duplicated, no stray blank-line
runs longer than one, and no leftover fence markers from the block above.

- [ ] **Step 4: Run the full verification**

Run: `make lint typecheck test`

Expected: unchanged from Task 4 — ruff clean, pyright clean, all tests pass. Documentation
edits cannot break these, so this step guards against an accidental stray edit.

- [ ] **Step 5: Commit**

```bash
git add docs/architecture/runtime.md
git commit -m "Say which layer owns which part of concurrency

The section stated the properties without saying who is responsible for them,
which is how a reader concludes the framework can create request concurrency, or
that a thin adapter still needs a concurrency test of its own.

Three layers, three owners: the channel technology decides whether two requests
may be in flight, ToolRuntime and PageRuntime decide whether two invocations may
be, and the app's own services decide whether overlapping mutation is correct.
Only the middle one is a framework contract, and what it guarantees is the
absence of serialization the framework itself introduces.

Records what both channel technologies actually do, with sources, that both are
held by tests because their version floors are open, and the consequence of
NiceGUI's single shared loop: concurrency here is cooperative, so a handler that
blocks serializes every channel in the process. That is why AGENTS.md requires
asyncio.to_thread, and the reason now sits next to the guarantee it would void.

Drops the standalone sentence on domain consistency; the table's third row now
owns that fact."
```

---

### Task 6: Retire the milestone folder

Run this task only once Tasks 1 to 5 are committed and `make lint typecheck test` passes.

**Files:**
- Delete: `docs/milestones/M5B/spec.md`, `docs/milestones/M5B/plan.md`, and the `docs/milestones/M5B/` folder

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Confirm everything still true has been promoted**

AGENTS.md requires promoting what is still true out of the folder before deleting it. Check
each part of the spec:

| Spec content | Where it now lives |
| --- | --- |
| concurrency ownership per layer | `docs/architecture/runtime.md`, Task 5 |
| what the MCP SDK and NiceGUI do, with sources | `docs/architecture/runtime.md`, Task 5 |
| the cooperative-concurrency consequence | `docs/architecture/runtime.md`, Task 5 |
| the barrier proof and why not timing | `docs/architecture/runtime.md` and the test's own docstring |
| only official patterns for external libraries | `docs/architecture/runtime.md`, and the per-test docstrings |
| the three acceptance criteria | `tests/test_execution_semantics.py` |
| why each channel test exists | the Task 3 and Task 4 commit messages |
| out-of-scope items and their owners | `docs/roadmap.md` already lists M20, M9, M10 and M17; ADR-005 already defers timeouts |
| the open question on deployment topology | git history, via the spec's commit message |

Run: `git log --format='%s' --grep='M5B' --all`

Expected: the spec commit `Specify the M5B execution semantics design` is present, so the
open question survives the folder's deletion.

Do not invent a document for the open question. No existing document owns "an undecided
deployment topology", and AGENTS.md forbids creating an architecture document for a concept
without stopping to ask. Raise it with the owner instead.

- [ ] **Step 2: Delete the folder**

```bash
git rm -r docs/milestones/M5B
```

- [ ] **Step 3: Verify nothing referenced it**

Run: `grep -rn "milestones/M5B" . --exclude-dir=.git`

Expected: no output. If a reference remains, remove or repoint it before committing.

- [ ] **Step 4: Run the full verification**

Run: `make lint typecheck test`

Expected: ruff clean, pyright clean, all tests pass.

- [ ] **Step 5: Commit**

```bash
git commit -m "Retire the M5B milestone folder

Concurrency ownership, what both channel technologies do, and the
execution-semantics contract now live in docs/architecture/runtime.md, and the
acceptance criteria live in the tests that prove them. Nothing in the folder is
still the sole home of a fact.

Whether the two channels of one installed App share one process stays an open
decision, recorded in this milestone's spec commit and owned by the App Package,
Hub Core and isolation milestones."
```

---

## Definition of done

- `make lint typecheck test` passes.
- `tests/test_execution_semantics.py` holds six passing tests, each shown to fail against a
  deliberate break: a global lock in `ToolRuntime`, a constant invocation id, two Apps with
  separate resources, and a lock in `PageRuntime.render`.
- Each channel test drives its library only through that library's documented API, and waits
  on that library's own mechanism. No test-only gate, sleep or completion flag exists.
- No file under `src/` changed, and no seam was added there for a test.
- `docs/architecture/runtime.md` states concurrency ownership per layer, what the MCP SDK and
  NiceGUI actually do with sources, the cooperative-concurrency consequence, and the contract
  the tests guarantee.
- `docs/milestones/M5B/` is gone.
- Nothing is pushed. Per the milestone workflow, the branch merges into `main` with `--no-ff`
  and the push happens only when the owner asks.
