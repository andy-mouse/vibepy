# M1 - Tool Core

## Scope

Implement the six core Tool abstractions named in `docs/roadmap.md`: `ToolDefinition`,
`Tool`, `ToolHandler`, `ToolContext`, `ToolRegistry`, `ToolRuntime`.

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

### ToolRegistry

Maps a name to a registered Tool.

- `register(tool)` accepts a `Tool` over any input/output models.
- Registering a name twice raises `ToolAlreadyRegisteredError`. Silent replacement is not
  offered; a duplicate name is a composition error, not a runtime condition.
- Resolution for invocation is consumed by `ToolRuntime` only.

Registration erases the generic parameters so that heterogeneous Tools can share one map.
Erasure happens inside a generic helper where the model types are still concrete, so
neither `Any` nor `cast` appears anywhere in the framework.

### ToolRuntime

The sole public invocation entry point. It resolves the name, creates the `ToolContext`,
and runs the erased invocation. No business logic, no global lock, no serialization of
concurrent invocations.

- Constructed from an `app_id` and a `ToolRegistry`.
- `invoke(name, raw_input)` returns the validated output model instance.

Input validation, handler call and output validation are performed together inside the
erased invocation created at registration. They are inseparable at that boundary: input
validation is precisely what proves the value has the handler's input type, so splitting
them would require a `cast` or an unreachable type guard. `ToolRuntime` remains the only
caller of that invocation.

Output validation revalidates the handler result through the output model rather than
accepting the instance as-is. Pydantic does not revalidate an instance of the same model,
so accepting it would make output validation unobservable and the acceptance criterion
untestable. The cost is one dump/validate round trip per invocation, and alias and
computed-field behaviour is out of scope for M1.

Serialization to dictionaries or JSON belongs to channel adapters, not to `ToolRuntime`.

## Errors

`VibepyError` is the single base class. Exception types are the contract; message strings
are not.

- `ToolNotFoundError` - the name is not registered
- `ToolInputValidationError` - raw input does not satisfy the input model
- `ToolOutputValidationError` - the handler result does not satisfy the output model
- `ToolAlreadyRegisteredError` - a name is registered twice

Exceptions raised by a handler propagate unchanged. `ToolRuntime` does not wrap them.
Normalizing domain exceptions at the channel boundary is M7's decision, and wrapping them
now would pre-empt it.

## Module layout

```text
src/vibepy/
  errors.py
  tool/
    model.py      ToolDefinition, ToolHandler, Tool, ToolContext
    registry.py   ToolRegistry
    runtime.py    ToolRuntime
```

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
- registering the same name twice raises `ToolAlreadyRegisteredError`
- the handler receives a `ToolContext` carrying the runtime's `app_id`
- two invocations receive different `invocation_id` values

Done when `make lint typecheck test` passes.

## Out of scope

Query/command classification, side-effect and idempotency metadata, permissions, exposure
policy, MCP schema generation, Tool name format policy, domain exception normalization,
timeouts, cancellation, middleware, `AppRuntime` and app-scoped dependencies.
