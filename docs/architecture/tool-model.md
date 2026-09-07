# Tool Model

## Definition

A Tool is the canonical public backend operation of an App.

A Tool represents a meaningful application or business operation that an external actor can intentionally invoke. Actors may include humans through Pages, agents through MCP, and future channels such as REST, CLI, automations, or webhooks.

A Tool is not an MCP construct.

## Examples

Good Tool names:

- `get_customer`
- `create_customer`
- `assign_owner`
- `request_discount`
- `close_opportunity`

Avoid infrastructure-shaped Tools unless the app domain genuinely requires them:

- `update_database_row`
- `set_field`
- `execute_sql`
- `call_external_api`

Internal helper functions, policies, services, and repositories are not required to be Tools.

## Core objects

The initial model should distinguish:

```text
ToolDefinition + ToolHandler -> Tool
```

Suggested responsibilities:

### ToolDefinition

- name
- description
- input model
- output model

Future metadata may include:

- query / command kind
- side-effect marker
- idempotency
- permissions
- exposure policy
- risk classification

Do not add these before a milestone requires them.

### ToolHandler

An async-first callable implementing the Tool operation.

Conceptual contract:

```python
async def handler(ctx: ToolContext, payload: InputModel) -> OutputModel:
    ...
```

Handler parameters are positional-only in the `ToolHandler` Protocol, so an app author may name them freely.

### ToolRegistry

Maps a Tool name to the Tool bound under it. Storage only; it implements no invocation
semantics, and resolution is consumed by ToolRuntime.

Registering a name twice replaces the earlier registration.

### ToolRuntime

The canonical invocation path for every channel. Constructed from an app id and a
ToolRegistry.

Minimal responsibilities:

1. resolve Tool
2. validate raw input
3. create/pass ToolContext
4. invoke handler
5. validate output
6. normalize framework errors

Business logic does not belong in ToolRuntime.

`ToolRuntime.invoke(name, raw_input)` returns the validated output model instance. Serialization belongs to channel adapters.

Framework errors are `ToolNotFoundError`, `ToolInputValidationError` and `ToolOutputValidationError`. Exceptions raised by a handler propagate unchanged.

A handler result is revalidated through the output model, so an output model must round-trip through `model_dump(by_alias=True)` back into `model_validate`. See `docs/decisions/ADR-007-framework-guarantees-tool-output.md`.

## Tool granularity

Prefer application/use-case semantics over generic record mutation.

A useful heuristic: a good Tool should usually satisfy the following.

1. A human can describe it as one meaningful application action.
2. An agent can infer when to use it from its name and contract.
3. Inputs and outputs use domain language.
4. It does not combine many independent workflows into one opaque operation.
5. It is natural for a Page to invoke directly.

## Query and command

A future version may classify Tools as:

- Query: reads state
- Command: changes state

This classification is useful for permissions, confirmations, audit, caching, and UI behavior, but is not required in the first Tool milestone.

## Channel neutrality

Tool behavior must not branch on channel-specific business rules.

Avoid patterns such as:

```python
if ctx.channel == "mcp":
    # business behavior A
else:
    # business behavior B
```

Channel metadata may later be used for audit, telemetry, or policy evaluation, but the domain behavior of a Tool remains channel-neutral.
