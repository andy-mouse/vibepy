# Error Model

## Principle

A framework failure is an exception. Inside Python the exception type is the contract; a
channel adapter catches a type and decides what its protocol does with it.

A Python type cannot cross a channel boundary. Every framework exception therefore also
carries a code, which is that type projected into something an agent can read, and a
message, which is for a human and is not a contract.

## Codes

A code is stable. The same code always means the same failure, two different failures never
share one, and a retired code is never reused. A milestone that adds an exception declares its
code on the class and maps its category in `vibepy_core/errors.py`.

| Code | Category | Exception |
| --- | --- | --- |
| `tool.not_found` | caller | `ToolNotFoundError` |
| `tool.input_invalid` | caller | `ToolInputValidationError` |
| `tool.output_invalid` | execution | `ToolOutputValidationError` |
| `tool.forbidden` | caller | `ToolForbiddenError` |
| `tool.name_conflict` | declaration | `ToolNameConflictError` |
| `page.not_found` | caller | `PageNotFoundError` |
| `page.route_invalid` | declaration | `PageRouteInvalidError` |
| `page.route_conflict` | declaration | `PageRouteConflictError` |
| `page.name_conflict` | declaration | `PageNameConflictError` |
| `config.invalid` | caller | `AppConfigInvalidError` |
| `package.entrypoint_unloadable` | declaration | `AppEntrypointUnloadableError` |
| `package.entrypoint_invalid` | declaration | `AppEntrypointInvalidError` |
| `package.app_not_declared` | caller | `AppNotDeclaredError` |

`app.unhandled` is the code for a failure the framework did not define. It belongs to no
exception class: an exception raised by an App's own code is described, not classified.

Two codes are retired and are never reused: `lifecycle.transition_forbidden` and
`lifecycle.not_running`, whose state machine no longer exists. The `lifecycle` category is
retired with them, because no code maps to it. See
`docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md`.

## Categories

A category says what kind of failure this is, independently of which one it is. A caller reads
it to learn whether a different call could succeed.

| Category | Meaning |
| --- | --- |
| `caller` | the call itself was wrong; a different call may succeed |
| `execution` | the call was well formed and running it failed; the same call fails again |
| `declaration` | the App declared something the framework rejects, raised at registration or at the point a package's declaration is read |

The set is closed and is an enum, so a branch over it ends with `assert_never` and a category
added later cannot be silently unhandled.

## ErrorInfo

`ErrorInfo` is one failure in the form every channel reports: `code`, `category`, `message`
and `details`. `to_error_info(error)` builds one from any exception. It crosses a process
boundary — `report_line` writes it and `read_report_line` reads it back — so it is one frozen
pydantic model the writer dumps and the reader validates, and a line naming a category the
framework does not know is not a report.

`details` carries every value the message interpolates, so an agent that needs to know which
Tool failed reads a mapping rather than parsing a sentence. This is what allows a message to
be reworded without breaking a client.

Classifying a failure is knowledge about the framework's own errors, so the framework owns it.
Were each adapter to classify, the channels could disagree about the same failure.

## What the framework does not do

Nothing is translated. An exception propagates to the caller as raised, and a handler's own
exception propagates unchanged. A lifespan that fails propagates to its host, which the host's
own contract already covers. Normalization is not wrapping: `to_error_info` is called where
a channel must render an answer, and nowhere else.

An App's own expected failures are not the framework's either. An App may publish an expected,
actionable failure as data inside its own output model, provided it carries `code`, `category`,
`message` and `details` — the same fields an `ErrorInfo` carries, so one reader parses both.
The table above stays the framework's, and an App's codes are the App's to publish and document.
See `docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md`.

## What each channel does

The Web channel translates nothing. A framework error or a handler exception raised during a
render reaches NiceGUI, which renders it. `docs/architecture/adapters.md` gives the reason.

A window that will not open reports its own failure in the `ErrorInfo` shape through `logging`
before it fails the server's startup. That is a record written beside the exception, not a
translation of it: the exception propagates as raised. It is what makes a failure of opening
legible to whatever started the process. See
`docs/decisions/ADR-030-a-window-reports-its-own-failure.md`.

The Agent channel answers every call, so it reports the normalized payload on both of its
paths: as JSON-RPC `data` for a protocol error, and as a JSON text content block for a result
marked `isError`. It does not use `structuredContent`, because a Tool declares an output schema
and the MCP specification requires structured results to conform to it
(<https://modelcontextprotocol.io/specification/2025-06-18/server/tools>).

A client ignores payload members it does not recognize, so a later milestone may add one.

## Related

- `docs/decisions/ADR-019-framework-errors-carry-stable-codes.md`
- `docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md`
- `docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md`
- `docs/decisions/ADR-030-a-window-reports-its-own-failure.md`
