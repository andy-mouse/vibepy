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
| Channel transport | may two requests be in flight at once? | MCP SDK, NiceGUI over uvicorn |
| Framework | may two invocations be in flight at once? | ToolRuntime, PageRuntime |
| Domain | is overlapping mutation correct? | the app's own services and storage |

Only the middle row is a framework contract. The framework's obligation is to add no
serialization of its own; it cannot create request concurrency that its channel technology
does not offer, and it does not make an app's domain state safe under overlap.

`src/vibepy/adapters/mcp/server.py` and `src/vibepy/adapters/nicegui/web.py` reduce a
request to a single `await` on a runtime, per
`docs/decisions/ADR-003-channel-adapters-are-thin.md`. Neither has a place to introduce
serialization.

## What the channel technologies actually do

The table above asserts something about two external libraries, so it is verified rather
than assumed.

### MCP SDK: concurrent in practice, not guaranteed in writing

Three layers answer this differently, and conflating them would overstate what we may rely
on.

The protocol permits concurrent in-flight requests. The Streamable HTTP transport refers to
messages "unrelated to any concurrently-running JSON-RPC request from the client", and
`CancelledNotification` exists so a client can cancel a request that is still in
flight.[^mcp-spec] Neither requires a server to process requests concurrently; both presume
it may.

The SDK's own documentation states no concurrency guarantee for server request handling. Its
low-level server guide says nothing about concurrency, reentrancy or thread-safety. Where it
does describe serialization, it describes the exception: the JSON-RPC dispatcher's
`inline_methods` are "awaited directly in the read loop before the next message is
dequeued", and notification bindings deliver "one at a time per binding".[^mcp-dispatch] The
server runner's API reference shows `inline_methods={"initialize"}`, so the handshake is the
only method described that way.[^mcp-inline]

The implementation does spawn. Verified against `mcp==2.1.1`: two `tools/call` requests
issued concurrently on one in-process `Client` session both arrive before either departs,
with distinct invocation ids and one shared dependency instance.

So the Agent channel's concurrency is a current implementation behaviour that the protocol
allows and the SDK does not promise, and `pyproject.toml` pins only `mcp>=2.1`. That is
precisely a dependency assumption to hold with a test rather than a sentence in a document —
not because an upgrade is likely to break it, but because nothing in writing says it cannot.

### NiceGUI: one shared event loop, cooperative, and fire-and-forget events

NiceGUI runs on "a single shared asyncio event loop", and blocking it "will freeze the
application for all users"; blocking I/O belongs in `run.io_bound` and CPU work in
`run.cpu_bound`.[^nicegui-loop][^nicegui-faq]

`handle_event` states the dispatch rule: "If the handler returns an awaitable, it is
scheduled as a background task."[^nicegui-event] An async event handler therefore does not
hold the interaction that dispatched it, and two interactions can be in flight at once.

Verified against `nicegui==3.16.0`: two users built from the `create_user` fixture, each
clicking a button whose handler invokes a Tool, produce the arrival log
`['arrived', 'arrived', 'departed', 'departed']`.

`pyproject.toml` pins only `nicegui>=3.16`, so this is the same kind of upgrade-breakable
assumption as the MCP one, and it becomes a test for the same reason.

One consequence stays a statement rather than a test, because no framework test can catch
it: concurrency here is cooperative, so a Tool handler that blocks the event loop serializes
every channel in its process. That is precisely the case where "ToolRuntime holds no lock"
delivers nothing, and it is why AGENTS.md requires blocking calls to be wrapped in
`asyncio.to_thread`.

[^mcp-dispatch]: MCP Python SDK, `mcp.shared.jsonrpc_dispatcher`,
    <https://py.sdk.modelcontextprotocol.io/v2/api/mcp/shared/jsonrpc_dispatcher>
[^mcp-inline]: MCP Python SDK, `mcp.server.runner`,
    <https://py.sdk.modelcontextprotocol.io/v2/api/mcp/server/runner>
[^nicegui-loop]: NiceGUI, `nicegui/llms.md`, "Async in NiceGUI: the event loop is shared",
    <https://github.com/zauberzeug/nicegui/blob/main/nicegui/llms.md>
[^nicegui-faq]: NiceGUI FAQ, "Why is my long running function blocking UI updates?",
    <https://github.com/zauberzeug/nicegui/wiki/FAQs>
[^nicegui-event]: NiceGUI, `nicegui.events.handle_event`,
    <https://github.com/zauberzeug/nicegui/blob/main/nicegui/events.py>
[^mcp-spec]: Model Context Protocol specification 2025-06-18, Transports and Cancellation,
    <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>

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

The fixture App declares:

- `Rendezvous`, the application-scoped resource: one `asyncio.Barrier(2)` and one log
- `meet`, a Tool that logs, awaits the barrier, logs again, and reports `ctx.invocation_id`
  and `id(ctx.dependencies)`
- `read_log`, a Tool that reports the log
- a Page whose render invokes `meet`, and a Page with a button whose click handler invokes
  `meet` and then updates a label

`create_dependencies` is the real `Rendezvous` factory. Every test observes app-scoped state
through `read_log` rather than by holding the resource, which is the pattern
`tests/test_app_runtime.py` already uses for `id(ctx.dependencies)`. No test reaches into a
runtime, and no seam is added to `src/` for the test's benefit.

| Test | Layer | Fails when |
| --- | --- | --- |
| two invocations are in flight at once | ToolRuntime | anything serializes invocation |
| concurrent invocations receive independent contexts | ToolRuntime | a context is reused across invocations |
| concurrent invocations share app-scoped dependencies | ToolRuntime | a dependency is rebuilt per invocation |
| two Page renders are in flight at once | PageRuntime | PageRuntime serializes renders |
| two Agent-channel calls are in flight at once | MCP adapter over the SDK | the SDK stops spawning `tools/call`, or the adapter serializes |
| two Web-channel interactions are in flight at once | NiceGUI adapter over NiceGUI | NiceGUI stops dispatching handlers as background tasks, or the adapter serializes |

Every test but the two identity ones asserts the same log, `["arrived", "arrived",
"departed", "departed"]`.

### Only official patterns for the external libraries

Each channel test drives its library the way that library documents, with no test-only
scaffolding standing in for a mechanism the library already provides.

Agent channel. `Client` accepts a `Server` instance directly for an in-process connection,
which the SDK documents as its in-memory transport and names as the testing
path.[^mcp-inproc] The test passes `build_mcp_server(app)` to `Client`, as
`tests/test_dual_channel.py` already does.

Web channel. NiceGUI documents the `create_user` factory fixture for simultaneous users,
stating that "the `User` instances are independent from each other and can interact with the
UI in parallel", and its example is `create_user()`, `await user.open(...)`,
`user.find(...)` with an interaction, then `await user.should_see(...)`.[^nicegui-user] The
test follows that shape exactly.

`should_see` is also the reason the Web test needs nothing of its own to wait on. A NiceGUI
event handler is dispatched as a background task, so the click returns before the Tool
invocation finishes; `should_see` retries until the label changes and raises an
`AssertionError` if it never does. An ad-hoc completion Event in the fixture would be a
test-only gate around a mechanism NiceGUI already documents, so there is none.

`asyncio.timeout` still wraps the three non-Web overlaps. That is not a gate around a
library: without it a serialized runtime hangs the suite instead of failing, and
`should_see` already provides the equivalent bound on the Web side.

### Why the two channel tests exist

Neither is a test of an external library. Each drives the composition a real caller
reaches — our adapter on top of that library — and pins the behaviour that makes the
framework's concurrency guarantee mean anything on that channel. Both floors in
`pyproject.toml` are open (`mcp>=2.1`, `nicegui>=3.16`), so an upgrade can remove either
behaviour with nothing failing.

The PageRuntime test exists for a different reason: `src/vibepy/page/runtime.py` already
claims it "does not serialize renders", and that claim has been untested since M2.

[^mcp-inproc]: MCP Python SDK, client transports and `mcp.client.client`,
    <https://py.sdk.modelcontextprotocol.io/v2/client/transports>,
    <https://py.sdk.modelcontextprotocol.io/v2/api/mcp/client/client>
[^nicegui-user]: NiceGUI, User fixture reference,
    <https://nicegui.io/documentation/user>

## Documentation

`docs/architecture/runtime.md` is the current-truth document for runtime execution, and its
Concurrency section already states the properties. It gains what it does not yet say:

- which layer owns which concurrency question, per the table above
- that the framework's guarantee is the absence of framework-introduced serialization rather
  than the presence of request concurrency
- what both channel technologies actually do, cited, and that both are pinned by tests
  because their version floors are open
- that concurrency is cooperative, so a Tool handler that blocks the event loop serializes
  every channel in its process

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
| detecting a Tool handler that blocks the event loop | cooperative concurrency makes this the app author's responsibility; AGENTS.md requires `asyncio.to_thread`, and a framework test cannot catch it | not planned |
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

`make lint typecheck test` passes. The six new tests pass, each shown to fail against a
deliberate break, and every existing test still passes unchanged.
