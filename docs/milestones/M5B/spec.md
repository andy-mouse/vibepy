# M5B - Execution semantics

## Acceptance criteria

From `docs/roadmap.md`:

- concurrent independent Tool calls execute without global serialization
- each invocation has independent ToolContext
- app-scoped dependencies remain shared

## Finding: the criteria are already structurally satisfied

`ToolRuntime.invoke` holds no lock, no queue and no mutable state. It resolves a Tool,
constructs a fresh `ToolContext` with a `uuid4()` invocation id, and awaits the Tool's bound
callable. `dependencies` is the one value the runtime received from AppRuntime, handed to
every context unchanged.

M5A proved context independence and dependency sharing across *sequential* invocations
(`tests/test_app_runtime.py`). It did not prove either while two invocations overlap, and it
did not prove that overlap is possible at all.

M5B therefore adds no capability. It converts the async-first concurrency decision of
`docs/decisions/ADR-005-tool-handlers-async-first.md` from an asserted property into a
tested contract, and records in `docs/architecture/runtime.md` which layer owns which part
of concurrency.

If the tests pass without any change under `src/`, that is the milestone's result, not a gap
in it.

## Where concurrency is owned

Three layers, three owners:

| Layer | Concurrency question | Owner |
| --- | --- | --- |
| Channel transport | may two requests be in flight at once? | MCP SDK, uvicorn |
| Framework | may two invocations be in flight at once? | ToolRuntime |
| Domain | is overlapping mutation correct? | the app's own services and storage |

Only the middle row is a framework contract. The framework's obligation is to add no
serialization of its own; it cannot create request concurrency that its channel technology
does not offer, and it does not make an app's domain state safe under overlap.

`src/vibepy/adapters/mcp/server.py` and `src/vibepy/adapters/nicegui/web.py` reduce a
request to a single `await` on a runtime, per
`docs/decisions/ADR-003-channel-adapters-are-thin.md`. Neither has a place to introduce
serialization, so neither is a subject of these tests: a test there would verify the MCP SDK
and uvicorn rather than a Vibepy contract.

## The proof

### Why not timing

"Two 100 ms calls finished in 120 ms, so they overlapped" fails on a loaded CI machine and
passes on a fast one for the wrong reason. No assertion in this milestone may depend on
wall-clock duration.

### The barrier

An `asyncio.Barrier(2)` opens only when two waiters are inside it. Put one in the App's
application-scoped dependency and have the Tool handler await it:

- if the two invocations overlap, the second waiter arrives while the first is suspended,
  the barrier opens, and both invocations return
- if anything serialized them, the first waiter waits for a second waiter that cannot be
  admitted, and nothing returns

The barrier is reached through `ctx.dependencies`, so it opens only if both invocations also
received the same dependency instance. Concurrency and dependency sharing are proven by the
same event rather than by two independent assertions.

Deadlock is a hang, not a failure, so the concurrent run is wrapped in `asyncio.timeout()`.
The timeout is a deadlock detector: passing the test requires no wall-clock assumption, and
the elapsed time of a passing run is not asserted on.

### Tests

A new `tests/test_execution_semantics.py` owns the execution-semantics contract, next to
`tests/test_dual_channel.py` which owns the dual-channel contract. Like that file it stays
for the life of the project.

One fixture App: a dependency holding the barrier, and one Tool whose handler awaits it and
reports `ctx.invocation_id` and `id(ctx.dependencies)` through its output model. One helper
runs the two invocations under `asyncio.gather` inside the timeout and returns both results.

| Test | Asserts | Fails when |
| --- | --- | --- |
| two invocations are in flight at once | both invocations return | anything serializes invocation |
| concurrent invocations receive independent contexts | the two invocation ids differ | a context is reused or cached across invocations |
| concurrent invocations share app-scoped dependencies | the two dependency identities are equal | a dependency is rebuilt per invocation |

The App is built through `AppRuntime`, not by constructing `ToolRuntime` directly, because
"app-scoped" is a claim about the layer that owns the resource.

## Documentation

`docs/architecture/runtime.md` is the current-truth document for runtime execution, and its
Concurrency section already states the properties. It gains what it does not yet say: which
layer owns which concurrency question, per the table above, and that the framework's
guarantee is the absence of framework-introduced serialization rather than the presence of
request concurrency.

No new architecture document: `runtime.md` owns this concept.

No ADR. ADR-005 already records async-first handlers and the absence of a global lock as
Accepted, and M5B takes no decision between real alternatives. Choices below that line, such
as the barrier technique and the test file's placement, go in commit messages.

## Out of scope

| Excluded | Why | Owner |
| --- | --- | --- |
| cancellation and timeout semantics | ADR-005 defers them explicitly | M20 |
| synchronous or blocking handler support | ADR-005 makes async canonical; AGENTS.md puts `asyncio.to_thread` on the app author | not planned |
| a fan-out helper such as `invoke_many` | a caller uses `asyncio.gather`; no repetition justifies the abstraction | not planned |
| adapter-level concurrency tests | the MCP SDK and uvicorn own request concurrency; the adapters are a single `await` | not planned |
| Page render concurrency | `PageRuntime` holds no per-render state, and a Page reaches a Tool through the ToolRuntime path proven here | not planned |
| concurrency between the Web and Agent channels | requires a deployment topology no document decides; see below | M9, M10, M17 |

## Open question, not decided here

No document states whether the Web channel and the Agent channel of one installed App share
one operating-system process.

`docs/decisions/ADR-010-agent-platform-owns-the-mcp-process.md` has the agent platform spawn
the MCP server process over stdio. That process builds its own AppRuntime, and therefore its
own application-scoped resource, so two channels deployed that way share no in-memory state.
ADR-010 also leaves room for MCP served over HTTP from inside the app process, where they
would share one AppRuntime.

The dual-channel contract in `docs/architecture/runtime.md` is an architectural requirement
about one App having one AppRuntime, which `tests/test_dual_channel.py` proves in-process. It
is not a statement about deployment topology.

M5B neither answers this nor depends on the answer. It belongs to the App Package, Hub Core
and isolation milestones, and the owner decides it.

## Verification

`make lint typecheck test` passes. The three new tests pass, and every existing test still
passes unchanged.
