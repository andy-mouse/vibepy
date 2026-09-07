# ADR-008: Tools are bound into uniform callables at registration

Status: Superseded by ADR-011

## Context

ToolRegistry addresses Tools by name, so every value it stores must share one static type,
while each handler declares its own input type.

The typing rules offer no common supertype. Generics are invariant by default, a type
parameter in a callable parameter position is contravariant, and the parameters of
differently parameterized generics cannot be recovered from a collection
([Typing spec - Generics](https://typing.python.org/en/latest/spec/generics.html)). An erased
`Tool[BaseModel, BaseModel]` would claim a Tool accepting any model, which no concrete handler
is.

Recovering the type inside a wrapper is closed too, because pyright's strict mode reports
both a statically always-true isinstance and an unnecessary cast as errors
([Pyright - Configuration](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)).

## Decision

Registration binds each typed Tool into a closure with one uniform callable type, produced by
a generic function that lives with ToolRuntime.

Input validation, the handler call and output validation happen inside that closure, because
input validation is what establishes that a raw mapping has the handler's input type.

## Consequences

- neither Any nor cast appears in the framework
- ToolRegistry stores callables and implements no invocation semantics
- the registry imports the binding function from the runtime module, and the runtime module
  imports ToolRegistry under `typing.TYPE_CHECKING` with a quoted annotation, which
  [PEP 484](https://peps.python.org/pep-0484/) defines for exactly this case
- cross-cutting concerns added later still attach at ToolRuntime, where the invocation steps
  live
