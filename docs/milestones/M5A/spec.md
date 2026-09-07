# M5A - AppRuntime and shared state: Design

## Goal

Give the App an owner. `docs/roadmap.md` sets the deliverables:

- AppDefinition
- AppRuntime
- application-scoped typed dependencies
- ToolContext creation from AppRuntime

and the acceptance criteria:

- Web-like and Agent-like calls share the same AppRuntime state
- a second AppRuntime is isolated by default

## Problem

`tests/todo_fixture.py::build_todo_app` performs work the framework does not offer: it
constructs the app's shared `TodoStore`, binds it into handlers, fills two registries and
wires two runtimes. M1 through M4 were built on the assumption that an App is already
assembled, and nothing owns the assembly.

The shared store is a local variable of a test helper. `docs/architecture/app-model.md`
assigns it to AppRuntime, which does not exist.

## Non-goals

- **Runtime lifecycle.** `CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED`, `on_start`
  and `on_stop` are M6. `AppRuntime` here has a constructor and no state machine.
- **Typed configuration.** M8. `AppDefinition` gains no config model.
- **Manifest, entrypoint, package loading.** M9. `AppDefinition` is constructed in Python
  by the app, not loaded from metadata.
- **Concurrency semantics.** M5B. Nothing here serializes invocations, and nothing here
  proves that it does not.
- **Per-App process isolation.** M17. Two AppRuntimes in one process share NiceGUI's
  process-global route table, as ADR-012 records.
- **A Todo sample package.** Todo stays a test fixture, as it is for M3 and M4.

## Decision: how a handler reaches app-scoped state

Two mechanisms are available.

**Closures.** The app binds its store into handlers at assembly, as `build_todo_app` does
today with `handler=store.create`. `ToolContext` is unchanged.

**ToolContext.** The app declares a factory for its shared resource, handlers are
module-level functions, and the resource arrives as `ctx.dependencies`.

ToolContext is chosen.

`docs/architecture/runtime.md` already reserves the position: a ToolContext may hold "app
id, invocation id, typed app services/config when required", and dependency ownership
should prefer "typed dependency objects over generic dictionaries". Under closures both
M5A deliverables named after it are vacuous — `ToolContext` would not change, and the
framework would hold no type for an app-scoped dependency.

The deciding argument is `docs/architecture/app-model.md`: an AppDefinition holds "Tool
declarations" and "Page declarations" and "should not contain live connections". A handler
bound to a live `TodoStore` puts a live object inside the declaration. It also makes an App
a procedure rather than a value, and `docs/architecture/authoring.md` requires the opposite:
`inspect_app` and `validate_app` (M12), package validation (M9) and conformance validation
(M16) read an App's declarations without running it.

Handlers still receive no access to AppRuntime. They receive one value of a type the app
itself declares, which is what "Tool handlers must not receive unrestricted access to
AppRuntime internals" asks for.

## Type parameter

`DepsT` is the app's own type for its shared resource. It threads through `ToolContext`,
`ToolHandler`, `Tool`, `ToolRegistry`, `ToolRuntime`, `AppDefinition` and `AppRuntime`.

ADR-008's variance problem does not recur. That problem arises because each Tool has its
own `InputT`; `DepsT` is one type per App, so a `ToolRegistry[DepsT]` holds uniformly typed
values. No `Any` and no `cast`.

The Page model is untouched. A Page reaches the domain only through Tools (ADR-002), and
`ToolInvoker` takes a name and a raw mapping, so `DepsT` has no position in `PageContext`,
`PageRuntime` or `PageRegistry`.

An app with no shared resource uses `DepsT = None` and `create_dependencies=lambda: None`.
No default is provided; the framework does not guess that an App has no state.

## Public API

### Tool model

```python
@dataclass(frozen=True)
class ToolContext[DepsT]:
    app_id: str
    invocation_id: str
    dependencies: DepsT


class ToolHandler[DepsT, InputT: BaseModel, OutputT: BaseModel](Protocol):
    def __call__(self, ctx: ToolContext[DepsT], payload: InputT, /) -> Awaitable[OutputT]: ...
```

`ToolDefinition` is unchanged.

### Tool carries its bound callable

`AppDefinition` holds a sequence of Tools, so every element must share one static type.
`Tool[DepsT, InputT, OutputT]` cannot: `InputT` appears covariantly in `definition` and
contravariantly in `handler`, making `Tool` invariant in it, which is ADR-008's problem in
a new position.

Binding already erases those parameters. It moves from `ToolRegistry.register` into `Tool`
itself:

```python
class Tool[DepsT]:
    def __init__[InputT: BaseModel, OutputT: BaseModel](
        self,
        *,
        definition: ToolDefinition[InputT, OutputT],
        handler: ToolHandler[DepsT, InputT, OutputT],
    ) -> None: ...

    definition: ToolDefinition[BaseModel, BaseModel]
    bound: BoundTool[DepsT]
```

A generic `__init__` on a non-generic-in-`InputT` class, so the call site is unchanged:
`Tool(definition=..., handler=...)` still reads as a declaration and `DepsT` is inferred
from the handler. `Tool` moves from `tool/model.py` to `tool/runtime.py`, because it now
carries invocation behaviour and `tool/model.py` declares that its types do not.

The alternative is a separate factory function over a frozen dataclass, which is more
obvious to a reader but adds a second name for one concept. The generic `__init__` is
chosen because it keeps one name and leaves every existing declaration site untouched; it
is PEP 695 syntax rather than metaprogramming, so AGENTS.md's preference for explicit
implementations is not in tension. Inference was verified against pyright in strict mode:
`Tool(definition=..., handler=create_todo)` resolves to `Tool[TodoStore]` and registers
into a `ToolRegistry[TodoStore]` with no diagnostics.

`ToolRegistry[DepsT]` therefore stores one dictionary of `Tool[DepsT]` instead of a
dictionary of bound callables plus a dictionary of declarations, and the free function
`bind` disappears. `definitions()` is unchanged.

### Tool runtime

```python
class ToolRuntime[DepsT]:
    def __init__(
        self, *, app_id: str, registry: ToolRegistry[DepsT], dependencies: DepsT
    ) -> None: ...

    async def invoke(self, name: str, raw_input: Mapping[str, object]) -> BaseModel: ...
```

`invoke` resolves the Tool, constructs
`ToolContext(app_id=..., invocation_id=uuid4(), dependencies=self._dependencies)` and awaits
`tool.bound`. Context creation stays here: it is the single invocation path every channel
converges on, and `docs/architecture/runtime.md` requires that channels never construct a
context. What AppRuntime supplies is the app-scoped content of that context.

### App model

```python
@dataclass(frozen=True)
class AppDefinition[DepsT]:
    app_id: str
    name: str
    version: str
    create_dependencies: Callable[[], DepsT]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
```

Static and reusable. `create_dependencies` is a factory rather than an instance, so one
definition yields independently isolated runtimes, which is ADR-004's stated consequence and
this milestone's second acceptance criterion.

```python
class AppRuntime[DepsT]:
    def __init__(self, definition: AppDefinition[DepsT]) -> None: ...

    @property
    def definition(self) -> AppDefinition[DepsT]: ...
    @property
    def tool_registry(self) -> ToolRegistry[DepsT]: ...
    @property
    def tool_runtime(self) -> ToolRuntime[DepsT]: ...
    @property
    def page_registry(self) -> PageRegistry: ...
    @property
    def page_runtime(self) -> PageRuntime: ...
```

The constructor calls `create_dependencies()` once, fills a `ToolRegistry` and a
`PageRegistry` from the declarations, and builds the two runtimes over them. Dependencies
are created in the constructor because M5A has no lifecycle;
`docs/architecture/lifecycle.md` places their initialization at startup step 2, so M6 moves
*when* the factory is called without changing its signature. This is a known seam.

Module layout follows `tool/` and `page/`:

```text
src/vibepy/app/
├── __init__.py   # re-exports AppDefinition, AppRuntime
├── model.py      # AppDefinition
└── runtime.py    # AppRuntime
```

### Channel adapters

```python
def build_mcp_server[DepsT](app: AppRuntime[DepsT]) -> Server[None]: ...
def register_pages[DepsT](app: AppRuntime[DepsT]) -> None: ...
```

`docs/architecture/app-model.md` requires that both adapters for one running app receive the
same AppRuntime instance. Passing the AppRuntime makes that a type-level guarantee and
removes a defect the current signatures permit: a registry and a runtime that do not belong
together. The MCP server's name and version come from `AppDefinition`, so
`build_mcp_server` loses three parameters and gains one. Adapter behaviour is otherwise
unchanged; `app_id` is the MCP server name, because it is the stable identifier.

The roadmap does not ask for this. It is included because both signatures have to change
regardless — their registry and runtime parameters become generic in `DepsT` — and leaving
them as two parameters would keep a pairing the type system cannot check.

## Errors

No new exception types. Duplicate Tool names replace, as the registry already documents;
duplicate Page routes are rejected by the Web adapter, as ADR-012 already requires.

## Testing

`tests/test_app_runtime.py`:

- two AppRuntimes built from one AppDefinition: a Tool call on the first is invisible to a
  read on the second — the isolation criterion
- an Agent-like and a Web-like call through one AppRuntime observe each other's state
  without a channel adapter — the sharing criterion at the runtime level
- a handler receives the resource produced by `create_dependencies`, and the same instance
  on every invocation

`tests/test_dual_channel.py` is rewired through `AppRuntime` and keeps asserting exactly
what it asserts today. It is constitutional; the milestone changes how it is built, not what
it proves.

`tests/test_tool_core.py`, `tests/test_mcp_adapter.py` and `tests/test_nicegui_adapter.py`
are updated for the new construction, not extended.

`tests/todo_fixture.py` is rewritten: `build_todo_app` returns an `AppRuntime[TodoStore]`,
the `TodoApp` dataclass disappears, handlers become module-level functions taking
`ToolContext[TodoStore]`, and `TodoStore.create`/`list_all` become plain domain methods that
no longer imitate a handler signature.

Done when `make lint typecheck test` passes.

## Compatibility

`ToolContext` gains a required field and a type parameter, and both adapter functions change
signature. Existing handlers keep their shape; `Tool(definition=..., handler=...)` keeps its
call site. The package is at version `0.0.0` and M5A is by definition the milestone that
introduces app-scoped state into the Tool contract, so the change is made directly rather
than deprecated. AGENTS.md's backward-compatibility rule starts applying to the surface this
milestone leaves behind.

## Documentation

Updated: `docs/architecture/app-model.md` (AppDefinition and AppRuntime become concrete),
`docs/architecture/tool-model.md` (ToolContext, Tool, ToolRegistry),
`docs/architecture/runtime.md` (dependency ownership, context creation),
`docs/architecture/adapters.md` (adapters are constructed from an AppRuntime).

New ADRs:

- app-scoped dependencies reach handlers through ToolContext, against closures bound at
  assembly
- a Tool carries its own bound callable, superseding ADR-011
- channel adapters are constructed from an AppRuntime
