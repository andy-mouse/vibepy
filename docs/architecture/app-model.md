# App Model

## Definition

`App` is the top-level unit of application definition, packaging, and runtime composition.

The initial core should distinguish at least:

```text
AppDefinition -> AppRuntime
```

A future distribution layer may introduce:

```text
AppPackage -> AppInstallation -> AppRuntime
```

Do not introduce `AppInstallation` until packaging/Hub work requires it.

## AppDefinition

`AppDefinition` is static and declarative. A frozen dataclass, generic in the app's own
dependency type:

```python
@dataclass(frozen=True)
class AppDefinition[DepsT]:
    app_id: str
    name: str
    version: str
    lifespan: Callable[[], AbstractAsyncContextManager[DepsT]]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
```

`lifespan` is a factory returning an async context manager, not a live one. A definition
holding a live resource would not be a declaration, and one definition would yield runtimes
that shared state. What precedes the `yield` runs at startup and what follows runs at
shutdown; `docs/architecture/lifecycle.md` owns those boundaries.

`DepsT` is the app's own type for its application-scoped resource. An App that has none
declares `AppDefinition[None]` with a lifespan yielding `None`; no default is provided,
because the framework does not guess that an App is stateless.

An AppDefinition does not contain live connections, request state, UI sessions, or running
adapters. Because it is a value rather than an assembly procedure, later milestones can read
it without running the App.

A future version may add an optional config model (M8).

## AppRuntime

`AppRuntime` is the executable instance of an AppDefinition.

```python
class AppRuntime[DepsT]:
    def __init__(self, definition: AppDefinition[DepsT]) -> None: ...

    @property
    def state(self) -> AppRuntimeState: ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

The constructor fills a ToolRegistry and a PageRegistry from the declarations and nothing
else; it acquires no resource. `start()` enters the lifespan and builds a ToolRuntime and a
PageRuntime over the value it yields. Two AppRuntimes built from one AppDefinition are
isolated by default: each enters its own lifespan.

It owns application-scoped runtime state:

- ToolRegistry
- ToolRuntime
- the application-scoped resource
- PageRegistry and PageRuntime
- typed configuration, when M8 introduces it
- lifecycle state

`definition`, `tool_registry` and `page_registry` are readable at any time: they are built
from declarations. `tool_runtime` and `page_runtime` exist only while the App is RUNNING,
because they are built over the resource, and reaching them outside that window raises. The
resource itself is not exposed: a Tool handler receives it through its ToolContext, and
nothing else needs it.

Web and MCP adapters for one running app must receive the same AppRuntime instance, which
their signatures enforce. See
`docs/decisions/ADR-015-adapters-are-built-from-an-app-runtime.md`.

## State ownership

Three scopes are distinguished:

### Application scope

Owned by AppRuntime:

- repository instances
- DB connection pools
- API clients
- shared cache
- immutable or typed application configuration

### Session scope

Owned by Web/Page session:

- current filter
- selected tab
- temporary form draft
- navigation/UI state

### Invocation scope

Owned by ToolContext. `docs/architecture/runtime.md` describes what a ToolContext carries,
now and later.

## Invariants

- AppDefinition is static metadata and declarations.
- AppRuntime is executable state.
- ToolRuntime belongs to AppRuntime.
- AppRuntime is shared by the Web and Agent channels of the same app instance.
- Page/session state must not leak into application-scoped state.
- Tool handlers must not receive unrestricted access to AppRuntime internals. A handler
  receives one value of a type the app itself declared. See
  `docs/decisions/ADR-013-dependencies-reach-handlers-through-tool-context.md`.
