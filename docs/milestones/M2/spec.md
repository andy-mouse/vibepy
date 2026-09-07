# M2 - Page Core: Design

## Scope

`docs/roadmap.md` M2 lists seven objects: PageDefinition, Page, PageHandler Protocol,
PageContext, ToolInvoker, PageRegistry, PageRuntime.

Acceptance: a test Page invokes an existing Tool through the narrow ToolInvoker interface.

Nothing else is built. No NiceGUI, no routing, no session state, no AppRuntime.

## Sources

Every contract below either comes from a repository document or is an open decision that
was decided with the owner. Nothing is invented.

| Contract | Source |
| --- | --- |
| `PageDefinition + PageHandler -> Page` | `docs/architecture/page-model.md` |
| PageDefinition fields: name, route, title | `docs/architecture/page-model.md` ("Minimal initial metadata") |
| `Page -> PageContext -> ToolInvoker -> ToolRuntime -> Tool` | `docs/architecture/page-model.md` |
| `await ctx.tools.call(name, input)` as the narrow interface | `docs/architecture/page-model.md` |
| PageContext must not expose unrestricted AppRuntime internals | `docs/architecture/page-model.md` |
| Pages do not bypass Tools for business state changes | `docs/decisions/ADR-002-pages-consume-tools.md` |
| Session state is session-scoped, not application-scoped | `docs/architecture/app-model.md` |
| The adapter enumerates PageDefinitions to register Web routes | `docs/architecture/adapters.md` |
| NiceGUI types must not leak into the core Page model | `docs/architecture/adapters.md`, ADR-003 |
| `invoke(name, raw_input)` returns the validated output model | `docs/architecture/tool-model.md` |
| A channel never constructs the invocation context itself | `docs/architecture/runtime.md` |

Three questions no document answered were decided with the owner:

1. PageHandler returns `None`. See "PageHandler" below.
2. PageContext carries no session state in M2. See "PageContext" below.
3. PageRegistry is keyed by name and also enumerates. See "PageRegistry" below.

## Package layout

```text
src/vibepy/page/
├─ __init__.py    public exports
├─ model.py       PageDefinition, Page, PageHandler, PageContext, ToolInvoker
├─ registry.py    PageRegistry
└─ runtime.py     PageRuntime, the ToolRuntime-backed ToolInvoker
```

This mirrors `src/vibepy/tool/`. `PageNotFoundError` joins the existing exceptions in
`src/vibepy/errors.py`, deriving from `VibepyError`.

## Contracts

### PageDefinition

A frozen dataclass with `name`, `route` and `title`, all required strings.

`name` is the stable identifier the framework addresses a Page by. `route` and `title` are
stored and unused in M2; the NiceGUI adapter consumes them in M4. Their formats are not
validated here, because the channel that gives them meaning does not exist yet.

### PageHandler

A Protocol whose single positional-only parameter is a PageContext, returning an
awaitable of `None`.

```python
class PageHandler(Protocol):
    def __call__(self, ctx: PageContext, /) -> Awaitable[None]: ...
```

Positional-only mirrors `ToolHandler`, so an app author may name the parameter freely.

`None` rather than a render result: NiceGUI page builders construct their UI by side
effect, and NiceGUI discards a builder's return value unless it is a `fastapi.Response`
([nicegui/page.py](https://github.com/zauberzeug/nicegui/blob/main/nicegui/page.py), which
returns `result` only `if isinstance(result, Response)` and logs a late return value as
ignored). A generic render type would therefore be a contract no channel reads. A
`Response` passthrough is rejected instead because `fastapi.Response` is a Web channel
type, and `docs/architecture/adapters.md` keeps channel types out of the core Page model;
if returning a response becomes necessary, M4 owns it at the adapter boundary. Navigation
inside a page is a side effect in NiceGUI as well (`ui.navigate.to`).

### Page

A frozen dataclass pairing a PageDefinition with its PageHandler.

Page is not generic. A Tool is generic over its input and output models, which is why
ADR-008 binds each Tool into a uniform callable before storing it by name. A PageHandler
takes only a PageContext and declares no models, so every Page already has one static
type and the registry stores it directly. No binding step exists in the Page package.

### ToolInvoker

A Protocol with one method, the narrow interface `page-model.md` asks for:

```python
class ToolInvoker(Protocol):
    def call(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]: ...
```

The signature is `ToolRuntime.invoke`'s: a raw mapping in, a validated output model out.
A Page hands over whatever its form collected and receives the same value the Agent
channel receives. Validation stays wholly inside ToolRuntime, so no second validation path
appears, and serialization remains a channel adapter concern per `tool-model.md`.

`runtime.py` provides the implementation backed by a ToolRuntime. Because ToolInvoker is a
Protocol, `model.py` does not import ToolRuntime: the core Page model depends on the shape
of Tool invocation, not on the Tool runtime.

Tool errors are not translated. `ToolNotFoundError`, `ToolInputValidationError` and
`ToolOutputValidationError` propagate to the caller of the Page unchanged, as do exceptions
raised by a handler. Exception types are the contract.

### PageContext

A frozen dataclass carrying one field, `tools: ToolInvoker`.

Nothing else. `page-model.md` lists ToolInvoker, session state and future identity as
PageContext's capabilities, and the first is the only one M2 delivers. An app id is not
added either: ToolRuntime already holds it for the ToolContext it creates, and no M2
contract reads one from a Page.

No session state. `page-model.md` lists session state among PageContext's eventual
capabilities, but M2's deliverables do not include it and the acceptance criterion does not
need it. The owner of session state is the Web channel, which arrives in M4 — NiceGUI has
`app.storage.*` for exactly these scopes. Adding a store now would mean designing a
session model against no session.

No principal or identity: `page-model.md` marks those future.

PageContext is created by PageRuntime, never by a Page or a channel. `runtime.md`
establishes this for ToolContext ("Channels never construct one"); `adapters.md` says the
NiceGUI adapter "construct[s] PageContext", which M4 satisfies by calling PageRuntime
rather than assembling a context itself.

### PageRegistry

Storage only, mirroring ToolRegistry:

- `register(page)` stores a Page under `page.definition.name`. Registering a name twice
  replaces the earlier registration, as ToolRegistry does.
- `resolve(name)` returns the Page, or raises `PageNotFoundError`.
- `definitions()` returns every registered PageDefinition.

Keyed by name, not by route, because `name` is the identifier that survives a route change
and because keying by route would put Web addressing into a milestone that has no Web
channel. `definitions()` exists for a documented consumer: `adapters.md` requires the
NiceGUI adapter to "project/register PageDefinitions as Web routes", which is enumeration,
not lookup. Route uniqueness is therefore validated in M4, where routes are registered.

The registry implements no invocation semantics.

### PageRuntime

Constructed from a PageRegistry and a ToolRuntime.

```python
async def render(self, name: str) -> None
```

1. resolve the Page by name
2. build the PageContext, with a ToolInvoker backed by the ToolRuntime
3. await the handler

`render` is the name because the operation is "run this Page's human-facing
implementation"; `page-model.md` calls PageHandler the "render implementation".

PageRuntime holds no per-Page state and does not serialize renders, consistent with
ToolRuntime.

## Data flow

```text
render("todos")
  -> PageRegistry.resolve("todos")            -> Page | PageNotFoundError
  -> PageContext(tools=ToolInvoker)           created by PageRuntime
  -> await handler(ctx)
       -> await ctx.tools.call("create_todo", {"title": "milk"})
            -> ToolRuntime.invoke(...)        -> validated output model
```

## Public API

`vibepy.page` exports `Page`, `PageContext`, `PageDefinition`, `PageHandler`,
`PageRegistry`, `PageRuntime` and `ToolInvoker`. `vibepy` re-exports those plus
`PageNotFoundError`, keeping the existing `__all__` sorted.

## Errors

| Error | Raised when |
| --- | --- |
| `PageNotFoundError` | no Page is registered under the requested name |

It derives from `VibepyError` and carries `page_name`, mirroring `ToolNotFoundError`.

No page input validation error exists: a Page declares no input model.

## Testing

`tests/test_page_core.py`, testing public contracts only. The fixture is the Todo sample
from `docs/roadmap.md`: a `create_todo` Tool over an in-memory list, and a Page whose
handler calls it.

1. **Acceptance.** A Page whose handler calls `create_todo` through `ctx.tools.call`, run
   via `PageRuntime.render`, leaves the Todo in the store. This proves the Page reached the
   Tool through ToolInvoker and ToolRuntime.
2. The value a Page receives from `ctx.tools.call` is the Tool's validated output model
   instance.
3. `render` of an unregistered name raises `PageNotFoundError`.
4. A Page calling an unregistered Tool name raises `ToolNotFoundError` unchanged.
5. A Page calling a Tool with input the Tool's model rejects raises
   `ToolInputValidationError` unchanged.
6. An exception raised by a PageHandler propagates unchanged.
7. Registering two Pages under one name leaves the later Page registered.
8. `definitions()` returns the registered PageDefinitions.
9. A PageContext exposes no way to reach ToolRuntime or a registry: the acceptance test
   reaches the Tool through `ctx.tools` alone.

`make lint typecheck test` passes, with no `Any` and no `cast`.

## Not in M2

Route registration and route uniqueness, `title` rendering, session state, principal or
identity, AppDefinition and AppRuntime, page composition or nesting, navigation, error
pages, NiceGUI, MCP.
