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

The package root is the App author's vocabulary, and nothing else: what an author declares, what
a declaration is described as, and what the framework raises. `tests/test_package.py` holds its
exact contents, so a name that is not exported there is not public. The subpackages beneath it —
`vibepy_core.tool`, `.page`, `.app`, `.errors` — are how the framework is organised, and they
follow the same rule.

An operation a host performs is not vocabulary, and is reached at its own module: discovery and
loading at `vibepy_core.app.package`, the environment's configuration at `vibepy_core.app.config`,
the entry point group at `vibepy_core.app.group`, reporting at `vibepy_core.errors`. A boundary
model lives with the vocabulary it is made of, never with the command that transports it —
`InvocationRequest` in `vibepy_core.tool`, `DescribedApp` beside the `AppDescription` it wraps.
Together these mean importing the root, or any aggregating subpackage, never brings a blocking
loader with it, so a module whose handlers must never reach a blocking call
(`docs/architecture/runtime.md` says why) cannot reach one by accident. ADR-035 says why.

## AppDefinition

`AppDefinition` is static and declarative. A frozen dataclass, generic in the app's own
dependency type:

```python
@dataclass(frozen=True)
class AppDefinition[DepsT, ConfigT: AppConfig]:
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

`config` is the other kind of type: an `AppConfig` subclass stating what this App requires of its
host. It is readable without acquiring anything, and it is required — an App that requires
nothing declares `NoConfig`, an empty one. Where the values come from is the environment a
process runs in, which `docs/architecture/packaging.md` owns. See
`docs/decisions/ADR-022-configuration-is-a-declaration.md` and
`docs/decisions/ADR-033-configuration-reaches-a-process-through-the-environment.md`.

A definition contains no live connections, no request state, no UI sessions and no running
adapters, and no factory for any of them. It is a value, so a later milestone can read it without
running it. See `docs/decisions/ADR-021-a-declaration-holds-no-resource-factory.md`.

## The running window

A channel obtains its runtime from an async context manager that pairs a definition with a
lifespan. The window is the block; there is no object for an App that is not running, and
therefore no state to inspect and no error to raise for reaching one.

```python
type Lifespan[DepsT, ConfigT] = Callable[[ConfigT], AbstractAsyncContextManager[DepsT]]

def tool_runtime_for[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> AbstractAsyncContextManager[ToolRuntime[DepsT]]: ...

def page_runtime_for[DepsT, ConfigT: AppConfig](
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
from declarations alone, so they are made before the resource is acquired. `config` is a raw mapping of explicit values; the window
instantiates the declaration with it, so the declaration's own reading of the environment fills
in the rest and a window that cannot run acquires nothing. The lifespan receives the instance. Two windows over one definition are
isolated by default: each enters its own lifespan.

The resource itself is never exposed. A Tool handler receives it through its ToolContext, and
nothing else needs it. `docs/architecture/lifecycle.md` owns the boundaries of the window, and
`docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md` records why the framework
owns no lifecycle of its own.

## The composition root

A definition and a lifespan meet in an entrypoint, and nowhere else. That entrypoint is package
metadata rather than framework behaviour, which is where ADR-010 already places one.

An installed App has one entrypoint per channel it offers. The Web channel's is what the operator
runs: `python -m vibepy_core.serve`, and the Agent channel's is `python -m vibepy_core.mcp`;
`docs/architecture/packaging.md` owns both. An App declaring no Pages has no Web channel.

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
