# ADR-007: The framework guarantees a Tool's output contract

Status: Accepted

## Context

The framework, not the app, publishes a Tool's output schema to channels, so the framework
owes the caller that the value it returns matches that schema.

Pydantic cannot be relied on to have already checked it. An existing model instance is
"assumed to be valid", `model_construct()` "does not do any validation, meaning it can
create models which are invalid", and assignment is unvalidated by default
([Pydantic - Models](https://pydantic.dev/docs/validation/latest/concepts/models/),
[Pydantic - Configuration](https://pydantic.dev/docs/validation/latest/api/pydantic/config/)).
Accepting a handler's instance as-is would therefore make output validation decorative.

## Decision

ToolRuntime validates every handler result against the declared output model rather than
trusting the instance the handler returned.

## Consequences

- the published schema and the returned value cannot diverge silently
- an app cannot bypass its own output contract, deliberately or by accident
- an output model must survive a dump and revalidation, and one that cannot fails
  deterministically
- one round trip is spent per invocation
