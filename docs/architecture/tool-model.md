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
- `read_only`: whether the operation is side-effect free, required and never defaulted
- `channels`: the channels the Tool is exposed through, both by default; non-empty, a declaration
  exposed through no channel is refused as it is constructed (`tool.channels_empty`)
- `required_roles`: the roles a caller must hold, empty meaning anyone

A ToolDefinition is a frozen dataclass, not a pydantic model: it holds types and callables and
stays inside one process. A shape that crosses a process boundary is one pydantic model owned by
`vibepy_core` — `ToolDescription` is the one a reader outside this process gets, and
`docs/architecture/packaging.md` owns it.

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

- idempotency
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

A Tool is bound once — both its attributes are `Final` — so it is contravariant in that
dependency type. An App may therefore include a Tool written against a wider one than its
own: a Tool that reads no dependencies at all, typed `ToolContext[object]`, or one typed
against a Protocol the App's dependency type satisfies. Such a Tool belongs in the App's
own `Sequence[Tool[Deps]]` unchanged, and receives the App's `ctx.dependencies`
(`docs/architecture/runtime.md`, ToolContext) like any other.

### ToolRegistry

Maps a Tool name to the Tool registered under it. Storage only; it implements no
invocation semantics.

One dictionary suffices, and resolution is all a channel asks of it: a channel enumerates what
an App declares from the declaration, so a registry answers a name and nothing else. See
`docs/decisions/ADR-027-a-channel-enumerates-declarations-from-the-declaration.md`.

Registering a name twice replaces the earlier Tool, declaration included. A declaration carrying
one name twice never reaches the registry: the `AppDefinition` refuses it as it is constructed,
because enumeration and resolution no longer read the same object.

A name's *format* is not validated anywhere. `ToolDefinition.name` is a `str`, and the projection
a channel publishes carries it through unchanged. This is a decision rather than a gap: any
grammar a name must satisfy belongs to the protocol a channel speaks, and a framework that
enforced one channel's grammar in the core model would be implementing that channel's rule on its
behalf. What the framework guarantees about a name is uniqueness within one App.

### ToolRuntime

The canonical invocation path for every channel. Constructed from a app id, a ToolRegistry,
the application-scoped resource the channel's window acquired, the channel that window
opened, and the App's own policy if it declares one.

`ToolRuntime.invoke(name, raw_input, *, principal)` is the whole of it:

1. create the invocation id and note the time, before anything can refuse
2. resolve the Tool by name, through ToolRegistry
3. the framework's default policy: the channel against `channels`, the principal's roles
   against `required_roles`
4. the App's policy, if it declared one
5. create the ToolContext, carrying that invocation id, the application-scoped resource, the
   principal and the channel
6. await the Tool
7. write the invocation record, whatever way steps 2–6 ended, and re-raise what they raised

`docs/architecture/runtime.md` owns the record.

Steps that need the declared models belong to the Tool, not to the runtime: input
validation, the handler call and output validation happen together inside the closure a
Tool builds over its handler.

Business logic does not belong in ToolRuntime.

`invoke` returns the validated output model instance. Serialization belongs to channel adapters.

Framework errors are `ToolNotFoundError`, raised by the registry when no Tool answers to the
name, `ToolForbiddenError`, raised by a policy, and `ToolInputValidationError` and
`ToolOutputValidationError`, raised by the Tool.
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

## Side-effect semantics

A Tool declares `read_only`: whether invoking it is free of side effects.

The vocabulary is HTTP's before it is MCP's. RFC 9110 calls a method *safe* when its semantics
are read-only, and *idempotent* when repeating it has the same effect as making it once
(<https://www.rfc-editor.org/rfc/rfc9110#section-9.2.1>,
<https://www.rfc-editor.org/rfc/rfc9110#section-9.2.2>). MCP carries the same two notions onto
Tools as `readOnlyHint` and `idempotentHint`, the second "meaningful only when `readOnlyHint ==
false`" (<https://modelcontextprotocol.io/specification/2025-06-18/server/tools>). One field
therefore crosses protocols without translation, and every channel reads the declaration rather
than a per-channel restatement of it.

`read_only` is required and has no default: a default would classify a Tool silently, and
whether an operation writes is the author's statement, not the framework's guess.

`destructive` and `idempotent` are not declared. They qualify a Tool that is not read-only,
which is the structure the specification gives them, and they join `read_only` when a milestone
needs them.

`read_only` refuses nothing. It is what a policy, an audit record and the Agent channel's
projection read; refusal is Authorization's, below.

## Authorization

Authorization has two levels. *Operation-level*: may this principal, on this channel, invoke
this kind of operation at all. *Record-level*: may this principal act on this particular
record. OWASP separates them the same way, and requires the check to be server-side and per
request, "for the specific object or functionality being accessed"
(<https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html>).

The framework owns the first level and decides it in ToolRuntime, before input is validated, so
a refused caller learns nothing of the input schema and no handler is reachable without the
decision. The second level is the handler's, reached through `ctx.principal`; its refusals are
the App's own expected failures and travel as data
(`docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md`). See
`docs/decisions/ADR-034-authorization-is-operation-level-in-toolruntime.md`.

A `Principal` is an `id` and the roles its host asserts for it. The framework compares roles and
interprets neither; it names no role of its own, and the host that opens a window decides who
the principal is. `docs/architecture/runtime.md` owns how a principal and a channel reach an
invocation.

The framework's default policy is the declaration read back:

- the invoking channel is not in `channels` — refused, reason `not_exposed`
- `required_roles` is non-empty and disjoint from the principal's roles — refused, reason
  `role_required`

An App may declare a `ToolPolicy` of its own on its AppDefinition. It runs after the default and
may only refuse further: an App narrows and never widens, so a defect in an App's policy cannot
open a Tool the declaration closed. One policy and not a chain —
`docs/architecture/runtime.md` forbids a middleware framework before a concrete need.

A refusal is `ToolForbiddenError`, whose `details` name the Tool, the principal, the channel and
the reason. `docs/architecture/errors.md` carries its code.

## Channel neutrality

Avoid patterns such as:

```python
if ctx.channel == "mcp":
    # business behavior A
else:
    # business behavior B
```

Channel metadata may later be used for audit, telemetry, or policy evaluation, but the domain behavior of a Tool remains channel-neutral.
