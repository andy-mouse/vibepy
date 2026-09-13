# App Model

## Definition

An App is the unit of packaging and declaration. It is what the operating role installs, removes and
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

A public module declares its surface in `__all__`, and every other module is implementation named
`_x.py`, reachable only from within `vibepy_core`. The public modules are the root,
`vibepy_core.app`, `.tool`, `.page`, `app.config`, `app.package`, `app.group`, `app.entrypoint`,
`errors`, `channel`, `principal`, `logs`, the two adapter packages `adapters.mcp` and
`adapters.nicegui`, and the four command modules `describe`, `invoke`, `serve` and `mcp`. `ruff`'s
`PLC2701` refuses a private import from outside the package, so the boundary is held where an
import is written rather than by a test after the fact (ADR-035, the 2026-09-13 amendment).

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

## Construction validates

An `AppDefinition` that exists conforms. Everything a channel or a host would otherwise have to
check about the shape of a declaration is checked once, as the dataclass is constructed: what
exists is already valid, and there is no half-valid `AppDefinition` to hand around.

`__post_init__` collects every violation rather than raising on the first, so an author sees all
of them at once:

| Check | Violation |
| --- | --- |
| Tool names are unique | name conflict |
| Page names are unique | name conflict |
| every route starts with `/`, and routes are unique | invalid route, route conflict |
| every Page's declared Tool exists and is exposed to `Channel.WEB` | missing, not_exposed |

All of it is raised as one `AppDefinitionInvalidError(app_id, errors)` (`app.declaration_invalid`),
whose members are the individual violations above. `docs/architecture/errors.md` owns how it is
reported. `docs/decisions/ADR-037-an-app-declaration-validates-itself-at-construction.md` records
why validation moved here.

`tool_registry_for`, `page_registry_for` and the NiceGUI adapter's `register_pages` register what
they are given; a window, `describe` and an adapter check nothing.

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

Closing the window writes one `WindowRecord` — the App id, the channel and `closed_at`, one
pydantic model owned by `vibepy_core.app`, read back by `read_window_record` beside it. It is
written by `tool_runtime_for` once the lifespan has exited, so it witnesses the resource being
released, and it is written on a clean exit only: a window that ends by raising crosses as one
report instead (`docs/architecture/errors.md`). Both channels open this window, so both are
observed by the one writer, as `docs/architecture/packaging.md`, "What a command writes to
standard error", records for the stream it lands on.

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
- An AppDefinition that exists conforms; no rule is checked twice.
- ToolRuntime and PageRuntime exist only inside a window.
- Page/session state must not leak into application-scoped state.
- Tool handlers must not receive unrestricted access to a window's internals. A handler receives
  one value of a type the app itself declared. See
  `docs/decisions/ADR-013-dependencies-reach-handlers-through-tool-context.md`.
