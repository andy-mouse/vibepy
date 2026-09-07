# ADR-007: The framework guarantees a Tool's output contract

Status: Accepted

## Context

The framework publishes a Tool's output schema to channels, and Pydantic assumes an existing
model instance is valid, so a handler can return a value that never passed validation
([Pydantic - Models](https://pydantic.dev/docs/validation/latest/concepts/models/)).

## Decision

ToolRuntime revalidates every handler result against the declared output model.

## Consequences

- the published schema and the returned value cannot diverge
- an app cannot bypass its own output contract
- an output model that cannot survive revalidation raises ToolOutputValidationError
- one dump and validate round trip is spent per invocation
