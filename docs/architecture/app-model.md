# App Model

## Definition

An App is the unit of packaging and declaration. It is what a Hub installs, removes and
updates, and what a channel is opened over. It is not a unit of execution: ADR-017 puts each
channel of an installed App in its own operating-system process, so what runs is a channel.

```text
AppDefinition + lifespan -> a channel's running window
```

`docs/architecture/packaging.md` owns the layer above the definition: how a distribution says
which App it contains, and how a reader learns that without importing it.

## The import surface

An App author reaches for `vibepy_core`, the package root: `tests/test_package.py` holds its
exact contents, so a name that is not exported there is not public. The subpackages beneath it —
`vibepy_core.tool`, `.page`, `.app`, `.errors` — are how the framework is organised, and they keep
working for anything already written against them. A module whose handlers must never reach a
blocking call (`docs/architecture/runtime.md` says why) imports the narrower subpackage instead of
the root that re-exports it; the Hub's Tool modules are that case, held by
`packages/vibepy-hub/tests/test_no_blocking_handlers.py`.

## AppDefinition

`AppDefinition` is static and declarative. A frozen dataclass, generic in the app's own
dependency type:

```python
@dataclass(frozen=True)
class AppDefinition[DepsT, ConfigT: BaseModel]:
    app_id: str
    name: str
    version: str
    config: type[ConfigT]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
```

`DepsT` is the app's own type for its application-scoped resource. The definition declares
that its Tools require one of that type; it does not declare where one comes from. An App whose
Tools need no resource declares `AppDefinition[None, ...]`; no default is provided, because the
framework does not guess that an App is stateless.

`config` is the other kind of type: a Pydantic model stating what this App requires of its host.
It is readable without acquiring anything, and it is required — an App that requires nothing
declares `NoConfig`, an empty model. See
`docs/decisions/ADR-022-configuration-is-a-declaration.md`.

A definition contains no live connections, no request state, no UI sessions and no running
adapters, and no factory for any of them. It is a value, so a later milestone can read it without
running it. See `docs/decisions/ADR-021-a-declaration-holds-no-resource-factory.md`.

## The running window

A channel obtains its runtime from an async context manager that pairs a definition with a
lifespan. The window is the block; there is no object for an App that is not running, and
therefore no state to inspect and no error to raise for reaching one.

```python
type Lifespan[DepsT, ConfigT] = Callable[[ConfigT], AbstractAsyncContextManager[DepsT]]

def tool_runtime_for[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> AbstractAsyncContextManager[ToolRuntime[DepsT]]: ...

def page_runtime_for[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> AbstractAsyncContextManager[PageRuntime]: ...
```

`tool_runtime_for` is the invocation window and belongs to no channel: every channel reaches
Tools through it. The Agent channel adds nothing to it and hands it to its server's lifespan.
`page_runtime_for` is the Web channel's window, and it is that same window with a PageRegistry
over it, so configuration is validated once and a resource acquired once. Registries are built
from declarations alone, so they are made before the resource is acquired. `config` is a raw mapping the window validates
against the declaration before it enters the lifespan, so a window that cannot run acquires
nothing; the lifespan receives the validated model. Two windows over one definition are
isolated by default: each enters its own lifespan.

The resource itself is never exposed. A Tool handler receives it through its ToolContext, and
nothing else needs it. `docs/architecture/lifecycle.md` owns the boundaries of the window, and
`docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md` records why the framework
owns no lifecycle of its own.

## The composition root

A definition and a lifespan meet in an entrypoint, and nowhere else. That entrypoint is package
metadata rather than framework behaviour, which is where ADR-010 already places one.

An installed App has one entrypoint per channel it offers. The Web channel's is what the operator
runs: `python -m vibepy_core.serve`, which `docs/architecture/packaging.md` owns. The Agent
channel has no command today — nothing in this repository declares a console script, and an
Agent-only App is therefore reachable only by a host that opens the channel itself. An App
declaring no Pages has no Web channel.

## State ownership

Three scopes are distinguished.

### Application scope

Owned by the channel's running window:

- repository instances
- DB connection pools
- API clients
- immutable or typed application configuration

An installed App runs one window per channel, so an application-scoped resource must be
share-nothing. A pool, a client and configuration qualify. An authoritative in-memory cache, a
scheduler, and a store that admits one writer do not: they belong in a backing service. See
`docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md`.

### Session scope

Owned by Web/Page session:

- current filter
- selected tab
- temporary form draft
- navigation/UI state

### Invocation scope

Owned by ToolContext. `docs/architecture/runtime.md` describes what a ToolContext carries, now
and later.

There is no per-invocation *resource* scope, and there will not be one. A ToolContext carries
the application-scoped value and nothing acquired and released around one invocation. Adding a
second resource mechanism beside ToolContext would put two answers in the codebase to the
question of where a handler's resource comes from, which is what ADR-013 settled. An App that
needs a session per call takes one from the pool its application-scoped resource holds. See
`docs/decisions/ADR-022-configuration-is-a-declaration.md`.

## Invariants

- AppDefinition is static metadata and declarations, and holds no factory.
- An App declares what it requires of its host as a type, and a window validates against that
  declaration before it acquires anything.
- A declaration is not a running channel.
- ToolRuntime and PageRuntime exist only inside a window.
- Page/session state must not leak into application-scoped state.
- Tool handlers must not receive unrestricted access to a window's internals. A handler receives
  one value of a type the app itself declared. See
  `docs/decisions/ADR-013-dependencies-reach-handlers-through-tool-context.md`.
