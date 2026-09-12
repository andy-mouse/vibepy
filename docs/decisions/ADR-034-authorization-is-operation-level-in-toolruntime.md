# ADR-034: Authorization is operation-level, decided in ToolRuntime

Date: 2026-09-12

Status: Accepted

## Context

Every Tool call runs. ToolRuntime resolves a name, validates input and awaits the handler;
nothing asks who is calling or from where, and nothing in a declaration says which channel a
Tool is meant for. The cost is visible in Studio, whose operating Tools — `install_app`,
`remove_app`, `start_app`, `stop_app` — are projected onto MCP beside the authoring ones, so a
coding agent connected to Studio can uninstall an App. ADR-032 named this as the debt this
decision pays.

Neither channel authenticates anyone. The Web channel has no login. The Agent channel is stdio,
and the MCP specification defines authorization for HTTP transports only: a stdio implementation
"SHOULD NOT follow this specification, and instead retrieve credentials from the environment",
while a server nonetheless "MUST implement proper access controls"
(<https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization>,
<https://modelcontextprotocol.io/specification/2025-06-18/server/tools>). So the question is not
how a caller is authenticated — that is a channel technology's, and ADR-025 leaves it there —
but what the framework does once a caller is named.

OWASP splits access control into two levels and requires both to be checked server-side on every
request, "for the specific object or functionality being accessed": access to a type of object
is not access to every object of that type
(<https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html>). The two
levels differ in what they need. Deciding whether a caller may invoke an operation at all needs
the declaration, the caller and the channel. Deciding whether a caller may act on one record
needs the record, and loading a record is domain work.

## Decision

The framework owns operation-level authorization and decides it in ToolRuntime, before input is
validated, from the declaration (`channels`, `required_roles`), the principal the caller was
given by its host, and the channel the window opened on. The framework's default policy always
runs. An App may declare a policy of its own; it runs after the default and may only refuse,
never admit.

Record-level authorization is the handler's, reached through `ctx.principal`, and its refusals
are the App's expected failures, travelling as data (ADR-029). No hook after input validation
exists and none is planned.

The current contracts are `docs/architecture/tool-model.md`'s and
`docs/architecture/runtime.md`'s.

Rejected, and why:

- **authorizing after input validation**: a refused caller would learn the input schema by
  probing it, and a hook holding a validated payload invites record-level checks into the
  framework, which cannot load a record.
- **exposure as a policy check with no declared field**: discovery reads the declaration
  (ADR-027), so a Tool hidden only by a policy would still be listed to an agent, and the list
  and the refusal would come from two places.
- **an App-level list of Tools per channel**: a Tool's name would be written twice, and the two
  would drift. The facts about a Tool belong on the Tool.
- **a chain of policies**: `docs/architecture/runtime.md` forbids a middleware framework before
  a concrete need, and the need here is one policy deep.
- **a principal bound to the window**: one Web process serves many visitors, so the binding
  would have to be undone the day a login exists.

## Consequences

- a host names the principal it serves, and the framework derives none. In this repository each
  host names one constant, and the command that stands in for a host is told
- `ToolRuntime.invoke` gains a required principal, and a window gains a channel; every caller in
  this repository passes them
- a refusal is one error type, `ToolForbiddenError`, whose `reason` distinguishes an unexposed
  Tool, a missing role and an App's own refusal. One code, because the category already tells a
  caller that a different call may succeed
- a Tool is not classified as a query or a command. The side-effect vocabulary is `read_only`,
  RFC 9110's *safe* as MCP carries it, and it is declared for audit, policy and the Agent
  channel's `readOnlyHint` projection, not for refusal
- an App's policy defect can narrow its own App and cannot open what a declaration closed
- when authentication arrives on either channel, the host's constant becomes a lookup and the
  adapters' signatures grow a resolver. Nothing below the adapters changes, because the
  principal already travels per invocation
