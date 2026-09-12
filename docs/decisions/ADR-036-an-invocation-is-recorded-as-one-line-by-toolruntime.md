# ADR-036: An invocation is recorded as one line by ToolRuntime

Status: Accepted

## Context

Every invocation carried an id, a principal and a channel in its ToolContext, and `read_only`
was declared "for audit", yet nothing wrote any of it down. The id reached the handler alone;
a refused or unknown call had none, because the context was built after the policy ran. The
MCP adapter logged two human lines about handler failures and the Web adapter logged none, so
the channels were already observed differently. The three framework processes configured
logging three ways.

`docs/architecture/runtime.md` names ToolRuntime as where cross-cutting concerns are added and
forbids a middleware framework before a concrete need. `AGENTS.md` requires standard `logging`,
and one pydantic model for a value that crosses a process boundary. `docs/architecture/errors.md`
puts the classification of a failure in one place so that two reporters cannot disagree.

The conventions consulted: the Python Logging Cookbook (a library configures no handler; a
structured message is an object whose string form is JSON), the OpenTelemetry semantic
conventions for recording errors and for tool execution (a thrown exception is a failure; on
success no error attribute is set; tool arguments and results are opt-in and sensitive), OWASP's
Logging Cheat Sheet (when, where, who, what; log authorization and validation failures; exclude
sensitive data), the MCP specification on cancellation (log it, do not answer), asyncio on
`CancelledError` (catch, clean up, re-raise), and gRPC's status codes, where `CANCELLED` stands
apart from a client's and a server's errors.

## Decision

`ToolRuntime.invoke` writes exactly one `InvocationRecord` for every invocation it starts, as
the invocation ends, whatever way it ends — returned, raised, or cancelled — and re-raises what
it caught. The record is a frozen pydantic model in `vibepy_core.tool`: id, App, Tool, channel,
principal, start time, duration, and `error: ErrorInfo | None` as the outcome. No status field,
no arguments, no results. It is written as its JSON on the logger `vibepy_core.tool.runtime` at
INFO, with the traceback appended for an `execution` failure only. The framework configures no
handler; the three processes that run an App share one configuration in `vibepy_core.logs`.

The id is created before the Tool is resolved, so a refusal is recorded with one.

A cancellation is `tool.cancelled` in a new category, `interrupted`: the call was well formed,
the App was not at fault, something outside ended it, and the same call may succeed.
`to_error_info` classifies it, and its parameter widens to exactly
`Exception | asyncio.CancelledError`.

The MCP adapter's two log lines are removed; the record supersedes them.

Rejected:

- **OpenTelemetry** — an external dependency with no consumer here, and the MCP conventions
  that would give it a peer are at Development status. The record's fields map one-to-one
  onto the `execute_tool` attributes, so an exporter is a later adapter.
- **An observer protocol on AppDefinition** — a middleware seam before a concrete need, with no
  implementer in this repository.
- **A record per channel adapter** — two writers of one fact, which is what ToolRuntime exists
  to prevent.
- **A JSON logging library** — it formats arbitrary records and owns no schema, so a reader
  would re-declare the fields.
- **Classifying cancellation as `app.unhandled`** — false on both counts: not the App's, and
  not a failure that repeats. **A `finally` block** — cannot say what ended the invocation.
  **Recording `KeyboardInterrupt`** — the process ends, and reports its own ending (ADR-030).

## Consequences

- The Hub's per-App log file carries one structured line per Tool call on either channel, and
  a reader exists for it. Showing them in the Hub is proposed to the owner as a follow-up
  (`docs/milestones/M15/spec.md` at the time of writing; `docs/roadmap.md` thereafter).
- `ErrorCategory` has four members. A timeout code, when ADR-005's question is decided, joins
  `interrupted`.
- `ToolRuntime.invoke`'s signature is unchanged. A host that wants records elsewhere attaches a
  handler to `vibepy_core.tool.runtime`.
- A framework process's standard error is a stream of three kinds of line, and every reader of
  it parses line by line.
- Returning the invocation id to a caller (MCP `result._meta`, a Web response) is not decided
  here; the id exists to be returned when a channel needs it.
