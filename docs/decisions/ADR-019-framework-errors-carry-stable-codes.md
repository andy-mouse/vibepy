# ADR-019: Framework errors carry stable codes and adapters read a normalized form

Status: Accepted

## Context

Eight exceptions accumulated across M1, M2, M4 and M6, each added by the milestone that needed
it. `AGENTS.md` states that exception types are the contract and message strings are not, but a
Python type cannot cross a channel boundary. The MCP adapter therefore sent `str(error)`, which
made an English sentence the only thing an agent could act on, and classified failures itself
with one `except` clause per type, knowledge a second adapter would have to repeat.

Google AIP-193 requires a structured error precisely so a client never parses a message, and
notes that a message may change over time only once one exists (<https://google.aip.dev/193>).
RFC 9457 states that consumers must use the stable identifier rather than the human-readable
members (<https://www.rfc-editor.org/rfc/rfc9457.html>). gRPC keeps a closed canonical set
alongside the specific error so a caller can tell whether retrying can change the outcome
(<https://grpc.io/docs/guides/status-codes/>).

## Decision

Every framework exception carries a stable `code` and reports the values its message
interpolates through `details()`. A closed `ErrorCategory` accompanies the code. `ErrorInfo` and
`to_error_info` in the core describe any exception in a channel-neutral form, and adapters read
that form instead of classifying exceptions themselves.

Errors are still not translated. Normalization happens only where a channel must render an
answer.

## Consequences

- an agent reads `code` and `category` rather than a sentence, so a message may be reworded
- the text of an MCP failure changes from an English sentence to a JSON object; an agent that
  parsed the prose breaks, which is accepted because the prose was never a contract
- a milestone that adds an exception must declare a code and map a category, and a test that
  walks every subclass enforces both
- one classification exists for all channels, so the Web, Agent and any future adapter cannot
  disagree about the same failure
- a code is permanent: it is never reused for a different failure and never redefined
