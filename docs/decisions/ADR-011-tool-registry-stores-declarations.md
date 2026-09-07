# ADR-011: The Tool registry stores declarations alongside bound callables

Status: Superseded by ADR-014

Supersedes: ADR-008

## Context

ADR-008 established that a typed Tool is bound into one uniform callable at registration,
because the Python typing specification treats a type parameter in a callable parameter
position as contravariant and offers no way to recover the parameters of differently
parameterized generics from a collection.

That argument reaches the handler and no further, but the registry stores the bound callable
alone and discards each `ToolDefinition`. Channel discovery enumerates what Tools exist
rather than looking one up, so it has nothing to enumerate.

A `ToolDefinition` holds no callable. Its fields are read positions only, so under
[PEP 695](https://peps.python.org/pep-0695/) inferred variance a frozen `ToolDefinition` is
covariant in both parameters, and a concrete declaration is assignable to
`ToolDefinition[BaseModel, BaseModel]`.

## Decision

ADR-008's decision is kept: registration binds each typed Tool into a closure with one
uniform callable type.

Its reach is corrected. Registration also stores the `ToolDefinition` as
`ToolDefinition[BaseModel, BaseModel]`, and `ToolRegistry.definitions()` enumerates the
stored declarations in registration order.

## Consequences

- channel adapters project declarations for discovery without receiving them through a
  second path alongside the registry
- neither `Any` nor `cast` is required: the contravariance argument applies to the handler,
  not to the declaration
- registering a name twice replaces both the bound callable and the declaration
- the registry remains storage only and implements no invocation semantics
