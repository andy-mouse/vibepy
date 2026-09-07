# ADR-011: The Tool registry stores declarations alongside bound callables

Status: Superseded by ADR-014

Supersedes: ADR-008

## Context

ADR-008's contravariance argument reaches the handler and no further, but the registry stores
the bound callable alone. Channel discovery enumerates what Tools exist rather than looking
one up, so it has nothing to enumerate.

A `ToolDefinition` holds no callable. Its fields are read positions only, so under inferred
variance a frozen declaration is covariant in both parameters
([PEP 695](https://peps.python.org/pep-0695/)) and a concrete one is assignable to
`ToolDefinition[BaseModel, BaseModel]`.

## Decision

ADR-008's binding is kept and its reach is corrected: registration also stores the
declaration, and the registry enumerates the stored declarations in registration order.

## Consequences

- channel adapters project declarations for discovery without a second path beside the
  registry
- neither `Any` nor `cast` is required, because the contravariance argument applies to the
  handler and not to the declaration
- registering a name twice replaces both the callable and the declaration
- the registry remains storage only
