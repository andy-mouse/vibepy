# ADR-007: The framework guarantees a Tool's output contract

Status: Accepted

## Context

A Tool declares an output model, and the Agent channel publishes a schema derived from that
model, so the value a channel receives must match what was published.

Pydantic treats an existing model instance as already valid. With `revalidate_instances`
defaulting to `'never'` instances "are assumed to be valid", `model_construct()` "does not do
any validation, meaning it can create models which are invalid", and `validate_assignment`
defaults to `False`, so a field changed after construction is not validated
([Pydantic - Models](https://pydantic.dev/docs/validation/latest/concepts/models/),
[Pydantic - Configuration](https://pydantic.dev/docs/validation/latest/api/pydantic/config/)).

A handler can therefore return an instance that never passed validation, and accepting it
as-is would make output validation decorative.

## Decision

ToolRuntime validates every handler result against the declared output model instead of
trusting the returned instance.

The guarantee belongs to the framework because the framework, not the app, publishes the
schema to channels.

## Consequences

- the published schema and the returned value cannot diverge silently
- an output model must round-trip through a dump and back into validation, and one whose
  aliases or computed fields break that round trip fails deterministically with
  ToolOutputValidationError
- one dump and validate round trip is spent per invocation
- an app cannot use model_construct to bypass its own output contract
