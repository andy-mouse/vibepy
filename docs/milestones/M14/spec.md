# M14 - Permissions and security

Date: 2026-09-12

## Acceptance criteria

From `docs/roadmap.md`, verbatim:

- unauthorized Tool calls are rejected before handler execution
- actor/principal and policy checks are enforced through the canonical ToolRuntime path
- Tool behavior remains channel-neutral while exposure and permission may vary by channel

## Sources

| Contract | Source |
| --- | --- |
| ToolRuntime is the canonical invocation path; "authorization" is named as a future cross-cutting concern that belongs there, and no middleware framework is built before a concrete need | `docs/architecture/runtime.md` |
| ToolContext may later carry principal, actor, channel metadata and permissions; it is not a service-locator bag | `docs/architecture/runtime.md`, `docs/decisions/ADR-013-dependencies-reach-handlers-through-tool-context.md` |
| ToolDefinition's future metadata names query/command kind, permissions and exposure policy, "not before a milestone requires them"; Tool behaviour never branches on channel, channel metadata may serve policy | `docs/architecture/tool-model.md` |
| Pages never bypass Tools; PageContext may later carry principal/identity; the Page package imports nothing from the Tool package | `docs/architecture/page-model.md`, `docs/decisions/ADR-002-pages-consume-tools.md` |
| A channel enumerates what an App declares from the declaration | `docs/decisions/ADR-027-a-channel-enumerates-declarations-from-the-declaration.md` |
| The host owns the window; adapters build and run nothing; each channel runs in its own process | `docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md`, `docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md` |
| Until per-channel exposure exists, every Studio Tool appears on both channels; "M14 decides exposure with the authoring loop of M18 as its measure" | `docs/decisions/ADR-032-authoring-is-studios-agent-channel.md` |
| The framework implements channel neutrality and delegates the rest | `docs/decisions/ADR-025-the-framework-implements-channel-neutrality-and-delegates-the-rest.md` |
| A framework error is a type with a stable code and a closed category; the Agent channel reports one as an `isError` text block, the Web channel translates nothing | `docs/architecture/errors.md`, `docs/decisions/ADR-019-framework-errors-carry-stable-codes.md` |
| An App's expected failures travel as data inside its output model | `docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md` |
| `vibepy_core.invoke` is how a host that must not import an App verifies a Tool; it runs the same path both channels run | `docs/architecture/packaging.md`, Invoking one Tool |
| The Apps this repository carries, and Expense as the App for actor/role | `docs/roadmap.md`, Apps |
| Authorization is defined for HTTP transports; a stdio implementation "SHOULD NOT follow this specification, and instead retrieve credentials from the environment" | MCP specification 2025-06-18, Authorization, Protocol Requirements |
| Servers "MUST implement proper access controls" | MCP specification 2025-06-18, Tools, Security Considerations |
| Access control is checked server-side, on every request, "for the specific object or functionality being accessed"; access to a type of object is not access to every object of that type | OWASP Authorization Cheat Sheet |
| `ToolAnnotations`: `readOnlyHint` (default false, "does not modify its environment"), `destructiveHint` (default true) and `idempotentHint` (default false) "meaningful only when `readOnlyHint == false`", `openWorldHint` (default true); all are hints, and "clients should never make tool use decisions based on ToolAnnotations received from untrusted servers" | MCP specification 2025-06-18, `schema.ts`, `ToolAnnotations` |
| A *safe* method is one whose semantics are read-only; an *idempotent* method may be repeated with the same effect | RFC 9110, §9.2.1 and §9.2.2 |
| Codex asks before an MCP tool call unless `readOnlyHint` is true: a tool without annotations is treated as destructive (`destructive_hint.unwrap_or(true)`); `writes` mode "prompts for tools that aren't marked read-only" | `openai/codex`, `codex-rs/core/src/mcp_tool_call.rs`, `requires_mcp_tool_approval`; Codex config reference, `mcp_servers.<id>.default_tools_approval_mode` |
| Claude Code reads no standard annotation for permissions; it reads `_meta["anthropic/requiresUserInteraction"]` | <https://code.claude.com/docs/en/mcp> |

## Problem

Every Tool call runs. ToolRuntime resolves a name, validates input and awaits the handler; nothing
asks who is calling or from where, and nothing in a declaration says which channel a Tool is meant
for. The cost is visible in Studio: `install_app`, `remove_app`, `start_app` and `stop_app` are
projected onto MCP beside the authoring Tools, so a coding agent connected to Studio can uninstall
an App. ADR-032 names this as the debt M14 pays.

Neither channel authenticates. The Web channel has no login; the Agent channel is stdio, whose
specification defines no authorization and makes the launcher the trusted party. This milestone
therefore does not decide *how a caller is authenticated*. It decides *what a caller is once
known*, how that reaches every Tool through the one path both channels share, and what a Tool
declares so the framework can refuse before a handler runs.

## Decisions

### Principal propagation, not authentication

The framework defines a `Principal` and threads it. A host — the process that opens a window —
decides who the principal is and hands it in; the framework never derives one. This is ADR-025
applied: authentication is a solved problem owned by channel technologies (NiceGUI's session
storage and auth middleware, MCP's OAuth on HTTP transports), and adopting either is a later
decision that plugs into the same seam. In M14 each host knows one caller, the party that
launched the process, and says so with a constant.

### Principal is `id` plus `roles`

```python
@dataclass(frozen=True)
class Principal:
    id: str
    roles: frozenset[str] = frozenset()
```

Role-based access control is the standard split: the host asserts identity, the App declares what
roles an operation requires, and the framework compares the two without interpreting either. The
framework never names a role. `id` is what a handler uses for record-level decisions ("mine").

### Exposure, side-effect semantics and required roles are declared on the Tool

```python
class Channel(StrEnum):
    WEB = "web"
    AGENT = "agent"

@dataclass(frozen=True)
class ToolDefinition[InputT, OutputT]:
    name: str
    description: str
    input_model: type[InputT]
    output_model: type[OutputT]
    read_only: bool                                      # required, no default
    channels: frozenset[Channel] = frozenset(Channel)    # both
    required_roles: frozenset[str] = frozenset()         # anyone
```

The facts about a Tool sit on the Tool. A channel enumerates from the declaration (ADR-027), so
filtering by `channels` at the adapter is one more read of the same object, and the list an agent
sees and the map a call resolves in cannot disagree.

`read_only` is the framework's side-effect vocabulary, and it is HTTP's before it is MCP's: RFC
9110 classifies methods as *safe* and *idempotent*, and MCP's `readOnlyHint`/`idempotentHint` carry
the same two notions onto Tools, "meaningful only when `readOnlyHint == false`" for the second. The
vocabulary therefore crosses protocols without translation — a REST adapter would read the same
field — where Query/Command, the design vocabulary `docs/roadmap.md` also names, would be
translated at every channel. A `bool` rather than a two-valued enum because the name says all the
enum would. `destructive` and `idempotent` are not declared: they qualify a Tool that is not
read-only, which is the structure the specification gives them, and they join beside `read_only`
when a milestone needs them (M20 names idempotency).

`read_only` has no default because a default would classify every existing Tool silently. Every
Tool in this repository is classified by hand in this milestone. `read_only` is not a permission
and refuses nothing; it is what a policy, an audit record (M15) and the Agent channel's projection
read.

`channels` defaults to both because a Tool native to both channels is the premise of the
framework, not a decision hidden in a default. `required_roles` empty means anyone.

`Channel` is a closed enum, so a branch over it ends with `assert_never`.

### The Agent channel projects `read_only` as `readOnlyHint`, and nothing else

`to_mcp_tool` sets `annotations.readOnlyHint = True` for a read-only Tool and sets no other
annotation. This is the standard's own mechanism for what the declaration says, and it has a
measured effect: Codex asks the user before every MCP tool call whose annotations do not say
read-only, so without it the M18 authoring loop prompts on every `inspect_app`. A Tool that is not
read-only carries no annotation and is treated by Codex as possibly destructive, which is the right
answer for `remove_app` and an honest one for `submit_expense`: `destructiveHint: false` would
claim a distinction the declaration does not make. Claude Code reads its own `_meta` key instead,
which is platform-specific metadata and belongs to M19.

The annotation secures nothing — the specification says so — and nothing here relies on it.
Refusal is ToolRuntime's.

### Authorization is operation-level, decided in ToolRuntime before input validation

Authorization has two levels. *Operation-level*: may this principal, on this channel, invoke this
kind of operation at all. *Record-level*: may this principal act on this particular record. The
first needs only the declaration, the principal and the channel. The second needs the record, and
loading a record is domain work. OWASP separates them the same way.

The framework owns the first level and decides it in ToolRuntime, before input is validated. That
is where "rejected before handler execution" and "enforced through the canonical ToolRuntime path"
are one and the same fact. A rejected caller learns nothing about the input schema. The second
level is the handler's, reached through `ctx.principal`, and its refusals are the App's expected
failures, as data (ADR-029). No hook after validation exists and none is planned: whatever it
would check needs the record, which is the handler's job.

Recorded in ADR-034.

### One policy Protocol; the App may narrow, never widen

```python
@dataclass(frozen=True)
class AuthorizationRequest:
    definition: ToolDefinition[BaseModel, BaseModel]
    principal: Principal
    channel: Channel

class ToolPolicy(Protocol):
    def authorize(self, request: AuthorizationRequest, /) -> None: ...   # raise to refuse
```

The framework's default policy is one implementation of this Protocol: refuse when `channel` is
not in `definition.channels`; refuse when `definition.required_roles` is non-empty and disjoint
from `principal.roles`. It always runs. An App may set `policy` on its AppDefinition; that runs
after the default and can only add refusals. A bug in an App's policy can therefore not open a
Tool the declaration closed. One policy, not a chain: `runtime.md` forbids a middleware framework
before a concrete need, and the need is one.

### Channel is a window property; principal is an invocation property

ADR-017: one process is one channel, so the channel is fixed when a window opens.
`tool_runtime_for(definition, lifespan, *, config, channel)` takes it, and ToolRuntime holds it
beside `dependencies`. `page_runtime_for` passes `Channel.WEB`, because it *is* the Web
channel's window.

A principal is per call. One Web process serves many sessions; binding a principal to the window
would have to be undone the day a login exists. So:

```python
class ToolRuntime[DepsT]:
    async def invoke(self, name: str, raw_input: Mapping[str, object], /, *, principal: Principal) -> BaseModel
```

Pages do not see principals. `PageRuntime.render(name, *, principal)` builds a `ToolInvoker`
bound to that principal and puts it in the PageContext; `ToolInvoker`'s signature is unchanged.
PageRuntime therefore no longer holds a `ToolInvoker` but the thing it binds one from:

```python
class PrincipalToolInvoker(Protocol):        # vibepy_core.page.model
    def invoke(self, name: str, raw_input: Mapping[str, object], /, *, principal: Principal) -> Awaitable[BaseModel]: ...
```

ToolRuntime satisfies it structurally, and the Page package still imports nothing from the Tool
package: `Principal` and `Channel` live in `vibepy_core/principal.py` and `vibepy_core/channel.py`,
which belong to neither.

### ToolContext carries `principal` and `channel`

```python
@dataclass(frozen=True)
class ToolContext[DepsT]:
    app_id: str
    invocation_id: str
    dependencies: DepsT
    principal: Principal
    channel: Channel
```

A handler reads `principal` for record-level rules. `channel` is there for audit and policy
(`tool-model.md` allows exactly that) and the prohibition on domain branching stands as written.

### The host decides the principal, and the command that stands in for a host is told

| Host | Channel | Principal in M14 | Where decided |
| --- | --- | --- | --- |
| `vibepy_core.mcp` | `AGENT` | `Principal(id="agent")` | `mcp.py`, passed to `build_mcp_server(..., principal=)` |
| `vibepy_core.serve` | `WEB` | `Principal(id="operator")` | `serve.py`, passed to `build_web_app(..., principal=)` |
| `vibepy_core.invoke` | `--channel` | `--principal`, `--role` (repeatable) | the caller |

Adapters carry what they are given and decide nothing. `build_mcp_server` passes its principal to
every `invoke`; `build_web_app` passes it to every `render`. When a session-level identity arrives
the host's constant becomes a lookup and the adapters' signatures grow a resolver; nothing below
changes.

`vibepy_core.invoke` is a host that opens a window on behalf of another host, so channel and
principal are its arguments and are required. Its trust model is stdio's: whoever can run it
already holds the App's environment, so naming a principal there is no escalation. Its stdin keeps
its shape. Studio's `invoke_tool` forwards its own `ctx.channel` and `ctx.principal`, so a call an
agent verifies through Studio is authorized exactly as the agent's own call would be.

### Studio's exposure, as ADR-032 deferred it

| Tools | `channels` | `read_only` |
| --- | --- | --- |
| `inspect_framework`, `inspect_app` | `{AGENT}` | True |
| `invoke_tool` | `{AGENT}` | False (it runs a Tool that may write) |
| `list_apps`, `describe_config` | `{WEB}` | True |
| `install_app`, `remove_app`, `update_app`, `configure_app`, `start_app`, `stop_app`, `register_package_source`, `remove_package_source` | `{WEB}` | False |

No Studio Tool declares `required_roles`: exposure already isolates operating from the agent, and
every Web caller in M14 is the operator. A role the framework's host would have to grant is a role
the framework names, which the model forbids.

### Fixtures

Every Tool in `todo-app`, `notes-app` and `timer-app` declares `read_only`: True for
`list_todos`, `measure_note` and `elapsed`, False for `create_todo` and `complete_todo`. `channels` stays at its
default, which is each App's present truth.

`fixtures/expense-app` is added, the App `docs/roadmap.md` assigns to actor/role. Tools and no
Pages, depending on `vibepy-core[agent]` as Notes does; a lifespan yielding an in-memory store;
configuration `NoConfig`.

| Tool | `read_only` | `required_roles` | Behaviour |
| --- | --- | --- | --- |
| `submit_expense` | False | — | records `(id, submitter=ctx.principal.id, amount, status="submitted")` |
| `approve_expense` | False | `{"manager"}` | sets `status="approved"`; when `submitter == ctx.principal.id` returns an expected failure `expense.self_approval` as data, unchanged store |
| `list_expenses` | True | — | every record |

The fixture shows the two levels side by side: the role gate is the framework's and fires before
the handler, the self-approval rule is the App's and fires inside it. `vibepy-expense` joins the
`dev` dependency group and `[tool.uv.sources]`, as the other fixtures do, so the in-repository
commands can address it.

### A shape that crosses a process boundary is one pydantic model, owned by core

Adding three fields to `ToolDefinition` exposed a defect this milestone must not merge over: the
description surface is a hand-written copy of the declaration, not a projection of it. A Tool's
facts are written in `ToolDefinition`, copied by hand into `ToolDescription` (a dataclass),
serialized with `asdict`, and read back by Studio's own `DescribedTool` — three places to edit
for one field, and a field forgotten in any of them is silently absent from what an agent sees.
The failure report has the same shape of defect: `ErrorInfo` is a dataclass, `report_line` and
the MCP adapter's `_payload` each build its dict by hand, `_Report` reads it, and Studio's
`Diagnostic` re-declares the same four fields and copies them in `diagnostic_of`.

The repository's own rule already says what these should be: pydantic for data that crosses a
boundary, dataclasses for in-process declarations that hold types and callables. `AppDescription`'s
docstring says "this is what crosses a process boundary". The rule is applied:

- `ErrorInfo` becomes a `BaseModel` (`code`, `category: ErrorCategory`, `message`,
  `details: dict[str, str]`). `report_line` is `info.model_dump_json()`; `read_report_line` is
  `ErrorInfo.model_validate_json`, returning `None` for a line that is not one; the MCP adapter's
  payload is `info.model_dump(mode="json")`. `_Report` is deleted. A line naming a category the
  framework does not know is not a report line: pre-production, no tolerance for an older writer.
- Studio's `Diagnostic` is deleted; Studio's expected failures *are* `ErrorInfo` (ADR-029 already
  requires the same four fields). `diagnostic_of` becomes `ErrorInfo.model_copy(update=…)` for the
  merged details, or is deleted where nothing is merged. The Expense fixture's expected failure is
  an `ErrorInfo` too.
- `ToolDescription`, `PageDescription`, `AppDescription` become `BaseModel`s in core;
  `ToolDescription` gains `read_only`, `channels: list[Channel]`, `required_roles: list[str]`.
  `AppEntrypoint.describe()` remains the one place a declaration is projected. The `describe`
  command's per-App entry becomes a core model `DescribedApp` (`app_name`, `distribution`,
  `distribution_version`, and the `AppDescription` fields), written with `model_dump_json` and
  read by Studio with `model_validate`. Studio's `Described`, `DescribedTool`, `DescribedPage`
  are deleted in favour of the core models.
- `TypeAdapter` over the dataclasses is not the fix: pydantic documents it for types that must stay
  non-pydantic, and these types exist to cross a boundary.

In-process declarations — `ToolDefinition`, `AppDefinition`, `ToolContext`, `Principal`,
`AuthorizationRequest` — stay dataclasses. Studio's `_ConfigSchema` stays: it reads a slice of a
standard (JSON Schema), not a copy of a framework shape.

### Error

`ToolForbiddenError(name, *, principal, channel, reason)`: code `tool.forbidden`, category
`caller`. `details` carries `tool`, `principal` (the id), `channel` and `reason`, where `reason`
is `not_exposed`, `role_required`, or the string an App policy supplied. One code: the category
already tells a caller a different call may succeed, and `reason` tells it which.

The MCP adapter reports it as it reports every Tool error, an `isError` text block. The Web channel
translates nothing. `vibepy_core.invoke` reports it as one stderr line and exits 1.

## Data flow

```text
host opens a window                         channel fixed here
  tool_runtime_for(definition, lifespan, config=…, channel=AGENT)
    -> ToolRuntime(app_id, registry, dependencies, channel)

a call arrives                              principal fixed here
  MCP  call_tool(params)         -> runtime.invoke(name, args, principal=host's)
  Web  route builder             -> pages.render(name, principal=host's)
                                    -> PageContext(tools=bound(runtime, principal))
                                    -> page handler -> ctx.tools.invoke(name, raw)
  CLI  vibepy_core.invoke        -> runtime.invoke(name, stdin.input, principal=argv's)

ToolRuntime.invoke(name, raw_input, *, principal)
  1. registry.resolve(name)                         tool.not_found
  2. default policy: channel in channels?           tool.forbidden / not_exposed
                     roles ∩ required_roles ≠ ∅?    tool.forbidden / role_required
  3. app policy, if declared                        tool.forbidden / <app reason>
  4. ToolContext(app_id, invocation_id, dependencies, principal, channel)
  5. tool.bound(ctx, raw_input)                     input validation -> handler -> output validation
```

Steps 2 and 3 run before step 5's validation, and a handler is unreachable without them. Discovery
reads the same declaration: `list_tools` projects Tools whose `channels` contains `AGENT`, with
`readOnlyHint` for those declaring `read_only`; `register_pages` is unaffected (Pages have no
exposure; the Tools they call do).

## Testing

One file per subject; success and failure paths of a subject share its file.

| File | Subject |
| --- | --- |
| `tests/test_tool_authorization.py` | ToolRuntime: a Tool not exposed on the runtime's channel is `tool.forbidden` with `not_exposed`; a role-gated Tool with a principal lacking the role is `tool.forbidden` with `role_required`, and with the role runs; an App policy's refusal is `tool.forbidden` with its reason; in every refusal the handler did not run; a refusal with invalid input is `tool.forbidden`, not `tool.input_invalid`; an App policy that raises nothing cannot admit a Tool the default refused; a Tool with no `required_roles` runs for a principal with no roles |
| `tests/test_tool_core.py` | ToolContext carries `principal` and `channel`; `ToolDefinition` requires `read_only`; existing assertions with `channel` and `principal` supplied |
| `tests/test_page_core.py` | `render(name, principal=)` binds the principal: the ToolContext a Page's call reaches carries it; a Page handler sees a `ToolInvoker` of the unchanged shape |
| `tests/test_channel_neutrality.py` | one Tool declared for both channels yields the same output through both; the same Tool with `channels={AGENT}` is listed by the MCP adapter and refused through a Page, with the handler untouched |
| `tests/test_mcp_adapter.py` | `list_tools` omits a Tool without `AGENT`; a read-only Tool is projected with `annotations.readOnlyHint` true and a Tool that is not carries no annotations; calling it by name yields `isError` with the `tool.forbidden` payload; the principal the host passed reaches the handler |
| `tests/test_nicegui_adapter.py` | the principal the host passed reaches a Page's Tool call |
| `tests/test_invoke_command.py` | `--channel`, `--principal` required (argparse exit 2 with usage); against `expense-app`: `approve_expense` as `alice` is one stderr report `tool.forbidden` `role_required` and exit 1; with `--role manager` on another's expense exits 0 with `status: approved`; on one's own expense exits 0 with `expense.self_approval` in the output; `--channel web` on `measure_note` still runs (default `channels`) |
| `tests/test_errors.py` | `tool.forbidden` is in the catalogue as `caller`; `details` carries the four keys; `report_line` round-trips through `read_report_line` as the same `ErrorInfo`; a line with an unknown category or without `code` reads as `None` |
| `tests/test_describe_command.py`, `tests/test_app_entrypoint.py` | `describe` writes `DescribedApp` entries; a Tool's `read_only`, `channels`, `required_roles` appear in its description; `AppDescription` and `ErrorInfo` are pydantic models |
| `packages/vibepy-studio/tests/*` | Studio reads `DescribedApp` and reports `ErrorInfo`; assertions on `.diagnostic.code` etc. unchanged in meaning |
| `tests/test_app_distributions.py` | picks `expense-app` up by discovery; no edit expected |
| `tests/test_dual_channel.py`, `tests/test_execution_semantics.py` | unchanged in assertion; constructed with `channel` and invoked with `principal` |
| `packages/vibepy-studio/tests/test_authoring_over_mcp.py` | discovery lists exactly the three authoring Tools and no operating Tool; `invoke_tool` against `fixtures/expense-app` `approve_expense` yields a diagnostic from a `tool.forbidden` report, because the agent's principal has no role |
| `packages/vibepy-studio/tests/test_board*.py`, `test_invoke_tool.py` | operating Tools still run through the board; `invoke_tool` passes `--channel agent --principal agent` |

The constitutional tests (dual-channel, execution semantics) change only in construction and keep
their assertions.

## Compatibility

Pre-production; no shims. `ToolDefinition.read_only` is a new required field, `ToolRuntime.invoke`
gains a required keyword, `tool_runtime_for` and the two builders gain required keywords,
`PageRuntime.render` gains a required keyword, and `vibepy_core.invoke` gains two required
arguments. Every App in this repository is updated in the same change. Additions to the public
API: `Principal`, `Channel`, `ToolPolicy`, `AuthorizationRequest`,
`ToolForbiddenError`, `PrincipalToolInvoker`, `DescribedApp`, `AppDefinition.policy`,
`ToolContext.principal`, `ToolContext.channel`, `ToolDescription.{read_only,channels,required_roles}`.
`ErrorInfo`, `ToolDescription`, `PageDescription`, `AppDescription` change from dataclass to
`BaseModel`; construction by keyword is unchanged, `dataclasses.asdict` on them is not. The
`describe` command's JSON is the same keys; Studio's `Diagnostic`, `Described`, `DescribedTool`,
`DescribedPage` and core's `_Report` are removed.

## Documentation

- `docs/architecture/tool-model.md`: `read_only`, `channels`, `required_roles` move from "future
  metadata" to the definition; "Query and command" becomes "Side-effect semantics", in the present
  tense, owning the vocabulary and its RFC 9110/MCP lineage and stating that `read_only` refuses
  nothing; ToolRuntime's steps gain the two policy steps; a "Authorization" section owning
  the two levels, the default policy, the narrowing rule and `Principal`
- `docs/architecture/runtime.md`: ToolContext's current fields; "authorization" leaves the future
  list; channel as window property, principal as invocation property
- `docs/architecture/page-model.md`: `render` takes a principal, PageContext's invoker is bound to
  it, `PrincipalToolInvoker`
- `docs/architecture/adapters.md`: discovery filters by `channels` and projects `read_only` as
  `readOnlyHint`; the host passes the principal, the adapter carries it
- `docs/architecture/packaging.md`: `invoke`'s arguments and trust model; `serve` and `mcp` name
  their principal
- `docs/architecture/authoring.md`: `invoke_tool` forwards the agent's channel and principal;
  which Studio Tools are on which channel
- `docs/architecture/errors.md`: `tool.forbidden` row; `ErrorInfo` is a pydantic model and the one
  form every writer dumps and every reader validates, an App's expected failure included
- `docs/architecture/packaging.md`, self-description: `describe` writes `DescribedApp`;
  `docs/architecture/tool-model.md`: the rule "boundary shapes are pydantic, in-process
  declarations are dataclasses" is stated once, where ToolDefinition is described
- `docs/decisions/ADR-034-authorization-is-operation-level-in-toolruntime.md`: the two levels,
  why the framework owns one and decides it before input validation, the narrowing rule, and the
  alternatives — policy after validation, exposure as a policy check without a declaration, an
  App-level list of channel Tools, a chain of policies
- `docs/decisions/ADR-032-...`: no edit; its consequence is discharged by Studio's declarations,
  and `authoring.md` states the outcome
- `docs/roadmap.md`: never edited; Expense exists as it describes
- this folder is deleted on integration

## Out of scope

Authentication on either channel, and a per-session principal on the Web channel. Streamable HTTP
and MCP OAuth. Impersonation through `invoke_tool` (an authoring request that names a principal
other than the agent's). Refusals or confirmations driven by `read_only`. `destructive`,
`idempotent` and their annotations (M20). Platform-specific `_meta` such as
`anthropic/requiresUserInteraction` (M19). Audit of refusals (M15). Exposure of Pages. Customer. Reading more of a configuration schema than `_ConfigSchema` does.
