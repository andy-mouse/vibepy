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

Prefer a narrow interface such as:

```python
await ctx.tools.call("create_customer", input)
```

over exposing ToolRuntime internals directly.

## Core objects

The initial model may distinguish:

```text
PageDefinition + PageHandler -> Page
```

### PageDefinition

Minimal initial metadata:

- name
- route
- title

### PageHandler

Human interaction/render implementation.

### PageContext

Provides Page-scoped capabilities such as:

- ToolInvoker
- session state
- future principal/identity information

It should not expose unrestricted AppRuntime internals.

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
