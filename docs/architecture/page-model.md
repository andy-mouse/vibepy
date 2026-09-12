# Page Model

## Definition

A Page is the human-facing interaction composition of an App.

Pages let humans view state, provide input, and invoke the App's canonical backend Tools.

A Page is not itself a NiceGUI-specific primitive. NiceGUI is the current Web channel implementation technology.

## Responsibilities

A Page may own:

- layout and presentation
- form/input collection
- UI/session state
- navigation
- result rendering
- Tool composition

A Page should not own:

- direct database mutation
- direct repository access for business operations
- domain policy enforcement
- duplicated backend business logic
- MCP-specific behavior

## Invocation model

Pages consume Tools through a narrow framework interface.

```text
Page -> PageContext -> ToolInvoker -> ToolRuntime -> Tool
```

A Page invokes a Tool by name and sees nothing of ToolRuntime beyond that one operation:

```python
await ctx.tools.invoke("create_customer", raw_input)
```

## Core objects

The model distinguishes:

```text
PageDefinition + PageHandler -> Page
```

### PageDefinition

Minimal initial metadata:

- name
- route
- title
- tools

`name` is the identifier the framework addresses a Page by, and it is stable across a
route change. `route` and `title` are consumed by the Web channel adapter. Route format,
route uniqueness, and that each declared Tool exists and is exposed to the Web channel are
validated as the `AppDefinition` holding the Page is constructed
(`docs/architecture/app-model.md`).

### PageHandler

Human interaction/render implementation.

Conceptual contract:

```python
async def handler(ctx: PageContext) -> None:
    ...
```

The parameter is positional-only in the `PageHandler` Protocol, so a app author may name
it freely.

A handler returns nothing. A Page builds its interface by side effect, as a NiceGUI page
builder does, and a render result would be a value no channel reads. Returning a Web
response instead is a Web channel concern and belongs to the NiceGUI adapter.

### Page

A PageDefinition paired with the handler that implements it.

Page is not generic. A PageHandler declares no input or output model, so every Page already
shares one static type and needs no binding step before storage. Only a Tool, whose declared
models differ per Tool, needs one.

### ToolInvoker

The narrow interface a Page invokes Tools through.

```python
def invoke(name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]: ...
```

The signature is `ToolRuntime.invoke`'s, name included, so validation stays wholly inside
ToolRuntime and no second validation path exists. ToolInvoker is a Protocol: the core Page
model depends on the shape of Tool invocation, not on the Tool runtime, and the Page package
imports nothing from the Tool package.

ToolRuntime satisfies the Protocol structurally, so nothing stands between a Page and the
canonical invocation path. What a Page can reach is what this Protocol declares: one
operation, addressed by name.

A Page reaches only the Tools its declaration names; any other name is `page.tool_undeclared`,
refused before ToolRuntime. The declaration is an allow-list, and `describe` publishes it.

Tool errors are not translated. `ToolNotFoundError`, `ToolForbiddenError`,
`ToolInputValidationError`, `ToolOutputValidationError` and `PageToolUndeclaredError` reach the
caller of the Page unchanged, as does an exception raised by a PageHandler.
`docs/architecture/errors.md` carries their codes.

### PageContext

Provides Page-scoped capabilities such as:

- ToolInvoker
- session state

Of these, a PageContext currently carries only its ToolInvoker. Session state is owned by
the Web channel, which is where a session exists.

A Page does not see a principal. The ToolInvoker it receives is already bound to the one the
render is for, so a Page invokes as that caller and cannot choose another.

It should not expose unrestricted access to the window's internals.

PageRuntime creates a PageContext. A Page never constructs one, and neither does a channel.

### PageRegistry

Maps a Page name to the Page registered under it. Storage only; it implements no invocation
semantics, and resolution is consumed by PageRuntime.

Registering a name twice replaces the earlier registration.

A declaration carrying one name twice never reaches the registry: the `AppDefinition` refuses it
as it is constructed, because `name` is what the framework addresses a Page by while a
route is the Web channel adapter's.

Resolving a name that was never registered raises `PageNotFoundError`.

### PrincipalToolInvoker

What PageRuntime is constructed over, and what it binds a ToolInvoker from.

```python
def invoke(
    name: str, raw_input: Mapping[str, object], /, *, principal: Principal
) -> Awaitable[BaseModel]: ...
```

This is `ToolRuntime.invoke`'s signature, which ToolRuntime satisfies structurally, so the Page
package still imports nothing from the Tool package: `Principal` and `Channel` belong to
neither and live beside them in `vibepy_core`.

### PageRuntime

Constructed from a PageRegistry and a PrincipalToolInvoker.

`PageRuntime.render(name, *, principal)` resolves the Page, binds `principal` into a ToolInvoker
of the unchanged shape, creates the PageContext over it, and awaits the handler. It holds no
per-Page state and does not serialize renders.

Who a render is for is the render's, not the Page's, which is why `render` takes the principal
and PageContext does not carry it. `docs/architecture/runtime.md` says why a principal is a
property of the invocation rather than of the window.

The window supplies its ToolRuntime as the invoker, so a Page reaches the Tools of the App
whose window it belongs to and no others. A Tool the App does not expose on the Web channel, or
whose roles the render's principal lacks, is refused at ToolRuntime like any other call.

## Relationship to Tools

Page-to-Tool relationships are many-to-many.

A Page may compose multiple Tools, and one Tool may be used by many Pages and by the Agent channel.

```text
          Tools
        /       \
     Pages      MCP
      |          |
    Human      Agent
```
