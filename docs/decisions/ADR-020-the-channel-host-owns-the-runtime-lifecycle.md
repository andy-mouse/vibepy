# ADR-020: The channel host owns the runtime lifecycle

Status: Accepted

Supersedes: ADR-004, ADR-015, ADR-018

## Context

`AppRuntime` exists before it is started and after it is stopped. Because the object can be held
in states where its contents do not exist, `tool_runtime` and `page_runtime` have to refuse to
answer, which is why `AppRuntimeState`, `AppRuntimeTransitionError`, `AppRuntimeNotRunningError`,
the transition checks and a shared `started()` test helper all exist. Every one of them is the
cost of having made a state representable that has no legitimate use.

Both channel hosts already bind a running window to a block, where that state cannot be reached
because the object does not yet exist.

The MCP SDK takes
`lifespan: Callable[[Server[LifespanResultT]], AbstractAsyncContextManager[LifespanResultT]]`,
propagates `LifespanResultT` to `ServerRequestContext`, and enters and exits the context manager
inside `run()`
(<https://py.sdk.modelcontextprotocol.io/v2/api/mcp/server/lowlevel/server>). A handler reaches
what it yielded through the request context it is already given.

NiceGUI offers no such mechanism, and its absence is documented rather than assumed. It documents
`app.on_startup` and `app.on_shutdown` and nothing that carries state between them
(<https://nicegui.io/documentation/section_action_events>). It mounts into an existing FastAPI
application as a sub-application, `ui.run_with(fastapi_app, mount_path='/gui')`
(<https://github.com/zauberzeug/nicegui/blob/main/nicegui/llms.md>), and Starlette documents that
request state is a shallow copy of lifespan state without documenting that it reaches a mounted
sub-application (<https://github.com/kludex/starlette/blob/main/docs/lifespan.md>). Reading the
resource out of `request.state` would therefore rest on behaviour no source promises.

It is not needed. A NiceGUI page builder is a callable the adapter constructs, and it already
closes over the runtime it renders through. A closure is a language guarantee, not a library one.

## Decision

The channel host owns the running window. The framework owns no lifecycle object, no lifecycle
state and no lifecycle error.

The framework supplies two async context managers, `tool_runtime_for` and `page_runtime_for`.
Each pairs a `AppDefinition` with a lifespan and yields the one runtime its channel needs, for
the duration of the block and no longer.

The Agent channel hands its context manager to `Server(lifespan=...)` and reads the runtime from
the request context. The Web channel opens the block itself, registers routes inside it, and lets
each page builder close over the runtime.

## Consequences

- `AppRuntime`, `AppRuntimeState`, `AppRuntimeTransitionError` and `AppRuntimeNotRunningError` are
  removed, and with them the codes `lifecycle.transition_forbidden` and `lifecycle.not_running`
  and the `ErrorCategory.LIFECYCLE` that no code then maps to. A lifespan that fails propagates to
  its host, which the host's own contract already covers
- a app that is not running is not representable. What replaced the guard is not a better guard
  but the absence of the state it guarded
- `_no_lifespan` is removed. It existed only to keep `Any` out of the adapter's return type, and a
  real lifespan carries a real type: the server is `Server[ToolRuntime[DepsT]]`
- the two channels use different mechanisms, because each host documents a different one. Giving
  them a common shape would mean inventing one, which ADR-003 forbids of an adapter
- the SDK enters its lifespan inside `run()`, so the window is one connection. Over stdio that is
  the process, because the client launches one server process and speaks to it over that process's
  streams, which is what ADR-010 and ADR-017 already rest on
- ADR-017 is completed on two points it left unsaid. A lifespan is entered once per channel
  process, so an installed App acquires its resource once per channel and not once in total;
  and ADR-015's requirement that both adapters receive one instance is destroyed by that same
  fact, not merely weakened
- ADR-004 is superseded. Its artifact, `AppDefinition -> AppRuntime`, no longer exists: what a
  declaration becomes is a window rather than an object. The principle underneath it — a
  declaration is not executable state — survives in ADR-021, which states it about a value
- ADR-015 is superseded. Its context sentence — "Both adapters of one running App must receive the
  same AppRuntime instance" — is false across processes. What it was protecting, that a channel
  cannot be wired to a backend that is not its own, is now carried by each adapter taking one
  definition and one lifespan
- ADR-018 is superseded in owner only. Acquisition and release remain one async context manager
  and paired `on_start`/`on_stop` hooks remain rejected, for the reasons ADR-018 gives and which
  this decision does not disturb. What changes is that the host enters it rather than an
  `AppRuntime` holding an `AsyncExitStack`
- ADR-006 and ADR-012 stand. ADR-006's "AppRuntime manages start/stop execution lifecycle only"
  and ADR-012's "the runtime lifecycle adds a call to `ui.run()` at startup" name an object that no
  longer exists; both decisions are carried forward unchanged, and how to serve becomes the
  entrypoint's decision rather than a lifecycle step
- `docs/roadmap.md` M6 asks that the "runtime transitions through the defined lifecycle states
  predictably". That criterion is superseded rather than unmet: it describes a machine this
  decision removes. The roadmap is not edited, and the owner was asked and approved
- the constitutional dual-channel test can no longer claim that two channels share one runtime.
  What it claims instead is that neither channel keeps a backend of its own, proven by composing
  one lifespan into both. `docs/architecture/runtime.md` carries the restatement
