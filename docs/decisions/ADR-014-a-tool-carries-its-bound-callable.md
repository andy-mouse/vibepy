# ADR-014: A Tool carries its own bound callable

Status: Accepted

Supersedes: ADR-011

## Context

An AppDefinition must hold a sequence of Tools, and that sequence needs one element type. A
Tool generic in its declared models cannot supply one: the input type appears covariantly in
the declaration and contravariantly in the handler, so the class is invariant in it and no
concrete Tool is assignable to a common erased form
([Typing spec - Generics](https://typing.python.org/en/latest/spec/generics.html)).

This is ADR-008's problem in a new position, and the registry is not where it can be solved.
A registry belongs to AppRuntime, so a declaration cannot hold one. ADR-011 also left the
registry holding each declaration in a second dictionary beside the bound callables.

## Decision

Binding moves from ToolRegistry.register into Tool itself. Tool is generic only in the
dependency type while its constructor is generic in the declared models, so a Tool has one
static type per App and a sequence of them is expressible.

A generic constructor is chosen over a factory function beside a frozen dataclass. The
factory is more obvious to a reader but adds a second name for one concept, and a generic
constructor leaves every declaration site unchanged. It is standard syntax rather than
metaprogramming ([PEP 695](https://peps.python.org/pep-0695/)), and the dependency type is
inferred from the handler alone.

ToolRegistry keeps one dictionary of Tools, and `definitions()` enumerates each Tool's
declaration in registration order, unchanged.

## Consequences

- an AppDefinition holds a sequence of Tools, a readable declaration rather than an assembly
  procedure
- the free bind function disappears; the erasure has exactly one cause and one place
- Tool belongs with the runtime rather than with the declarations, because it now carries
  invocation behaviour
- every declaration site is unchanged
- a Tool no longer exposes its handler, so code that reached through a Tool to call a handler
  calls the function instead
- registering a name twice still replaces the earlier Tool, declaration included
