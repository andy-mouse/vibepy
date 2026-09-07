# M5B Execution Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn ADR-005's async-first concurrency decision into a tested contract, and record in `docs/architecture/runtime.md` which layer owns which part of concurrency.

**Architecture:** No production code changes. A new constitutional test proves that two invocations of one App overlap, each with its own ToolContext, over one shared application-scoped resource. The proof is an `asyncio.Barrier(2)` reached through `ToolContext.dependencies`, so overlap and dependency sharing are proven by the same event and no assertion depends on wall-clock duration.

**Tech Stack:** Python 3.12, pytest with `pytest-asyncio` in auto mode, pydantic v2, `asyncio.Barrier`, `asyncio.timeout`.

## Global Constraints

- `pyproject.toml` is the only project config. Do not add `setup.py` or `requirements.txt`.
- `requires-python = ">=3.12"`. `asyncio.Barrier` (3.11+) and `asyncio.timeout` (3.11+) are available.
- ruff `line-length = 100`, lint rules `["E", "F", "I", "UP", "B", "ASYNC", "RUF"]`.
- pyright `typeCheckingMode = "strict"` over `src` and `tests`.
- `Any` and `cast` are not acceptable. Narrow with `isinstance`, as the existing tests do.
- pytest `asyncio_mode = "auto"`. An `async def test_*` needs no decorator.
- Tests verify public contracts, not internals.
- Standard `logging` only. No `print`.
- A change is done when `make lint typecheck test` passes.
- `docs/roadmap.md` is never edited.
- Do not implement ahead of M5B. Timeouts, cancellation, sync handler support and fan-out helpers are out of scope; see `docs/milestones/M5B/spec.md`.

## File Structure

| File | Responsibility |
| --- | --- |
| `tests/test_execution_semantics.py` (create) | The execution-semantics contract: overlap, context independence, dependency sharing. Constitutional, like `tests/test_dual_channel.py`. |
| `docs/architecture/runtime.md` (modify) | Current truth for runtime execution. Gains concurrency ownership per layer and the contract the new test guarantees. |
| `docs/milestones/M5B/` (delete, last task) | Retired on integration per AGENTS.md. |

No file under `src/` changes. `ToolRuntime.invoke` already holds no lock and already builds a fresh `ToolContext` per invocation over one shared `dependencies`.

---

### Task 1: The execution-semantics contract test

**Files:**
- Create: `tests/test_execution_semantics.py`
- Temporarily modify, then revert: `src/vibepy/tool/runtime.py`

**Interfaces:**
- Consumes: `AppDefinition(app_id, name, version, create_dependencies, tools, pages)` and `AppRuntime(definition)` from `vibepy.app`; `Tool(definition=..., handler=...)`, `ToolDefinition(name, description, input_model, output_model)` and `ToolContext[DepsT]` with fields `app_id`, `invocation_id`, `dependencies` from `vibepy.tool`; `AppRuntime.tool_runtime.invoke(name, raw_input) -> Awaitable[BaseModel]`.
- Produces: nothing later tasks import. Task 2 refers to this file by path only.

- [ ] **Step 1: Write the failing test**

Create `tests/test_execution_semantics.py` with exactly this content:

```python
"""The execution-semantics contract from docs/architecture/runtime.md.

Two invocations of one App overlap, each with its own ToolContext, over one
application-scoped resource. This test is constitutional: it stays for the life
of the project.

The proof is a barrier rather than a duration. An ``asyncio.Barrier(2)`` opens
only once two waiters are inside it, and it is reached through
``ctx.dependencies``, so it opens only if the two invocations overlap and also
received the same resource. A passing run asserts nothing about elapsed time;
the timeout exists only to turn the deadlock of a serialized runtime into a
failure.

The resource is built by the test rather than read back from AppRuntime, which
does not expose it. Observing app-scoped state is what this contract is about,
and reaching it this way adds no accessor to the runtime.
"""

import asyncio

from pydantic import BaseModel

from vibepy.app import AppDefinition, AppRuntime
from vibepy.tool import Tool, ToolContext, ToolDefinition

PARTIES = 2
DEADLOCK_TIMEOUT_SECONDS = 5


class EmptyInput(BaseModel):
    pass


class Meeting(BaseModel):
    """What one invocation reports about itself once the barrier opens."""

    invocation_id: str
    dependency_id: int


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


MEET = Tool(
    definition=ToolDefinition(
        name="meet",
        description="Wait for a concurrent invocation, then report this one's identity",
        input_model=EmptyInput,
        output_model=Meeting,
    ),
    handler=meet,
)


def build_definition(resource: Rendezvous) -> AppDefinition[Rendezvous]:
    return AppDefinition(
        app_id="rendezvous-app",
        name="Rendezvous",
        version="0.0.0",
        create_dependencies=lambda: resource,
        tools=[MEET],
        pages=[],
    )


async def overlap() -> tuple[Rendezvous, Meeting, Meeting]:
    """Invoke one App's Tool twice concurrently and return the resource and both reports.

    Built through AppRuntime rather than by constructing a ToolRuntime directly,
    because "app-scoped" is a claim about the layer that owns the resource.
    """
    resource = Rendezvous()
    app = AppRuntime(build_definition(resource))

    async with asyncio.timeout(DEADLOCK_TIMEOUT_SECONDS):
        first, second = await asyncio.gather(
            app.tool_runtime.invoke("meet", {}),
            app.tool_runtime.invoke("meet", {}),
        )

    assert isinstance(first, Meeting)
    assert isinstance(second, Meeting)
    return resource, first, second


async def test_two_invocations_are_in_flight_at_once() -> None:
    resource, _first, _second = await overlap()

    assert resource.log[:PARTIES] == ["arrived", "arrived"]
    assert resource.log[PARTIES:] == ["departed", "departed"]


async def test_concurrent_invocations_receive_independent_contexts() -> None:
    _resource, first, second = await overlap()

    assert first.invocation_id != second.invocation_id


async def test_concurrent_invocations_share_app_scoped_dependencies() -> None:
    resource, first, second = await overlap()

    assert first.dependency_id == second.dependency_id
    assert first.dependency_id == id(resource)
```

- [ ] **Step 2: Run the test and expect it to pass on the first run**

Run: `uv run pytest tests/test_execution_semantics.py -v`

Expected: 3 passed.

This is the milestone's finding, not a mistake. `ToolRuntime.invoke` already satisfies all
three acceptance criteria, so there is no red phase to reach by writing production code. A
test that has never failed proves nothing, so the next two steps make each assertion fail on
purpose against a deliberately broken runtime.

- [ ] **Step 3: Negative control A — prove the barrier test detects serialization**

Edit `src/vibepy/tool/runtime.py`. Add `import asyncio` at the top of the import block, then
replace the body of `ToolRuntime` with a globally locked version by adding a lock to
`__init__` and wrapping `invoke`:

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

Revert immediately:

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

Revert immediately:

```bash
git checkout src/vibepy/tool/runtime.py
```

- [ ] **Step 5: Negative control C — prove the barrier depends on a shared resource**

This control edits the test, not the runtime, because no small change to `ToolRuntime`
produces a per-invocation resource. In `tests/test_execution_semantics.py`, replace these
two lines inside `overlap()`:

```python
    resource = Rendezvous()
    app = AppRuntime(build_definition(resource))
```

with two Apps that each own their own resource:

```python
    resource = Rendezvous()
    app = AppRuntime(build_definition(resource))
    other = AppRuntime(build_definition(Rendezvous()))
```

and replace the second invocation inside the `gather` call:

```python
            app.tool_runtime.invoke("meet", {}),
```

so that the two invocations go to different Apps:

```python
            other.tool_runtime.invoke("meet", {}),
```

Run: `uv run pytest tests/test_execution_semantics.py -v`

Expected: all 3 tests FAIL with `TimeoutError`. Two invocations that do not share a resource
do not share its barrier, so it never opens. This is what makes the barrier a proof of
sharing and not only of overlap, as the spec claims.

Restore the file by hand — it is untracked at this point, so `git checkout` cannot help.
Delete the `other = ...` line and change `other.tool_runtime.invoke("meet", {}),` back to
`app.tool_runtime.invoke("meet", {}),`, leaving two identical `app.tool_runtime.invoke`
lines inside the `gather` call.

- [ ] **Step 6: Confirm the working tree is clean apart from the new test**

Run: `git status --short`

Expected: exactly one line, `?? tests/test_execution_semantics.py`. If
`src/vibepy/tool/runtime.py` appears, a revert was missed; run
`git checkout src/vibepy/tool/runtime.py` and re-run `git status --short`.

Then confirm the test file itself is back to the Step 1 content:

Run: `grep -c "app.tool_runtime.invoke" tests/test_execution_semantics.py`

Expected: `2`. A `1` means Control C's edit is still in place.

- [ ] **Step 7: Run the full verification**

Run: `make lint typecheck test`

Expected: ruff clean, pyright clean, every test passes including the 3 new ones and all
pre-existing tests unchanged.

- [ ] **Step 8: Commit**

```bash
git add tests/test_execution_semantics.py
git commit -m "Prove two Tool invocations of one App overlap

ToolRuntime already held no lock and already built a fresh ToolContext per
invocation over one shared resource, so this milestone adds no production code.
The contract was asserted in ADR-005 and untested; now a test holds it.

The proof is an asyncio.Barrier(2) reached through ToolContext.dependencies.
It opens only when two invocations are inside it, so overlap and dependency
sharing are proven by one event, and a passing run asserts nothing about
elapsed time. asyncio.timeout only turns a serialized runtime's deadlock into a
failure.

Verified against three deliberately broken runtimes: a global lock times all
three tests out, a constant invocation id fails only the independence test, and
a per-invocation copy of the resource fails overlap and sharing together."
```

---

### Task 2: Record where concurrency is owned

**Files:**
- Modify: `docs/architecture/runtime.md:72-83` (the `## Concurrency` section)

**Interfaces:**
- Consumes: `tests/test_execution_semantics.py` from Task 1, referenced by path.
- Produces: nothing later tasks import.

- [ ] **Step 1: Read the section as it stands**

Run: `sed -n '68,90p' docs/architecture/runtime.md`

Expected: the `## Concurrency` section, then `## Dual-channel contract`.

- [ ] **Step 2: Replace the Concurrency section**

Replace everything from the line `## Concurrency` up to but not including the line
`## Dual-channel contract` with:

```markdown
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
| Framework | may two invocations be in flight at once? | ToolRuntime |
| Domain | is overlapping mutation correct? | the app's own services and storage |

Only the middle row is a framework contract. The framework guarantees the absence of
serialization it introduces itself. It cannot create request concurrency that its channel
technology does not offer, and it does not make an app's domain state safe under overlap.

A channel adapter reduces a request to a single `await` on a runtime, so it adds no
serialization of its own. See `docs/decisions/ADR-003-channel-adapters-are-thin.md`.

Timeouts and cancellation are not yet defined. See
`docs/decisions/ADR-005-tool-handlers-async-first.md`.

### The execution-semantics contract

The framework must maintain a constitutional integration test proving that two invocations
of one App overlap, each with its own ToolContext, over one application-scoped resource.

The proof is a barrier, not a duration. A barrier reached through
`ToolContext.dependencies` opens only once two invocations are inside it, so overlap and
dependency sharing are proven by the same event, and a passing run asserts nothing about
elapsed time.

This test should remain throughout the project.

```

Note that the sentence "Domain consistency belongs to the app's service/repository/storage
layer." is deliberately gone: the table's third row now owns that fact, and one fact is not
stated in two places.

- [ ] **Step 3: Check the surrounding document still reads correctly**

Run: `sed -n '1,120p' docs/architecture/runtime.md`

Expected: `## ToolContext`, `## Dependency ownership`, `## Concurrency` with its two new
subsections, then `## Dual-channel contract` intact and unmodified. No heading duplicated, no
stray blank-line runs longer than one.

- [ ] **Step 4: Run the full verification**

Run: `make lint typecheck test`

Expected: unchanged from Task 1 — ruff clean, pyright clean, all tests pass. Documentation
edits cannot break these, so this step is a guard against an accidental stray edit.

- [ ] **Step 5: Commit**

```bash
git add docs/architecture/runtime.md
git commit -m "Say which layer owns which part of concurrency

The section stated the properties without saying who is responsible for them,
which is how a reader concludes the framework can create request concurrency,
or that a thin adapter still needs a concurrency test of its own.

Three layers, three owners: the channel technology decides whether two requests
may be in flight, ToolRuntime decides whether two invocations may be, and the
app's own services decide whether overlapping mutation is correct. Only the
middle one is a framework contract, and what it guarantees is the absence of
serialization the framework itself introduces.

Drops the standalone sentence on domain consistency; the table's third row now
owns that fact."
```

---

### Task 3: Retire the milestone folder

Run this task only once Tasks 1 and 2 are committed and `make lint typecheck test` passes.

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
| concurrency ownership per layer | `docs/architecture/runtime.md`, Task 2 |
| the barrier proof and why not timing | `docs/architecture/runtime.md` and the test's own docstring |
| the three acceptance criteria | `tests/test_execution_semantics.py` |
| why adapters are not tested for concurrency | `docs/architecture/runtime.md`, and ADR-003 already owns adapter thinness |
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

Concurrency ownership and the execution-semantics contract now live in
docs/architecture/runtime.md, and the acceptance criteria live in the test that
proves them. Nothing in the folder is still the sole home of a fact.

Whether the two channels of one installed App share one process stays an open
decision, recorded in this milestone's spec commit and owned by the App Package,
Hub Core and isolation milestones."
```

---

## Definition of done

- `make lint typecheck test` passes.
- `tests/test_execution_semantics.py` holds three passing tests, each shown to fail against a
  deliberately broken runtime.
- No file under `src/` changed.
- `docs/architecture/runtime.md` states concurrency ownership per layer and the contract the
  test guarantees.
- `docs/milestones/M5B/` is gone.
- Nothing is pushed. Per the milestone workflow, the branch merges into `main` with `--no-ff`
  and the push happens only when the owner asks.
