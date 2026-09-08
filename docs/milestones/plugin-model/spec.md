# Plugin Model: Design

This is not a roadmap milestone. It is a structural correction of what M5A and M6 delivered,
taken before M8 because M8 builds directly on the model it changes. `docs/roadmap.md` is not
edited; ADR-020 records how its existing wording is to be read.

## Acceptance criteria

No roadmap entry owns this change, so its criteria are stated here.

- a plugin that is not running is not representable: no framework object stands for one, and no
  framework error guards access to one
- each channel obtains its runtime from the mechanism its own host documents, and the framework
  adds no lifecycle of its own
- a `PluginDefinition` is a value that can be read without running it, and declares no resource
  factory
- the application-scoped resource still reaches a handler only through `ToolContext`, typed by a
  parameter the plugin supplies
- the two constitutional tests survive, with the dual-channel test's claim restated to what
  ADR-017 makes true
- `make lint typecheck test` passes

## Sources

| Contract | Source |
| --- | --- |
| each channel runs in its own OS process; an app-scoped resource must be share-nothing | `docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md` |
| the agent platform spawns the MCP server process; building a server is not running one | `docs/decisions/ADR-010-agent-platform-owns-the-mcp-process.md` |
| the resource reaches a handler through ToolContext, typed by the app | `docs/decisions/ADR-013-dependencies-reach-handlers-through-tool-context.md` |
| acquisition and release are one async context manager, not paired hooks | `docs/decisions/ADR-018-app-scoped-resource-is-an-async-context-manager.md` |
| adapters translate a protocol and own no business logic | `docs/decisions/ADR-003-channel-adapters-are-thin.md` |
| the NiceGUI adapter registers routes and runs no server | `docs/decisions/ADR-012-nicegui-adapter-registers-routes.md` |
| runtime lifecycle and package lifecycle are separate | `docs/decisions/ADR-006-runtime-vs-package-lifecycle.md` |
| a framework error carries a stable code; a retired code is never reused | `docs/architecture/errors.md`, `docs/decisions/ADR-019-framework-errors-carry-stable-codes.md` |
| a Page reaches Tools through one named operation | `docs/decisions/ADR-016-tool-invocation-has-one-name.md` |
| pre-release removal without a deprecation path has precedent | `docs/decisions/ADR-016-tool-invocation-has-one-name.md` |
| `Server(lifespan=...)` is entered once when the server starts and exited once when it stops; whatever it yields becomes `ctx.lifespan_context` | <https://py.sdk.modelcontextprotocol.io/v2/api/mcp/server/lowlevel/server> |
| `ui.run_with(fastapi_app, mount_path=...)` mounts NiceGUI as a sub-application | <https://github.com/zauberzeug/nicegui/blob/main/nicegui/llms.md> |
| NiceGUI documents `app.on_startup`/`app.on_shutdown` and no lifespan | <https://nicegui.io/documentation/section_action_events> |
| NiceGUI runs as a single process; module-level variables are shared across all users | <https://github.com/zauberzeug/nicegui/blob/main/README.md> |
| request state is a shallow copy of lifespan state; propagation into a mounted sub-application is not documented | <https://github.com/kludex/starlette/blob/main/docs/lifespan.md> |
| an AsyncExitStack registers a release only after its acquisition returns and unwinds in reverse | <https://github.com/python/cpython/blob/main/Doc/library/contextlib.rst> |

## Problem

Three findings, each established against the sources above.

**The App has no substance.** It is not the packaging unit — a package is. It is not the
execution unit — ADR-017 makes that the channel process. It is not a dependency scope — the
lifespan is. `AppDefinition` is a real declaration wearing the wrong name; `AppRuntime` is an
object with nothing left to be.

**The framework made an illegal state representable and then guarded it.** An `AppRuntime`
exists while CREATED and while STOPPED, so `tool_runtime` and `page_runtime` must refuse to
answer outside the running window. `AppRuntimeState`, `AppRuntimeTransitionError`,
`AppRuntimeNotRunningError`, the transition checks and `tests/lifecycle.py::started` are all the
cost of that one choice. Both channel hosts already bind a running window to a block, where the
state cannot be reached because the object does not yet exist.

**`lifespan` is not a declaration.** It is a factory — an assembly step — sitting inside a frozen
value whose whole purpose is to be read without running. Everything else in an `AppDefinition`
is inspectable; this field is opaque by construction.

ADR-015 rests on a premise ADR-017 refutes: two adapters of one App cannot receive the same
`AppRuntime` instance when they run in different processes.

## Governing principle

> Static state is read from the `PluginDefinition`. Dynamic state is read from the host's own
> running window.

Nothing in the framework spans the two.

## The Plugin

`PluginDefinition` is what `AppDefinition` was, minus the factory and under the name that
describes it. `App` leaves the vocabulary entirely: nothing it named survives without a better
name.

The definition stays generic in `DepsT`. It declares that its Tools require a resource of that
type; it does not declare where one comes from. The composition root supplies it, and the type
checker rejects a mismatch at that one site.

## The composition root

An entrypoint pairs a definition with a lifespan. That is the only place the two meet, and it is
package metadata rather than framework behaviour, which is where ADR-010 already puts an
entrypoint. Nothing is lost for inspection: Tools and Pages remain values in the definition, and
`DepsT` was never inspectable — ADR-013's requirement is satisfied exactly as before.

The framework supplies two async context managers. Each yields the one runtime its channel needs
and nothing more, which is narrower than the five properties `AppRuntime` exposed to both.

## What each channel does

The two channels are deliberately asymmetric, because each uses the mechanism its own host
documents. Forcing a common shape would mean inventing one.

**Agent channel.** The MCP SDK documents a lifespan on `Server` and documents that what it
yields becomes `ctx.lifespan_context`. The adapter passes one, the handler reads it, and the
server's type becomes `Server[ToolRuntime[DepsT]]`. `_no_lifespan` disappears: it existed only to
keep `Any` out of the return type, and a real lifespan now carries a real type.

**Web channel.** NiceGUI documents no lifespan. It mounts as a sub-application under
`ui.run_with`, and Starlette does not document lifespan state reaching a mounted sub-application,
so reading the resource from `request.state` would depend on undocumented behaviour.

It is not needed. A page builder already closes over its runtime today. Registration happens
inside the running block, and the closure holds the runtime for as long as the block lasts:

```python
async with page_runtime_for(TODO, todo_lifespan) as pages:
    register_pages(TODO, pages)
    await serve()
```

The block is the running window. Outside it there is no runtime to reach and no route
registered, so the same property the Agent channel gets from the SDK is obtained here from the
language, with no undocumented dependency. ADR-012 is untouched: the adapter still registers
routes and runs no server, and how to serve is the entrypoint's decision.

## Package layout

```text
src/vibepy/
  plugin/
    __init__.py        PluginDefinition
    model.py           PluginDefinition
    composition.py     Lifespan, tool_runtime_for, page_runtime_for
  tool/                unchanged
  page/                unchanged
  errors.py            two exceptions and one category retired
  adapters/
    mcp/server.py      build_mcp_server(definition, lifespan)
    nicegui/web.py     register_pages(definition, pages)
```

`src/vibepy/app/` and `src/vibepy/lifecycle.py` are deleted.

## Public API

```python
@dataclass(frozen=True)
class PluginDefinition[DepsT]:
    plugin_id: str
    name: str
    version: str
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]


type Lifespan[DepsT] = Callable[[], AbstractAsyncContextManager[DepsT]]


def tool_runtime_for[DepsT](
    definition: PluginDefinition[DepsT], lifespan: Lifespan[DepsT], /
) -> AbstractAsyncContextManager[ToolRuntime[DepsT]]: ...


def page_runtime_for[DepsT](
    definition: PluginDefinition[DepsT], lifespan: Lifespan[DepsT], /
) -> AbstractAsyncContextManager[PageRuntime]: ...


def build_mcp_server[DepsT](
    definition: PluginDefinition[DepsT], lifespan: Lifespan[DepsT], /
) -> Server[ToolRuntime[DepsT]]: ...


def register_pages[DepsT](
    definition: PluginDefinition[DepsT], pages: PageRuntime, /
) -> None: ...


@dataclass(frozen=True)
class ToolContext[DepsT]:
    plugin_id: str
    invocation_id: str
    dependencies: DepsT
```

Removed: `AppDefinition`, `AppRuntime`, `AppRuntimeState`, `AppRuntimeTransitionError`,
`AppRuntimeNotRunningError`, `ErrorCategory.LIFECYCLE`.

## Data flow

```text
Agent channel process, launched by the MCP client
  PluginDefinition ──static──▶ ToolRegistry ──▶ list_tools
  lifespan ──▶ DepsT ──▶ ToolRuntime ──▶ ctx.lifespan_context ──▶ call_tool ──▶ Tool

Web channel process, launched by the Hub
  PluginDefinition ──static──▶ route validation ──▶ ui.page
  lifespan ──▶ DepsT ──▶ ToolRuntime ──▶ PageRuntime ──closure──▶ builder ──▶ Page ──▶ Tool
```

## Errors

Two codes are retired and never reused, and the category that held them becomes empty and is
removed with them.

| Retired | Reason |
| --- | --- |
| `lifecycle.transition_forbidden` | no state machine exists to forbid a transition |
| `lifecycle.not_running` | a runtime that is not running is not reachable |
| `ErrorCategory.LIFECYCLE` | no code maps to it |
| `app.unhandled` | replaced by `plugin.unhandled`; App leaves the vocabulary |

A lifespan that fails now propagates to its host, which is what the host's own contract already
covers. The framework neither classifies nor wraps it.

The remaining six codes and their categories are unchanged.

## Testing

| File | Change |
| --- | --- |
| `tests/test_app_lifecycle.py` | deleted; the state-machine tests describe states that no longer exist |
| `tests/test_plugin_composition.py` | new; keeps the lifespan tests worth keeping — the window's two sides, what a Tool receives, isolation between two compositions, an earlier resource released when a later one fails, a failure reaching the caller |
| `tests/test_app_runtime.py` | renamed and rewritten against `tool_runtime_for` |
| `tests/test_dual_channel.py` | claim restated: both channels reach one Tool implementation over one resource when composed over one. Sharing is a property of the composition, not a framework guarantee |
| `tests/test_execution_semantics.py` | fixture rewiring only; the barrier proof is unchanged |
| `tests/test_mcp_adapter.py` | fixture rewiring; `test_the_core_packages_do_not_import_mcp` follows `app/` to `plugin/` |
| `tests/test_nicegui_adapter.py` | fixture rewiring |
| `tests/test_errors.py` | catalogue shrinks by two |
| `tests/test_package.py` | `__all__` |
| `tests/lifecycle.py` | `started` deleted; `no_dependencies` kept |
| `tests/todo_fixture.py` | exports a `PluginDefinition` and a lifespan instead of a built runtime |

The count of tests falls. That is the deliverable, not a regression: the deleted tests assert
transitions of a machine this design removes.

## Compatibility

The public API changes without a deprecation path. The framework is pre-release and has no
consumer outside this repository, which is the ground ADR-016 already took for a smaller
rename.

## Documentation

Three ADRs are written and three are superseded.

| ADR | Action |
| --- | --- |
| ADR-020 the Plugin replaces the App | new; supersedes ADR-004 |
| ADR-021 the channel host owns the runtime lifecycle | new; supersedes ADR-015 and ADR-018 |
| ADR-022 a declaration holds no resource factory | new |

ADR-021 carries forward the statements of ADR-006 and ADR-012 whose wording names `AppRuntime`,
and records the two things ADR-017 left unsaid: a lifespan is entered once per channel process,
and ADR-015's premise is destroyed. ADR-020 records how `docs/roadmap.md`'s existing "App",
"AppDefinition" and "App Package" are to be read, and that M6's state-machine acceptance
criterion is superseded rather than unmet.

Ten documents change: `docs/architecture.md`; `app-model.md` renamed to `plugin-model.md`;
`lifecycle.md`, `runtime.md`, `adapters.md`, `errors.md`, `tool-model.md`, `page-model.md`,
`authoring.md`; and four invariants in `AGENTS.md`.

## Out of scope

- per-invocation resource scope. The framework has no equivalent of a request-scoped dependency,
  which no milestone has yet required and which M8 should decide
- typed plugin configuration and what a plugin may declare about its host (M8)
- how an entrypoint is declared, resolved and loaded from a package (M9)
- the Hub's own process management (M10) and the Hub UI affordance for a plugin with no Web
  channel (M11)
- capability declaration across plugins (M19)
