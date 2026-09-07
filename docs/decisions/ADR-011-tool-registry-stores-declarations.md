# ADR-011: The Tool registry stores declarations alongside bound callables

Status: Superseded by ADR-014

Supersedes: ADR-008

## Context

ADR-008's contravariance argument reaches the handler and no further, yet ToolRegistry stores
the bound callable alone and discards each declaration. Channel discovery enumerates what
Tools exist rather than resolving one, so it has nothing to enumerate.

A ToolDefinition holds no callable. Its fields are read positions only, so under inferred
variance a frozen declaration is covariant in both parameters
([PEP 695](https://peps.python.org/pep-0695/)) and a concrete declaration is assignable to
`ToolDefinition[BaseModel, BaseModel]`.

## Decision

ADR-008's binding is kept, and its reach is corrected. Registration also stores the
ToolDefinition in that erased form, and `ToolRegistry.definitions()` enumerates the stored
declarations in registration order.

## Consequences

- channel adapters project declarations for discovery without receiving them through a second
  path beside the registry
- neither Any nor cast is required, because the contravariance argument applies to the handler
  and not to the declaration
- registering a name twice replaces both the bound callable and the declaration
- ToolRegistry remains storage only and implements no invocation semantics
