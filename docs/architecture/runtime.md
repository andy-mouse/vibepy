# Runtime Architecture

## ToolRuntime as the execution center

All channel invocation converges at ToolRuntime.

```text
Web / Page ----\
                -> ToolRuntime -> Tool -> Domain internals
MCP Adapter ---/
```

This central boundary is where generic framework behavior can be added consistently over time.

Potential future cross-cutting concerns include:

- authorization
- audit
- timeout
- tracing
- metrics
- transaction hooks
- rate limits

Do not add a generic middleware framework until a concrete need appears.

## ToolContext

ToolContext is invocation-scoped and deliberately narrower than the window it comes from.

It currently carries:

- app id
- invocation id
- `dependencies`: the application-scoped resource, typed by the app itself

`dependencies` is one value of the app's own type, not a mapping and not the runtime.

Future fields may include:

- principal
- actor
- channel metadata
- tenant
- locale
- permissions
- trace context

ToolRuntime creates a ToolContext for every invocation, with an invocation id unique to
that invocation. Channels never construct one.

Do not make ToolContext an untyped service-locator bag. See
`docs/decisions/ADR-013-dependencies-reach-handlers-through-tool-context.md`.

## Dependency ownership

Application-scoped dependencies belong to the channel's running window, which
`docs/architecture/app-model.md` describes together with the other state scopes. A window
validates the App's configuration before it acquires anything, so a resource is never acquired
for a window that cannot run. See `docs/decisions/ADR-022-configuration-is-a-declaration.md`.

What the runtime does with them: ToolRuntime holds the one resource the window acquired and puts
that value into every ToolContext it creates. Prefer typed dependency objects over generic
dictionaries when practical.

## Concurrency

Tool handlers are async-first.

ToolRuntime permits concurrent invocations by default.

ToolRuntime must not serialize all calls with a global lock.

Each invocation receives an independent ToolContext while sharing the application-scoped
resource its window acquired.

### Where concurrency is owned

| Layer | Question | Owner |
| --- | --- | --- |
| Channel transport | may two requests be in flight at once? | MCP SDK, NiceGUI over uvicorn |
| Framework | may two invocations be in flight at once? | ToolRuntime, PageRuntime |
| Domain | is overlapping mutation correct? | the app's own services and storage |

Only the middle row is a framework contract. The framework guarantees the absence of
serialization it introduces itself. It cannot create request concurrency that its channel
technology does not offer, and it does not make a app's domain state safe under overlap.

A channel adapter reduces a request to a single `await` on a runtime, so it adds no
serialization of its own. See `docs/decisions/ADR-003-channel-adapters-are-thin.md`.

### What the channel technologies do

The MCP protocol permits concurrent in-flight requests but does not require a server to
process them concurrently, and the SDK documents no concurrency guarantee for request
handling. What it documents is the serialized exception: `inline_methods` are awaited in the
read loop before the next message is dequeued, and the runner sets that to `initialize`
alone. Everything else is spawned, so `tools/call` requests on one session overlap in
practice.

NiceGUI runs on a single shared asyncio event loop and dispatches an async event handler as
a background task, so an interaction does not hold the request that triggered it and two
interactions overlap. Blocking that loop freezes the application for every user, so blocking
I/O belongs in `run.io_bound` and CPU work in `run.cpu_bound`.

Neither behaviour is promised in writing, and `pyproject.toml` carries only a lower bound on
each library. They are held by tests rather than by this section.

Concurrency in this framework is therefore cooperative. Overlap happens at `await` points,
which has one consequence a app author must know: a Tool handler that blocks the event loop
serializes every channel in its process, and that is exactly the case where ToolRuntime's
absence of a lock delivers nothing. Wrap blocking calls in `asyncio.to_thread`.

Sources:

- <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>
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

The proof is a barrier, not a duration. A barrier reached through `ToolContext.dependencies`
opens only once two invocations are inside it, so overlap and dependency sharing are proven
by the same event, and a passing run asserts nothing about elapsed time.

Each channel is driven the way its library documents, and each waits on the mechanism that
library provides. A test-only gate standing in for such a mechanism is not acceptable.

This test should remain throughout the project.

Timeouts and cancellation are not yet defined. See
`docs/decisions/ADR-005-tool-handlers-async-first.md`.

## Dual-channel contract

The framework must maintain a constitutional integration test proving that neither channel keeps
a backend of its own: both reach one Tool implementation over one resource.

Example:

1. Agent-side invocation creates item A.
2. Web-side invocation creates item B.
3. Web-side read sees A and B.
4. Agent-side read sees A and B.

The test composes one lifespan into both channels, so a private backend on either side shows up
as a divergence. That composition is the test's own arrangement, not a framework guarantee: a
deployed App runs each channel in its own process, so a resource that must be shared across
them belongs in a backing service. See
`docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md`.

This test should remain throughout the project.
