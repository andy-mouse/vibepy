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

- an App author declares a lifespan and hands it to a channel. There is no runtime to construct,
  start or stop, and no order of those calls to get wrong
- a runtime that is not running is not representable, so the lifecycle state and its two errors
  have nothing left to describe. A lifespan that raises propagates to its host, whose contract
  already covers reporting it
- a window cannot be reached from outside itself. A control plane that stops a channel stops its
  process, which is what the Hub was already going to do for the Web channel
- an installed App acquires its resource once per channel rather than once in total, which makes
  ADR-017's share-nothing requirement binding rather than advisory
- the two channels reach their runtime by different means, because each host documents a
  different one. Giving them a common shape would mean inventing one, which ADR-003 forbids of an
  adapter
- ADR-018's shape survives its supersession: acquisition and release remain one async context
  manager and paired hooks remain rejected. Only the owner changes
- `docs/roadmap.md` M6 asks that the "runtime transitions through the defined lifecycle states
  predictably". That criterion is superseded rather than unmet, the roadmap is not edited, and
  the owner approved the departure
