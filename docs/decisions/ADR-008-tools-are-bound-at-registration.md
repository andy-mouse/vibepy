# ADR-008: Tools are bound into uniform callables at registration

Status: Superseded by ADR-011

## Context

ToolRegistry addresses Tools by name, so every stored value needs one static type, while each
handler declares its own input type. The typing rules offer no common supertype
([Typing spec - Generics](https://typing.python.org/en/latest/spec/generics.html)).

## Decision

Registration binds each typed Tool into a closure with one uniform callable type.

Input validation, the handler call and output validation happen inside that closure, because
input validation establishes that a raw mapping has the handler's input type.

## Consequences

- neither Any nor cast appears in the framework
- ToolRegistry stores callables and implements no invocation semantics
- cross-cutting concerns attach at ToolRuntime, where the invocation steps live
