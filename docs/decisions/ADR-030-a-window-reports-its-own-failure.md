# ADR-030: A window reports its own failure

Status: Accepted

## Context

ADR-026 makes an App's Web window the served application's ASGI lifespan. ASGI's answer for a
window that will not open is that a server seeing `lifespan.startup.failed` logs the message and
exits (<https://asgi.readthedocs.io/en/latest/specs/lifespan.html>). That is legible to a person
reading a terminal.

It is not legible to a caller. The Hub starts an App as a child process and reads an exit status,
so every failure of opening — a configuration the window refuses, a lifespan that raises, a
declaration the adapter rejects — arrived at the Hub as one undifferentiated `hub.start_failed`,
even where the framework had normalized that same failure into a code, a category and details
inside the child. `docs/architecture/errors.md` names `config.invalid` as `caller`, meaning a
different call could succeed; across the process boundary that distinction was lost, and the Hub
told its caller "execution" for a failure the caller could have fixed.

## Decision

A window reports the normalized failure of its own opening through `logging`, in the `ErrorInfo`
shape, and then re-raises. Whoever owns the process routes that record where its caller reads it:
`vibepy_core.serve` writes framework records to standard error as one JSON object per line, and
the Hub gives each child a standard-error file of its own and reads the last such object back
when a start fails.

## Consequences

- any failure of opening crosses a process boundary with a `code`, a `category` and `details`
- the exception is still propagated unchanged and the server still fails its startup, so ADR-026
  is untouched and `errors.md`'s "the Web channel translates nothing" holds: a report written
  beside a failure is not a translation of an answer
- a host that embeds `build_web_app` in its own application sees one `ERROR` record it can route
  or silence like any other
- the Hub answers `start_app` with the code the child reported, and keeps `hub.start_failed` for
  a child that reported nothing — one that was killed, or never reached the framework at all
- a category the Hub does not recognize degrades to `execution` rather than failing the answer
- validating the configuration inside the command before the server sees it was rejected: it
  fixes one code and leaves every other window failure as prose, and ADR-022 puts validation in
  the window
- reading the server's own state for what went wrong was rejected: uvicorn documents no such
  interface
