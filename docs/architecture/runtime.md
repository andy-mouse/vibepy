# Runtime Architecture

## ToolRuntime as the execution center

All channel invocation converges at ToolRuntime.

```text
Web / Page ----\
                -> ToolRuntime -> Tool -> Domain internals
MCP Adapter ---/
```

This central boundary is where generic framework behavior can be added consistently over time.

Potential future cross-cutting concerns include:

- authorization
- audit
- timeout
- tracing
- metrics
- transaction hooks
- rate limits

Do not add a generic middleware framework until a concrete need appears.

## ToolContext

ToolContext is invocation-scoped and deliberately narrower than AppRuntime.

It currently carries:

- app id
- invocation id
- `dependencies`: the application-scoped resource, typed by the app itself

`dependencies` is one value of the app's own type, not a mapping and not AppRuntime.

Future fields may include:

- principal
- actor
- channel metadata
- tenant
- locale
- permissions
- trace context

ToolRuntime creates a ToolContext for every invocation, with an invocation id unique to
that invocation. Channels never construct one.

Do not make ToolContext an untyped service-locator bag. See
`docs/decisions/ADR-013-dependencies-reach-handlers-through-tool-context.md`.

## Dependency ownership

Application-scoped dependencies belong to AppRuntime.

Examples:

- DB connection pool
- repository
- API client
- cache

Prefer typed dependency objects over generic dictionaries when practical.

AppRuntime creates the resource once from `AppDefinition.create_dependencies` and hands it
to ToolRuntime, which puts it into every ToolContext it creates. Two AppRuntimes built from
one AppDefinition each call the factory, so they are isolated by default.

## Concurrency

Tool handlers are async-first.

ToolRuntime permits concurrent invocations by default.

ToolRuntime must not serialize all calls with a global lock.

Domain consistency belongs to the app's service/repository/storage layer.

Each invocation receives an independent ToolContext while sharing application-scoped dependencies from AppRuntime.

## Dual-channel contract

The framework must maintain a constitutional integration test proving that Web-like and Agent-like calls share the same AppRuntime and state.

Example:

1. Agent-side invocation creates item A.
2. Web-side invocation creates item B.
3. Web-side read sees A and B.
4. Agent-side read sees A and B.

This test should remain throughout the project. Both channels are built from one
AppRuntime, so sharing is structural rather than arranged by the test.
