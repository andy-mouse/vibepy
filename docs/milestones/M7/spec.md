# M7 - Structured error model: Design

## Acceptance criteria

From `docs/roadmap.md`:

- framework failures are represented with stable machine-readable error codes
- Tool, Page, lifecycle, and adapter failures can be distinguished consistently
- channel adapters preserve the same framework error semantics

## Sources

Every contract below either comes from a repository document or is an open decision that was
decided with the owner. Nothing is invented.

| Contract | Source |
| --- | --- |
| Exception types are the contract; message strings are not | `AGENTS.md` |
| Framework exceptions derive from a single base class | `AGENTS.md` |
| `Any` and `cast` are unacceptable in the public API | `AGENTS.md` |
| Exhaustive branches over typed unions end with `assert_never` | `AGENTS.md` |
| The milestone's acceptance criteria in the roadmap are the tests | `AGENTS.md` |
| A new architecture document requires a concept no existing document owns | `AGENTS.md` |
| An accepted ADR is superseded, never rewritten | `AGENTS.md` |
| The same fact is not stated in two documents | `AGENTS.md` |
| Errors are not translated; they reach the caller as raised | `docs/architecture/tool-model.md`, `page-model.md` |
| The three Tool errors and what raises each | `docs/architecture/tool-model.md` |
| A handler exception propagates unchanged | `docs/architecture/tool-model.md` |
| `PageNotFoundError` is raised by the registry | `docs/architecture/page-model.md` |
| Route format and uniqueness are validated where routes are registered | `docs/architecture/page-model.md`, `adapters.md` |
| The NiceGUI adapter translates nothing, because only MCP's protocol demands an answer to every call | `docs/architecture/adapters.md` |
| The MCP adapter translates validated Tool results and errors into MCP responses | `docs/architecture/adapters.md` (responsibility 4) |
| MCP types must not leak into the core Tool package | `docs/architecture/adapters.md`, ADR-003 |
| Future REST/CLI adapters are projections over the same ToolRuntime | `docs/architecture/adapters.md` |
| The two lifecycle errors, and why they are distinct failures | `docs/architecture/lifecycle.md` |
| Diagnostics should be machine-readable whenever practical | `docs/architecture/authoring.md` |
| `get_app_errors` is a future Authoring capability | `docs/architecture/authoring.md` |
| The adapter maps framework errors onto MCP by hand, an accepted cost | ADR-009 |
| `ToolOutputValidationError` exists because the framework publishes the schema | ADR-007 |
| Handler parameters are positional-only, so an author may name them freely | `docs/architecture/tool-model.md`, `page-model.md` |
| M9 and M16 produce structured diagnostics; M14 adds a rejection before handler execution; M15 owns invocation correlation; M10 aggregates several installed Apps | `docs/roadmap.md` |

External behaviour comes from official documentation. Each fact is cited where it is used:

- [MCP - Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools): a server
  MUST provide structured results conforming to a declared output schema; unknown tools are a
  protocol error, while execution failures are reported inside the result with `isError`
- [Google AIP-193 - Errors](https://google.aip.dev/193): the same identifier must always mean the
  same failure and never two different ones; information contributing to the message must appear
  in the structured metadata; a message may change over time only once a structured error exists
- [RFC 9457 - Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html): consumers must use
  the stable identifier rather than parse human-readable members; unrecognized extension members
  must be ignored; `instance` is the slot for an occurrence identifier
- [gRPC - Status codes](https://grpc.io/docs/guides/status-codes/): a closed canonical set exists
  so that a caller can tell whether retrying can change the outcome

Five questions no repository document answered were decided with the owner:

1. A code is added to each existing exception rather than replacing the type. Within Python the
   type remains the contract; the code is the projection of that type across a boundary a Python
   type cannot cross. See "Codes live on the exception class".
2. A closed category set exists alongside the specific code. See "Category is a closed set".
3. Normalization lives in the core as `ErrorInfo` and `to_error_info`, rather than each adapter
   classifying exceptions itself. See "ErrorInfo is the channel-neutral form".
4. The diagnostics M9 and M16 collect are a separate type, sharing this milestone's code
   namespace and nothing else. See "Non-goals".
5. An occurrence identifier is deferred to M15 and an error domain to M10, rather than being
   reserved now. See "Non-goals".

## Problem

Eight framework exceptions exist. Each was added by the milestone that needed it: M1 added the
three Tool errors, M2 added `PageNotFoundError`, M4 added the two route errors, M6 added the two
lifecycle errors. No milestone owned the error model itself, and four rounds of local decisions
left three inconsistencies.

A framework failure carries no machine-readable identifier. Across a channel boundary a Python
exception type cannot travel, so the MCP adapter sends `str(error)` and the English sentence
becomes the contract an agent reads. `AGENTS.md` states the opposite: exception types are the
contract, message strings are not. Today no agent can distinguish "your input was wrong, fix it
and retry" from "the App failed while running" without parsing prose.

`PageRouteInvalidError` and `PageRouteConflictError` are reachable only from `vibepy.errors`,
while the other six are exported from the package root.

The MCP adapter classifies failures by hand, one `except` clause per exception type
(`src/vibepy/adapters/mcp/server.py:72-83`). A second adapter would repeat that knowledge.

## Goal

Give every framework failure a stable machine-readable code and a channel-neutral normalized
form, so that a channel can report framework error semantics without the framework knowing which
channel is asking, and so that message strings stop being a contract.

M7 standardizes the eight errors that exist. It adds no new failure and changes no control flow.

## Non-goals

- Wrapping handler exceptions in a framework error. `tool-model.md`, `page-model.md` and
  `adapters.md` all state that errors are not translated, and they stay true.
- Translating errors in the NiceGUI adapter. `adapters.md` gives the reason: MCP wraps failures
  because its protocol demands an answer to every call, and the Web channel makes no such demand.
- An occurrence identifier on errors. RFC 9457 reserves that slot as `instance`; M15 owns
  invocation correlation and fills it.
- Separating an error domain from its reason, as AIP-193 does. Our namespace prefixes serve that
  role within one framework. M10 aggregates errors from several installed Apps, and the App
  identifier belongs to that decision.
- Diagnostics. M9 and M16 collect findings about static artifacts without raising anything; they
  need severity and a location, which a runtime failure has no use for. They share this
  milestone's code namespace and nothing else.

## Design

### Codes live on the exception class

Each exception carries a `code` class constant. A milestone that adds an error adds it in its own
module rather than editing a central enumeration.

Adopted from AIP-193 as a contract, not as a convention: the same code must always mean the same
failure, and two logically different failures must never share a code. A code is never reused
after removal and never redefined.

| Code | Category | Exception |
| --- | --- | --- |
| `tool.not_found` | caller | `ToolNotFoundError` |
| `tool.input_invalid` | caller | `ToolInputValidationError` |
| `tool.output_invalid` | execution | `ToolOutputValidationError` |
| `page.not_found` | caller | `PageNotFoundError` |
| `page.route_invalid` | declaration | `PageRouteInvalidError` |
| `page.route_conflict` | declaration | `PageRouteConflictError` |
| `lifecycle.transition_forbidden` | lifecycle | `AppRuntimeTransitionError` |
| `lifecycle.not_running` | lifecycle | `AppRuntimeNotRunningError` |

### Category is a closed set

A category answers what kind of failure this is, independently of which one it is. gRPC keeps a
closed set of canonical codes for exactly this reason: a caller learns whether retrying can
change the outcome. AIP-193 layers a specific reason over a canonical code the same way.

- `caller` - the call itself was wrong. A different call may succeed.
- `execution` - the call was well formed and running it failed. The same call fails again.
- `lifecycle` - the App is not in a state that permits the call.
- `declaration` - the App declared something the framework rejects. Raised at registration, before
  any caller exists.

Category is an enum, so an adapter branching over it exhaustively ends with `assert_never` and a
category added by M14 cannot be silently unhandled.

### ErrorInfo is the channel-neutral form

A frozen dataclass in `vibepy/errors.py`, carrying `code`, `category`, `message` and `details`.
It imports nothing from any adapter.

`details` is a `Mapping[str, str]`. AIP-193 requires that any request-specific information
contributing to the message be present in the structured metadata, and every framework message
interpolates such a value: `tool_name`, `page_name`, `route`, `state`, `transition`. Each becomes
a `details` entry. An agent that needs to know which Tool failed reads `details`, never the
sentence.

A normalization function converts an exception into an `ErrorInfo`. A framework error contributes
its own code, category and details. Any other exception normalizes to `app.unhandled` in the
`execution` category, because a failure the framework did not define came from the App's own code
and running it is what failed. `app.unhandled` belongs to no exception class and carries no
details: the framework knows nothing about the value it received. Normalizing
is not wrapping: the exception still propagates unchanged, and normalization happens only where a
channel must render an answer.

### What the MCP adapter sends

The MCP specification states that when a tool declares an output schema, servers MUST provide
structured results that conform to it. Every Tool declares one (`projection.py:19`), so an error
payload cannot travel in `structuredContent`. It travels as JSON in a text content block, which
is the shape the specification's own error example uses.

The protocol/result split stays where it is. The specification names unknown tools as a protocol
error, so `tool.not_found` remains an `MCPError`; every other failure remains a result with
`is_error`. Category does not drive this mapping today. It is what the agent reads to decide
whether to retry, and what a future REST adapter maps to 4xx or 5xx.

Clients must ignore payload members they do not recognize, per RFC 9457, so M14 and M15 can add
fields without breaking an agent written against M7.

### Uniform exports

`PageRouteInvalidError` and `PageRouteConflictError` join the package root exports. Once a code is
a contract, an error that cannot be caught where the others are caught is an inconsistency, not a
choice.

## Public API

### ErrorCategory

```python
class ErrorCategory(StrEnum):
    CALLER = "caller"
    EXECUTION = "execution"
    LIFECYCLE = "lifecycle"
    DECLARATION = "declaration"
```

A `StrEnum` because the value crosses a channel boundary as a string and reads as itself in a
JSON payload, while remaining a closed type a branch can exhaust with `assert_never`.

### VibepyError

```python
class VibepyError(Exception):
    code: ClassVar[str]

    def details(self) -> Mapping[str, str]: ...
```

`code` is declared on the base without a value, so a subclass that forgets one fails the
catalogue test rather than inheriting a meaningless default. `category` is not a field on the
exception: it is a property of the code, and the normalization function owns that mapping.

`details` returns the values the subclass interpolates into its message. Each subclass overrides
it; the base returns an empty mapping.

### ErrorInfo

```python
@dataclass(frozen=True)
class ErrorInfo:
    code: str
    category: ErrorCategory
    message: str
    details: Mapping[str, str]
```

### Normalization

```python
def to_error_info(error: Exception, /) -> ErrorInfo: ...
```

Positional-only, matching the parameter convention the Tool and Page handler protocols already
use. A `VibepyError` contributes its own code, details and mapped category; any other exception
yields `app.unhandled` in the `EXECUTION` category with empty details.

### Exports

`ErrorCategory`, `ErrorInfo` and `to_error_info` join the package root, as do
`PageRouteInvalidError` and `PageRouteConflictError`. `test_package.py` asserts the full export
list, so it is updated in the same change.

## Contract changes

The text of an MCP failure result changes from an English sentence to a JSON object. An agent
reading the prose breaks. This is intended: the prose was never a contract, and introducing codes
is what frees the message. AIP-193 draws the same line, requiring a stable message only from APIs
that carry no structured error. ADR-019 records it.

Adding exports and adding attributes to existing exceptions is backward compatible. No exception
is renamed, removed, or given a new base class.

## Verification

- Every `VibepyError` subclass has a code that is non-empty, namespaced, and unique across the
  framework. One test walks the subclasses and is the catalogue's guarantee.
- Every framework exception normalizes to an `ErrorInfo` whose `details` contain each value its
  message interpolates.
- Normalizing an exception the framework did not define yields the `execution` category.
- Through a real MCP client: an unknown Tool is a protocol error; invalid input and a raising
  handler are results whose payload carries the expected code and category.
- The NiceGUI adapter still translates nothing. A Tool error raised during a render reaches the
  caller unchanged.
- `make lint typecheck test` passes.

## Documentation

`docs/architecture/errors.md` is new. No existing document owns the error model as a whole:
`tool-model.md`, `page-model.md`, `adapters.md` and `lifecycle.md` each describe the errors of
their own subject. That scattering is the concept M7 introduces, so the new document is
warranted.

It carries the code catalogue, the category set, and the normalization contract. The four
existing documents keep their behavioural statements and reference the catalogue instead of
restating it. Removing that duplication is part of the milestone, not a follow-up.

ADR-019 records that framework errors carry stable codes and that adapters read a normalized
form. It adds to the ADR record; it supersedes nothing, because no accepted ADR decides the error
model.
