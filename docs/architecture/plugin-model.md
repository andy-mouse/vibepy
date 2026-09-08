# Plugin Model

## Definition

A Plugin is the unit of packaging and declaration. It is what a Hub installs, removes and
updates, and what a channel is opened over. It is not a unit of execution: ADR-017 puts each
channel of an installed Plugin in its own operating-system process, so what runs is a channel.

```text
PluginDefinition + lifespan -> a channel's running window
```

A future distribution layer may introduce a package and an installation above the definition.
Do not introduce either until packaging or Hub work requires it.

## PluginDefinition

`PluginDefinition` is static and declarative. A frozen dataclass, generic in the plugin's own
dependency type:

```python
@dataclass(frozen=True)
class PluginDefinition[DepsT]:
    plugin_id: str
    name: str
    version: str
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
```

`DepsT` is the plugin's own type for its application-scoped resource. The definition declares
that its Tools require one of that type; it does not declare where one comes from. A Plugin whose
Tools need no resource declares `PluginDefinition[None]`; no default is provided, because the
framework does not guess that a Plugin is stateless.

A definition contains no live connections, no request state, no UI sessions and no running
adapters, and no factory for any of them. It is a value, so a later milestone can read it without
running it. See `docs/decisions/ADR-022-a-declaration-holds-no-resource-factory.md`.

A future version may add an optional config model and a statement of what the Plugin requires of
its host (M8).

## The running window

A channel obtains its runtime from an async context manager that pairs a definition with a
lifespan. The window is the block; there is no object for a Plugin that is not running, and
therefore no state to inspect and no error to raise for reaching one.

```python
type Lifespan[DepsT] = Callable[[], AbstractAsyncContextManager[DepsT]]

def tool_runtime_for[DepsT](
    definition: PluginDefinition[DepsT], lifespan: Lifespan[DepsT], /
) -> AbstractAsyncContextManager[ToolRuntime[DepsT]]: ...

def page_runtime_for[DepsT](
    definition: PluginDefinition[DepsT], lifespan: Lifespan[DepsT], /
) -> AbstractAsyncContextManager[PageRuntime]: ...
```

Each yields the one runtime its channel needs. Registries are built from declarations alone, so
they are made before the resource is acquired. Two windows over one definition are isolated by
default: each enters its own lifespan.

The resource itself is never exposed. A Tool handler receives it through its ToolContext, and
nothing else needs it. `docs/architecture/lifecycle.md` owns the boundaries of the window, and
`docs/decisions/ADR-021-the-channel-host-owns-the-runtime-lifecycle.md` records why the framework
owns no lifecycle of its own.

## The composition root

A definition and a lifespan meet in an entrypoint, and nowhere else. That entrypoint is package
metadata rather than framework behaviour, which is where ADR-010 already places one.

An installed Plugin has one entrypoint per channel it offers. The Agent channel's is a command
the MCP client launches; the Web channel's is what the Hub opens. A Plugin declaring no Pages has
no Web channel, and is complete for an agent.

## State ownership

Three scopes are distinguished.

### Application scope

Owned by the channel's running window:

- repository instances
- DB connection pools
- API clients
- immutable or typed application configuration

An installed Plugin runs one window per channel, so an application-scoped resource must be
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

## Invariants

- PluginDefinition is static metadata and declarations, and holds no factory.
- A declaration is not a running channel.
- ToolRuntime and PageRuntime exist only inside a window.
- Page/session state must not leak into application-scoped state.
- Tool handlers must not receive unrestricted access to a window's internals. A handler receives
  one value of a type the plugin itself declared. See
  `docs/decisions/ADR-013-dependencies-reach-handlers-through-tool-context.md`.
