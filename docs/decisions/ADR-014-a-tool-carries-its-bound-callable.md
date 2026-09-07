# ADR-014: A Tool carries its own bound callable

Status: Accepted

Supersedes: ADR-011

## Context

ADR-008 established that a typed Tool is bound into one uniform callable at registration,
because the Python typing specification treats a type parameter in a callable parameter
position as contravariant and offers no way to recover the parameters of differently
parameterized generics from a collection
([Typing spec - Generics](https://typing.python.org/en/latest/spec/generics.html)).
ADR-011 kept that decision and corrected its reach: the registry also stores each
`ToolDefinition`, in a second dictionary beside the bound callables.

`AppDefinition` must hold a sequence of Tools, and that sequence needs one element type.
`Tool[DepsT, InputT, OutputT]` cannot supply one. `InputT` appears covariantly in the
declaration and contravariantly in the handler, so the class is invariant in it and no
concrete Tool is assignable to a common `Tool[DepsT, BaseModel, BaseModel]`. This is
ADR-008's problem in a new position, and the registry is not where it can be solved:
`docs/architecture/app-model.md` assigns `ToolRegistry` to AppRuntime, so a definition
cannot hold one.

## Decision

Binding moves from `ToolRegistry.register` into `Tool` itself.

```python
class Tool[DepsT]:
    def __init__[InputT: BaseModel, OutputT: BaseModel](
        self,
        *,
        definition: ToolDefinition[InputT, OutputT],
        handler: ToolHandler[DepsT, InputT, OutputT],
    ) -> None: ...
```

The class is generic only in `DepsT`; `__init__` is generic in the declared models. A Tool
therefore has one static type per App and a sequence of them is expressible.

A generic `__init__` is chosen over a factory function beside a frozen dataclass. The
factory is more obvious to a reader but adds a second name for one concept, and the
generic `__init__` leaves every declaration site unchanged. It is
[PEP 695](https://peps.python.org/pep-0695/) syntax rather than metaprogramming.

`ToolRegistry` keeps one dictionary of Tools. `definitions()` enumerates
`tool.definition` in registration order, unchanged.

## Consequences

- `AppDefinition` holds `Sequence[Tool[DepsT]]`, a readable declaration rather than an
  assembly procedure
- the free function `bind` disappears; the erasure has exactly one cause and one place
- `Tool` moves from `tool/model.py` to `tool/runtime.py`, because it now carries invocation
  behaviour and `tool/model.py` declares that its types do not
- `Tool(definition=..., handler=...)` is unchanged at every call site
- a Tool no longer exposes its handler. Code that reached through a Tool to call a handler
  directly calls the function instead
- registering a name twice still replaces the earlier Tool, declaration included
