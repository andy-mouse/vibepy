# ADR-008: Tools are bound into uniform callables at registration

Status: Superseded by ADR-011

## Context

ToolRegistry addresses Tools by name, so every stored value must share one static type,
while each handler has its own input type.

The Python typing specification makes generic types invariant by default, treats a type
parameter in a callable parameter position as contravariant, and provides no mechanism for
recovering the type parameters of differently parameterized generics from a collection
([Typing spec - Generics](https://typing.python.org/en/latest/spec/generics.html)). A
common supertype such as `Tool[BaseModel, BaseModel]` would mean a Tool accepting any
model, which a concrete handler does not.

Recovering the type inside a wrapper class method is not available either: pyright's strict
mode reports a statically always-true `isinstance` and an unnecessary `cast` as errors
([Pyright - Configuration](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)).

## Decision

Registration binds each typed Tool into a closure with one uniform callable type, produced
by a generic function that lives with ToolRuntime.

Input validation, the handler call and output validation happen inside that closure,
because input validation is what establishes that a raw mapping has the handler's input
type.

## Consequences

- neither `Any` nor `cast` appears in the framework
- ToolRegistry stores callables, not typed Tools, and implements no invocation semantics
- cross-cutting concerns added later still attach at ToolRuntime, where the invocation
  steps live
