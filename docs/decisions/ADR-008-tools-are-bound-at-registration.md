# ADR-008: Tools are bound into uniform callables at registration

Status: Superseded by ADR-011

## Context

A registry addressed by name needs one static type for every value it stores, while each
handler declares its own input type. The typing rules offer no common supertype: generics
are invariant by default and a type parameter in a callable parameter position is
contravariant, with no way to recover the parameters of differently parameterized generics
from a collection
([Typing spec - Generics](https://typing.python.org/en/latest/spec/generics.html)).
`Tool[BaseModel, BaseModel]` would claim a Tool that accepts any model, which no concrete
handler does.

Recovering the type inside the wrapper is not open either, because pyright's strict mode
rejects both an always-true `isinstance` and an unnecessary `cast`.

## Decision

Registration binds each typed Tool into a closure with one uniform callable type.

Input validation, the handler call and output validation happen inside that closure, because
input validation is what establishes that a raw mapping has the handler's input type.

## Consequences

- neither `Any` nor `cast` appears in the framework
- the registry stores callables and implements no invocation semantics
- cross-cutting concerns added later still attach at ToolRuntime, where the invocation steps
  live
