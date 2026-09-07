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

`AppDefinition` is static and declarative. It should eventually contain:

- stable app id
- display name
- version
- Tool declarations
- Page declarations
- optional config model
- optional lifecycle hooks
- metadata

It should not contain live connections, request state, UI sessions, or running adapters.

## AppRuntime

`AppRuntime` is the executable instance of an AppDefinition.

It owns application-scoped runtime state such as:

- ToolRegistry
- ToolRuntime
- application-scoped dependencies
- typed configuration
- lifecycle state
- active channel adapters

Web and MCP adapters for one running app must receive the same AppRuntime instance.

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

Owned by ToolContext:

- invocation id
- principal / actor when introduced
- tracing metadata
- deadline / cancellation metadata
- invocation-specific transaction context when introduced

## Invariants

- AppDefinition is static metadata and declarations.
- AppRuntime is executable state.
- ToolRuntime belongs to AppRuntime.
- AppRuntime is shared by the Web and Agent channels of the same app instance.
- Page/session state must not leak into application-scoped state.
- Tool handlers must not receive unrestricted access to AppRuntime internals.
