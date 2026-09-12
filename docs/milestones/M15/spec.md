# M15 - Observability and audit

Date: 2026-09-12

## Acceptance criteria

From `docs/roadmap.md`, verbatim:

- canonical Tool invocations can be correlated through invocation identifiers
- channel, actor, timing, and execution status are observable
- observability applies consistently across Web- and Agent-originated Tool calls

## Sources

| Contract | Source |
| --- | --- |
| All channel invocation converges at ToolRuntime; audit, tracing and metrics are named there as future cross-cutting concerns; no middleware framework before a concrete need | `docs/architecture/runtime.md` |
| ToolRuntime creates a ToolContext per invocation with an invocation id unique to it; channels never construct one | `docs/architecture/runtime.md`, ToolContext |
| `invoke` resolves, authorizes, creates the context and awaits the Tool; nothing translates an exception | `docs/architecture/tool-model.md`, ToolRuntime |
| A framework failure is an exception with a stable code; `ErrorInfo` is one failure in the form every channel reports; classifying a failure is the framework's knowledge, so one place classifies; a code is declared by the milestone that adds it | `docs/architecture/errors.md` |
| Categories are a closed enum a branch exhausts with `assert_never`, so a category added later cannot be silently unhandled | `docs/architecture/errors.md`, Categories |
| A value that crosses a process boundary is one pydantic model owned by `vibepy_core`; the writer dumps, the reader validates, nobody re-declares its fields | `AGENTS.md`, Python conventions |
| Standard `logging` only, `getLogger(__name__)` per module | `AGENTS.md`, Python conventions |
| Channel adapters are thin and own no business logic | `docs/decisions/ADR-003-channel-adapters-are-thin.md` |
| A window reports its own failure as one report line on standard error; Studio finds it by parsing each line, not by position | `docs/decisions/ADR-030-a-window-reports-its-own-failure.md`, `vibepy_studio/internals/processes.py` |
| `read_only` and `channel` are what "a policy, an audit record and the Agent channel's projection read" | `docs/architecture/tool-model.md`, Side-effect semantics |
| Timeouts and cancellation are not yet defined | `docs/decisions/ADR-005-tool-handlers-async-first.md` |
| `extra=` populates the LogRecord's `__dict__` with user-defined attributes, intended for "specialized circumstances, such as multi-threaded servers where the same code executes in many contexts"; keys must not clash with the record's own | Python `logging` reference, `Logger.debug` |
| "Configuring logging by adding handlers, formatters and filters is the responsibility of the application developer, not the library developer"; a library adds nothing but a `NullHandler`; a library documents the logger names it uses | Python Logging Cookbook, "Patterns to avoid"; Logging HOWTO, "Configuring Logging for a Library" |
| Structured logging: an object whose `__str__` is JSON is passed as the message, printed by a `%(message)s` formatter | Python Logging Cookbook, "Implementing structured logging" |
| `uvicorn.run(log_config=...)` takes a `dictConfig` dictionary | <https://github.com/kludex/uvicorn/blob/main/docs/concepts/logging.md> |
| `CancelledError` subclasses `BaseException`; "in almost all situations the exception must be re-raised"; clean-up is done in `try/finally` and the exception propagated after it | Python `asyncio` reference, Exceptions and Task Cancellation |
| Receivers of `notifications/cancelled` SHOULD stop processing, free resources and not send a response; both parties SHOULD log cancellation reasons | MCP specification 2025-06-18, Cancellation |
| The SDK's default peer-cancel mode `"interrupt"` cancels the handler's scope, so the request handler sees `CancelledError`; the cancelled request is never answered | MCP Python SDK 2.1.1, `mcp.shared.jsonrpc_dispatcher`, `PeerCancelMode` |
| An operation is failed if it throws an exception; on failure set status `Error` and `error.type`; on success set neither | OpenTelemetry semantic conventions, "Recording errors" |
| `error.type` is "a class of error the operation ended with", low cardinality — an error code or the exception's canonical class name; not set on success | OpenTelemetry semantic conventions, `error.type` |
| Tool execution has a span convention (`execute_tool`, `gen_ai.tool.name`, `gen_ai.tool.call.id`, `error.type`); tool arguments and results are Opt-In and "may contain sensitive information"; status Development | OpenTelemetry GenAI semantic conventions, "Execute tool span" |
| MCP instrumentation propagates trace context in `params._meta`; status Development | OpenTelemetry semantic conventions for MCP |
| An event records when (date and time, interaction identifier), where (application identifier, name and version), who (user identity) and what (type, severity, description); log authorization failures and input validation failures; never log secrets, tokens or sensitive personal data | OWASP Logging Cheat Sheet, "Event attributes", "Which events to log", "Data to exclude" |
| `CANCELLED` — "the operation was cancelled, typically by the caller" — is a status of its own beside `INVALID_ARGUMENT` and `INTERNAL`; `DEADLINE_EXCEEDED` stands next to it | gRPC status codes, <https://grpc.io/docs/guides/status-codes/> |

## Problem

Every invocation already carries an id, a principal and a channel in its ToolContext, and
`read_only` is declared "for audit". Nothing writes any of it down. The id is visible to the
handler alone, so nothing outside a process can say which call a handler's own log line belongs
to, and a refused or unknown call never receives an id at all because the context is built
after the policy runs. Timing is measured nowhere. What a Tool call did, for whom, from which
channel, and how it ended is not observable on either channel, and the two channels are not even
asymmetric in the same way: the MCP adapter logs two human lines about handler failures and the
Web adapter logs none.

The three framework processes also configure logging three ways. `serve` has a `dictConfig`
that writes `vibepy_core` records at ERROR as their message alone, `mcp` calls `basicConfig` at
ERROR, and `invoke` configures nothing. One fact — how a framework process writes what it
reports on standard error — is stated three times and already disagrees. A record added by
patching each would be the fourth statement.

## Decision: one record per invocation, written by ToolRuntime

`ToolRuntime.invoke` writes exactly one record for every invocation it starts, at the moment
the invocation ends, whatever way it ends. Nothing else observes. No hook, no observer
protocol, no middleware: the log is the audit trail, and `logging` is the hook — a host that
wants the records elsewhere attaches a handler to the documented logger, which is what the
library's own conventions say a host does.

Rejected, and why:

- **OpenTelemetry**: an external dependency for a framework that has no consumer of spans,
  and the MCP conventions that would give it a peer are at Development status. The record's
  fields map one-to-one onto the GenAI `execute_tool` attributes — `tool` to
  `gen_ai.tool.name`, `invocation_id` to `gen_ai.tool.call.id`, `error.code` to `error.type`
  — so an exporter is a later adapter, not a redesign.
- **an observer protocol on AppDefinition**: `docs/architecture/runtime.md` forbids a middleware
  framework before a concrete need, and no App in this repository would implement it.
- **a record per channel adapter**: the channels would disagree about the same invocation, which
  is the defect ToolRuntime exists to prevent. ADR-003 keeps adapters thin.
- **a JSON logging library**: it formats arbitrary records and owns no schema, so a reader would
  re-declare the fields; `AGENTS.md` puts the schema in one pydantic model instead.

### The record

`InvocationRecord` is a frozen pydantic model owned by `vibepy_core`:

```python
class InvocationRecord(BaseModel):
    invocation_id: str
    app_id: str
    tool: str
    channel: Channel
    principal: Principal
    started_at: datetime        # timezone-aware UTC; RFC 3339 in JSON
    duration_seconds: float     # monotonic clock, time.perf_counter
    error: ErrorInfo | None     # None: the Tool returned
```

- OWASP's when / where / who / what is `started_at` and `invocation_id` / `app_id` / `principal`
  / `tool`, `channel`, `error`. The App's version is not repeated per record: one process is one
  App version, and `describe` already publishes it.
- There is no `status` field. OpenTelemetry leaves status unset and `error.type` absent on
  success, and `docs/architecture/errors.md` says the same fact is not stated twice: the
  invocation failed exactly when `error` is present, and how it failed is `error.code`.
- `error` is `ErrorInfo` whole, not a projection of it. It is already the one shape every
  reporter uses, and its `code` is the low-cardinality class OpenTelemetry asks of `error.type`.
- Arguments and results are not recorded. OWASP excludes sensitive data and OpenTelemetry makes
  both Opt-In with a sensitivity warning; a Tool's payload is the App's data, not the framework's
  to write down.
- `started_at` is the wall clock for the auditor; `duration_seconds` is the monotonic clock for
  the measurement, in seconds as the MCP duration metrics are.

The record is written as `logger.info(record.model_dump_json())` on the logger
`vibepy_core.tool.runtime` — the module's own `getLogger(__name__)`, documented in
`docs/architecture/runtime.md` as the HOWTO requires. The framework adds no handler. It is read
back by `read_invocation_record(line) -> InvocationRecord | None`, the pair to
`read_report_line`, kept beside the model. A line is a report or a record or neither, never
both: the two models do not validate each other's lines, and a test holds that.

### When it is written

```text
invoke(name, raw_input, principal)
  1. invocation_id, started_at, perf_counter          ← before anything can refuse
  2. resolve → default policy → App policy
  3. ToolContext, carrying the same invocation_id
  4. await tool
  ├ returned:        record(error=None)
  ├ CancelledError:  record(error=tool.cancelled)      then re-raise
  └ Exception:       record(error=to_error_info(exc))  then re-raise
```

The id moves to the front so a refusal and an unknown name have one. OWASP names
authorization failures and input validation failures among the events that must be logged, and
a refused caller that left no trace would be the audit gap the record exists to close. The
handler's `ctx.invocation_id` and the record's are one value.

Nothing is translated. The exception propagates as raised, exactly as
`docs/architecture/errors.md` says; the record is written on the way out.

Cancellation is recorded. The SDK's default mode cancels the handler's scope on
`notifications/cancelled`, so `CancelledError` is raised inside `invoke` today; the specification
says both parties should log it, OpenTelemetry counts a thrown exception as a failure, and
asyncio says catch, clean up, re-raise. `KeyboardInterrupt` and `SystemExit` are not recorded:
they end the process, not the invocation, and the process reports its own ending (ADR-030).
Two `except` arms rather than one `finally`, because the record must say what ended the
invocation and `finally` does not know.

The record for an `execution` failure — `app.unhandled`, `tool.output_invalid` — is written with
`exc_info`, so the formatter appends the traceback after the JSON line. Only that category is a
defect in code a developer must find; a caller's mistake, a declaration's, or an interruption has
no stack worth keeping. This is where the two human lines the MCP adapter writes today go: the
record supersedes them, and the traceback they carried now follows the record on either channel.

### A new code and a new category

`tool.cancelled` is the code for an invocation the outside interrupted. Like `app.unhandled` it
belongs to no framework exception class: `asyncio.CancelledError` is asyncio's and is not
wrapped.

It needs a category none of the three fits. `caller` says a different call may succeed;
`execution` says the same call fails again; `declaration` says the App is wrong. A cancelled
call was well formed, the App was not at fault, and the same call may well succeed. gRPC makes
this a status of its own — `CANCELLED`, with `DEADLINE_EXCEEDED` beside it — distinct from its
client-error and server-error codes, and OpenTelemetry would write the exception's class name.
The category is `interrupted`: the call was well formed and something outside it ended the
execution; the same call may succeed. When ADR-005's open question is decided, a timeout code
joins it there, which is what makes it a category and not a home for one code.

`to_error_info` classifies it, because `docs/architecture/errors.md` puts classification in one
place so that two reporters cannot disagree. Its parameter widens from `Exception` to
`Exception | asyncio.CancelledError` — precisely that, not `BaseException`, so that a
`KeyboardInterrupt` cannot be described as `app.unhandled` by falling through.

## One logging configuration for the framework's processes

One module in `vibepy_core` owns the `dictConfig` dictionary the three commands share. `serve`
passes it to `uvicorn.run(log_config=...)`; `mcp` and `invoke` apply it with
`logging.config.dictConfig`. Its content is `serve`'s today with one change: the `vibepy_core`
logger at INFO instead of ERROR, still to standard error, still as the message alone. The
framework has no INFO call today, so the only new lines are the records.

Only the `vibepy_core` namespace is configured. An App's own loggers (`vibepy_studio.*`) are
left to Python's defaults, as the Cookbook leaves a library's loggers to the application; a
framework process applies its one-line JSON convention to what it writes itself and does not
decide how an App's text is written. The `uvicorn` loggers are unchanged.

A framework process's standard error therefore carries three kinds of line: a report
(`ErrorInfo`), a record (`InvocationRecord`), and everything else — a traceback after an
`execution` record, uvicorn's own lines. Every reader already parses line by line and skips what
does not validate; Studio's `reported` needs no change and finds no report in a record.

## Data flow

```text
Page / MCP client ──▶ adapter ──▶ ToolRuntime.invoke ──▶ Tool
                                        │
                                        └─ logger.info(InvocationRecord json)
                                                 │
                                   vibepy_core logger (INFO, %(message)s) ──▶ stderr
                                                 │
                        serve / mcp / invoke process ──▶ Hub: <root>/logs/<app>.log
                                                     └─▶ terminal or MCP client
```

Studio is an App like any other, so its Hub and authoring Tools produce the same records with
`app_id` `vibepy-studio`; nothing is special-cased.

## Testing

- `tests/test_tool_observability.py`, one subject: the record. Through `caplog` on ToolRuntime:
  a returned Tool leaves one record whose fields are filled and whose `invocation_id` is the
  one the handler saw; an unknown name, a refusal, invalid input, a handler exception and a
  cancellation each leave one record carrying the matching `ErrorInfo` and propagate as raised;
  a traceback follows an `execution` record and no other; the same Tool invoked through
  PageRuntime and through the MCP adapter leaves two records that differ in `channel`,
  `principal` and `invocation_id` alone; a record line is not a report and a report line is not
  a record; `read_invocation_record` round-trips.
- `tests/test_errors.py`: the catalogue gains `tool.cancelled` and `interrupted`, so the existing
  catalogue tests cover them; `to_error_info(CancelledError())` classifies as that code.
- `tests/test_invoke_command.py`, `tests/test_mcp_command.py`, `tests/test_serve_command.py`:
  one test each that a record line reaches the process's standard error. Whether INFO reaches
  the stream is a fact about the process and is proven only by one.

## Compatibility

`ToolRuntime.invoke`'s signature does not change. `to_error_info` accepts what it accepted.
`ErrorCategory` gains a member; no framework branch over it exists outside `errors.py`, and
Studio constructs categories without branching on them. The MCP adapter's two log lines are
removed, superseded by the record. `serve`'s standard error carries INFO records where it
carried ERROR alone; Studio's reader is unaffected.

## Documentation

- `docs/architecture/runtime.md`: the record, the logger name, when it is written; audit and
  tracing leave the list of future concerns; the invocation id exists before authorization.
- `docs/architecture/tool-model.md`: `invoke`'s steps, id first and record last.
- `docs/architecture/errors.md`: `tool.cancelled` in the code table, `interrupted` in the
  category table, `to_error_info`'s parameter, `InvocationRecord` as a boundary model.
- `docs/architecture/packaging.md`: a command's standard error carries one record per invocation
  beside its report line.
- `docs/architecture/adapters.md`: whatever mentions the adapter's own failure logging.
- `docs/decisions/ADR-036`: an invocation is recorded as one line by ToolRuntime; the
  alternatives above; the new category.

## Out of scope

Showing records in the Hub (below). Returning the invocation id to a caller through MCP
`result._meta` or a Web response. Trace-context propagation. Configuring an App's own loggers,
or a `contextvars` filter that stamps a handler's own lines with the invocation id. Recording
arguments or results. Timeouts, whose code will join `interrupted` when ADR-005's question is
decided. A verbosity option on the commands.

## Follow-up proposed to the owner: the Hub shows an App's invocation records

The Hub is the operator's console for installed Apps (ADR-024), it already writes each App's
standard error to `<root>/logs/<app>.log`, and after this milestone that file carries one
structured record per Tool call. Operator consoles conventionally show an application's log
beside the application, and OWASP treats logging as incomplete until the log is reviewed. The
records are therefore worth a view: a Tool that reads an App's recent records through
`read_invocation_record`, and a Page on the board that shows them per App row.

It is not this milestone. The acceptance criteria end at "observable", `docs/roadmap.md` has no
such item, and it is a Tool and a Page with a design of their own. This milestone leaves the
format and its reader in the framework so that the view, when the owner schedules it, reads
rather than re-declares. Suggested as a follow-up item after M15, or a milestone after M16.
