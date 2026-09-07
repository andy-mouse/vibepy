# ADR-011: The Tool registry stores declarations alongside bound callables

Status: Superseded by ADR-014

Supersedes: ADR-008

## Context

ADR-008's contravariance argument reaches the handler alone, yet ToolRegistry discards each
declaration, leaving channel discovery nothing to enumerate. A ToolDefinition holds no
callable and is covariant in both parameters
([PEP 695](https://peps.python.org/pep-0695/)).

## Decision

Registration also stores the ToolDefinition, and ToolRegistry enumerates the stored
declarations in registration order.

## Consequences

- channel adapters reach declarations through the registry rather than a second path
- neither Any nor cast is required
- registering a name twice replaces both the callable and the declaration
- ToolRegistry remains storage only
