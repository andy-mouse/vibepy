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

A Page invokes a Tool by name and never sees ToolRuntime:

```python
await ctx.tools.call("create_customer", raw_input)
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

`name` is the identifier the framework addresses a Page by, and it is stable across a
route change. `route` and `title` are consumed by the Web channel adapter, so their format
is validated where routes are registered, not in the core Page model.

### PageHandler

Human interaction/render implementation.

Conceptual contract:

```python
async def handler(ctx: PageContext) -> None:
    ...
```

The parameter is positional-only in the `PageHandler` Protocol, so an app author may name
it freely.

A handler returns nothing. A Page builds its interface by side effect, as a NiceGUI page
builder does, and a render result would be a value no channel reads. Returning a Web
response instead is a Web channel concern and belongs to the NiceGUI adapter.

### Page

A PageDefinition paired with the handler that implements it.

Page is not generic. A PageHandler declares no input or output model, so every Page already
shares one static type and needs no binding step before storage. ADR-008 applies to Tools
only.

### ToolInvoker

The narrow interface a Page invokes Tools through.

```python
def call(name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]: ...
```

The signature is `ToolRuntime.invoke`'s, so validation stays wholly inside ToolRuntime and
no second validation path exists. ToolInvoker is a Protocol: the core Page model depends on
the shape of Tool invocation, not on the Tool runtime.

Tool errors are not translated. `ToolNotFoundError`, `ToolInputValidationError` and
`ToolOutputValidationError` reach the caller of the Page unchanged, as does an exception
raised by a PageHandler.

### PageContext

Provides Page-scoped capabilities such as:

- ToolInvoker
- session state
- future principal/identity information

Of these, a PageContext currently carries only its ToolInvoker. Session state is owned by
the Web channel, which is where a session exists.

It should not expose unrestricted AppRuntime internals.

PageRuntime creates a PageContext. A Page never constructs one, and neither does a channel.

### PageRegistry

Maps a Page name to the Page registered under it. Storage only; it implements no invocation
semantics, and resolution is consumed by PageRuntime.

Registering a name twice replaces the earlier registration.

The registry also enumerates its declarations, because a Web channel adapter projects every
PageDefinition into a route. Route uniqueness is therefore validated where routes are
registered.

Resolving a name that was never registered raises `PageNotFoundError`.

### PageRuntime

Constructed from a PageRegistry and a ToolRuntime.

`PageRuntime.render(name)` resolves the Page, creates its PageContext with a ToolInvoker
backed by that ToolRuntime, and awaits the handler. It holds no per-Page state and does not
serialize renders.

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
