# ADR-014: A Tool carries its own bound callable

Status: Accepted

Supersedes: ADR-011

## Context

An AppDefinition must hold a sequence of Tools, and a sequence needs one element type. A Tool
generic in its declared models supplies none: the input type appears covariantly in the
declaration and contravariantly in the handler, so the class is invariant in it and no
concrete Tool is assignable to a common one
([Typing spec - Generics](https://typing.python.org/en/latest/spec/generics.html)).

This is ADR-008's problem in a new position, and the registry is not where it can be solved,
because a registry belongs to the runtime and a declaration cannot hold one.

## Decision

Binding moves from the registry into the Tool itself. The class is generic only in the
dependency type while its constructor is generic in the declared models, so a Tool has one
static type per App and a sequence of them is expressible.

A generic constructor is chosen over a factory function beside a frozen dataclass. The factory
is more obvious to a reader but adds a second name for one concept, and it is standard syntax
rather than metaprogramming ([PEP 695](https://peps.python.org/pep-0695/)).

## Consequences

- an AppDefinition holds a readable declaration rather than an assembly procedure
- the free binding function disappears; the erasure has one cause and one place
- `Tool` moves out of the declarations module into the runtime one, because it carries
  invocation behaviour and the declarations module states that its types do not
- every declaration site is unchanged
- a Tool no longer exposes its handler, so code that reached through a Tool calls the
  function instead
