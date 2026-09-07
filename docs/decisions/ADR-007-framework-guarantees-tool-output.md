# ADR-007: The framework guarantees a Tool's output contract

Status: Proposed

## Context

A Tool declares an output model. From M3 the Agent channel publishes a schema derived from
that model, so the value a channel receives must match what was published.

Pydantic treats an existing model instance as already valid:

- `revalidate_instances` defaults to `'never'`, and instances "are assumed to be valid"
  ([Pydantic - Models](https://pydantic.dev/docs/validation/latest/concepts/models/),
  [Pydantic - Configuration](https://pydantic.dev/docs/validation/latest/api/pydantic/config/))
- `model_construct()` "does not do any validation, meaning it can create models which are
  invalid" ([Pydantic - Models](https://pydantic.dev/docs/validation/latest/concepts/models/))
- `validate_assignment` defaults to `False`, so changing a field after construction is not
  validated ([Pydantic - Configuration](https://pydantic.dev/docs/validation/latest/api/pydantic/config/))

A handler can therefore return an instance that never passed validation, and accepting it
as-is would make output validation decorative.

## Decision

ToolRuntime validates every handler result against the declared output model instead of
trusting the returned instance.

The guarantee belongs to the framework because the framework, not the app, publishes the
schema to channels.

## Consequences

- the published schema and the returned value cannot diverge silently
- an output model must round-trip through `model_dump(by_alias=True)` into
  `model_validate`; a model whose aliases or computed fields break that round trip fails
  deterministically with `ToolOutputValidationError`
- one dump/validate round trip is spent per invocation
- an app cannot use `model_construct` to bypass its own output contract
