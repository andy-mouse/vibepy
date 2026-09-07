# M1 - Tool Core

## Scope

Implement the six core Tool abstractions named in `docs/roadmap.md`: `ToolDefinition`,
`Tool`, `ToolHandler`, `ToolContext`, `ToolRegistry`, `ToolRuntime`.

No class beyond those six is introduced. Registration binds each typed Tool into a closure
of one uniform callable type, named by a type alias, per
`docs/decisions/ADR-008-tools-are-bound-at-registration.md`. The `ToolInvoker` name and its
position in front of `ToolRuntime` stay reserved for M2.

Acceptance: raw input -> validation -> async handler -> validated output, with
deterministic unknown/input/output errors.

## Invocation flow

`ToolRuntime` is the only execution path. One invocation performs exactly these steps.

```text
channel (MCP / Web Page)
   |  invoke("create_todo", {"title": "buy milk"})
   v
ToolRuntime
   1. resolve the name in ToolRegistry     -> ToolNotFoundError
   2. create ToolContext(app_id, invocation_id)
   3. validate raw input into the input model -> ToolInputValidationError
   4. await handler(ctx, input)             -> domain exceptions propagate unchanged
   5. validate the result into the output model -> ToolOutputValidationError
   6. return the validated output model instance
```

## Components

### ToolDefinition

Static declaration only, generic in its input and output models.

- `name: str`
- `description: str`
- `input_model: type[InputT]`
- `output_model: type[OutputT]`

Both models are required. `InputT` and `OutputT` are bound to `pydantic.BaseModel`.
No name format policy, no query/command kind, no exposure or permission metadata.

### ToolHandler

An async `Protocol`, generic in input and output.

```python
async def __call__(self, ctx: ToolContext, input: InputT) -> OutputT: ...
```

### Tool

A `ToolDefinition` paired with a `ToolHandler` over the same models. Immutable.
`Tool` carries no invocation behaviour; validation belongs to `ToolRuntime`.

### ToolContext

Invocation-scoped and immutable.

- `app_id: str`
- `invocation_id: str`

`invocation_id` is unique per invocation. It has no consumer inside M1; it exists so that
observability and audit (M15) have a correlation key, and so that "each invocation receives
an independent ToolContext" is observable in tests. `AppRuntime` does not exist yet, so
`ToolRuntime` is constructed with an `app_id` and creates every `ToolContext` itself.
Channels never construct a `ToolContext`.

### Binding

`ToolRuntime` owns the invocation steps, which `docs/architecture/tool-model.md` lists as
its minimal responsibilities. The binding function therefore lives with `ToolRuntime`:

```python
type BoundTool = Callable[[ToolContext, Mapping[str, object]], Awaitable[BaseModel]]

def bind[InputT: BaseModel, OutputT: BaseModel](tool: Tool[InputT, OutputT]) -> BoundTool
```

`bind` closes over the typed Tool and returns a plain callable from raw input to a
validated output model. Input validation, the handler call and output validation happen
inside that closure. Why a closure rather than a wrapper class, and why validation cannot
be split from the handler call:
`docs/decisions/ADR-008-tools-are-bound-at-registration.md`.

Why the handler result is revalidated rather than accepted as-is, and what that requires of
an app's output models: `docs/decisions/ADR-007-framework-guarantees-tool-output.md`.

`BoundTool` and `bind` are framework-internal. They are not re-exported from `vibepy`.

### ToolRegistry

Maps a name to a `BoundTool`. Storage only; it does not implement invocation semantics.

- `register(tool)` accepts a `Tool` over any input/output models and binds it.
- Registering a name twice replaces the earlier binding. Declaration consistency is M16's
  scope in `docs/roadmap.md`, and M1 does not build ahead of it.
- Resolution is consumed by `ToolRuntime` only.

Binding is what lets heterogeneous Tools share one map, and it happens where the model
types are still concrete, so neither `Any` nor `cast` appears anywhere in the framework.

`registry.py` imports `bind` and `BoundTool` from `runtime.py`. `runtime.py` imports
`ToolRegistry` under `typing.TYPE_CHECKING` with a quoted annotation, so no import executes
in both directions at runtime.

### ToolRuntime

The sole public invocation entry point. It resolves the name, creates the `ToolContext`,
and calls the `BoundTool`. No business logic, no global lock, no serialization of
concurrent invocations.

- Constructed from an `app_id` and a `ToolRegistry`.
- `invoke(name, raw_input)` returns the validated output model instance.

Serialization to dictionaries or JSON belongs to channel adapters, not to `ToolRuntime`.

## Errors

`VibepyError` is the single base class. Exception types are the contract; message strings
are not.

- `ToolNotFoundError` - the name is not registered
- `ToolInputValidationError` - raw input does not satisfy the input model
- `ToolOutputValidationError` - the handler result does not satisfy the output model

Each carries a `tool_name` attribute, which is what the Python tutorial describes as an
exception's usual purpose - attributes that let a handler extract information about the
error ([Errors and Exceptions](https://docs.python.org/3/tutorial/errors.html)). Names
follow [PEP 8](https://peps.python.org/pep-0008/): CapWords with an `Error` suffix.

Exceptions raised by a handler propagate unchanged. `ToolRuntime` does not wrap them.
Normalizing domain exceptions at the channel boundary is M7's decision, and wrapping them
now would pre-empt it.

## Module layout

```text
src/vibepy/
  errors.py
  tool/
    model.py     ToolDefinition, ToolHandler, Tool, ToolContext
    registry.py  ToolRegistry
    runtime.py   BoundTool, bind, ToolRuntime
```

`bind` sits in `runtime.py` because `docs/architecture/tool-model.md` assigns input
validation, the handler call and output validation to `ToolRuntime`. A separate binding
module and a private function inside `registry.py` are both implementable, and both put
those steps somewhere that document does not.

A package rather than a single module, because two repository invariants are import
boundaries - MCP types must not reach the core Tool model, NiceGUI types must not reach the
core Page model. A package makes those boundaries checkable. The layout also mirrors
`docs/architecture/`, which is already split by concept.

The public API is re-exported from `vibepy`. `tests/test_package.py` asserts
`vibepy.__all__ == []` today and is updated accordingly.

## Verification

Todo (`create_todo`, `list_todos`, `complete_todo`) is used as a test fixture only. No
sample app under `src/`: `AppDefinition` and `Page` do not exist yet, and building half of
one would be rewritten in M2, M4 and M5A.

Tests verify public contracts:

- a raw dictionary round-trips through a Tool into a validated output model
- an unregistered name raises `ToolNotFoundError`
- malformed raw input raises `ToolInputValidationError`
- a handler returning a value that violates its output model raises `ToolOutputValidationError`
- a domain exception raised by a handler reaches the caller unchanged
- the handler receives a `ToolContext` carrying the runtime's `app_id`
- two invocations receive different `invocation_id` values

Done when `make lint typecheck test` passes.

## Out of scope

Query/command classification, side-effect and idempotency metadata, permissions, exposure
policy, MCP schema generation, Tool name format policy, duplicate declaration diagnostics,
domain exception normalization, timeouts, cancellation, middleware, `AppRuntime` and
app-scoped dependencies.
