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

Avoid infrastructure-shaped Tools unless the app's domain genuinely requires them:

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

It also answers with its own JSON Schemas, so every surface that publishes them publishes the
same ones: `input_schema()` is the input model's validation schema, because an argument mapping
is validated against it, and `output_schema()` is the output model's serialization schema,
because a channel sends `model_dump(by_alias=True, mode="json")`. A computed member or a
serialization alias therefore appears in the output schema and in the payload, and in neither
the input schema nor the arguments a caller may send. Two surfaces publish these — the Agent
channel's projection and a package's self-description — and the rule lives here rather than at
each of them, so one cannot describe a model the other does not. See
`docs/decisions/ADR-007-framework-guarantees-tool-output.md`.

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
async def handler(ctx: ToolContext[Deps], payload: InputModel) -> OutputModel:
    ...
```

`Deps` is the app's own type for its application-scoped resource, reached as
`ctx.dependencies`. See
`docs/decisions/ADR-013-dependencies-reach-handlers-through-tool-context.md`.

Handler parameters are positional-only in the `ToolHandler` Protocol, so a app author may name them freely.

### Tool

A ToolDefinition paired with the handler that implements it, bound at construction into
one uniform callable. The class is generic only in the dependency type; its `__init__` is
generic in the declared models, so `Tool(definition=..., handler=...)` reads as a
declaration and an AppDefinition can hold a sequence of Tools. A Tool does not expose its
handler.

### ToolRegistry

Maps a Tool name to the Tool registered under it. Storage only; it implements no
invocation semantics.

One dictionary suffices, and resolution is all a channel asks of it: a channel enumerates what
an App declares from the declaration, so a registry answers a name and nothing else. See
`docs/decisions/ADR-027-a-channel-enumerates-declarations-from-the-declaration.md`.

Registering a name twice replaces the earlier Tool, declaration included. A declaration carrying
one name twice never reaches the registry: the window refuses it where it builds one, because
enumeration and resolution no longer read the same object.

A name's *format* is not validated anywhere. `ToolDefinition.name` is a `str`, and the projection
a channel publishes carries it through unchanged. This is a decision rather than a gap: any
grammar a name must satisfy belongs to the protocol a channel speaks, and a framework that
enforced one channel's grammar in the core model would be implementing that channel's rule on its
behalf. What the framework guarantees about a name is uniqueness within one App.

### ToolRuntime

The canonical invocation path for every channel. Constructed from a app id, a ToolRegistry
and the application-scoped resource the channel's window acquired.

`ToolRuntime.invoke(name, raw_input)` is the whole of it:

1. resolve the Tool by name, through ToolRegistry
2. create the ToolContext, carrying the invocation id and the application-scoped resource
3. await the Tool

Steps that need the declared models belong to the Tool, not to the runtime: input
validation, the handler call and output validation happen together inside the closure a
Tool builds over its handler.

Business logic does not belong in ToolRuntime.

`invoke` returns the validated output model instance. Serialization belongs to channel adapters.

Framework errors are `ToolNotFoundError`, raised by the registry when no Tool answers to the
name, and `ToolInputValidationError` and `ToolOutputValidationError`, raised by the Tool.
Nothing translates them: they reach the caller as raised, as does an exception from a
handler. A channel adapter decides what its protocol does with them, and
`docs/architecture/errors.md` carries their codes.

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

Avoid patterns such as:

```python
if ctx.channel == "mcp":
    # business behavior A
else:
    # business behavior B
```

Channel metadata may later be used for audit, telemetry, or policy evaluation, but the domain behavior of a Tool remains channel-neutral.
