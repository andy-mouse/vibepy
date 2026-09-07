# ADR-014: A Tool carries its own bound callable

Status: Accepted

Supersedes: ADR-011

## Context

An AppDefinition holds a sequence of Tools, which needs one element type, and a Tool generic
in its declared models is invariant in them. ToolRegistry cannot supply the type, because a
registry belongs to AppRuntime and a declaration cannot hold one.

## Decision

Binding moves from ToolRegistry.register into Tool. Tool is generic only in the dependency
type while its constructor is generic in the declared models, so a Tool has one static type
per App.

A generic constructor is chosen over a factory beside a frozen dataclass, which would add a
second name for one concept.

## Consequences

- an AppDefinition holds a sequence of Tools rather than an assembly procedure
- the free bind function disappears; the erasure has one cause and one place
- Tool belongs to the runtime rather than to the declarations, because it carries behaviour
- every declaration site is unchanged
- a Tool no longer exposes its handler
