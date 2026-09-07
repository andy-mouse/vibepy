# ADR-008: Tools are bound into uniform callables at registration

Status: Superseded by ADR-011

## Context

ToolRegistry addresses Tools by name, so every value it stores must share one static type,
while each handler declares its own input type.

The typing rules offer no common supertype. Generics are invariant by default, a type
parameter in a callable parameter position is contravariant, and the parameters of
differently parameterized generics cannot be recovered from a collection
([Typing spec - Generics](https://typing.python.org/en/latest/spec/generics.html)). An erased
Tool would claim a Tool accepting any model, which no concrete handler is.

Recovering the type inside a wrapper is closed too, because pyright's strict mode rejects
both an always-true isinstance and an unnecessary cast.

## Decision

Registration binds each typed Tool into a closure with one uniform callable type.

Input validation, the handler call and output validation happen inside that closure, because
input validation is what establishes that a raw mapping has the handler's input type.

## Consequences

- neither Any nor cast appears in the framework
- ToolRegistry stores callables and implements no invocation semantics
- cross-cutting concerns added later still attach at ToolRuntime, where the invocation steps
  live
