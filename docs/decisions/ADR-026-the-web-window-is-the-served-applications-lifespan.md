# ADR-026: The Web window is the served application's own lifespan

Status: Accepted; the stdin configuration sentence superseded by ADR-033

Amendment, appended: `serve` reads its configuration from the environment since ADR-033, and the
standard input this record names is deprecated.

## Context

ADR-020 gives the running window to the channel host and leaves each host to open it with its own
documented mechanism. The Agent channel had one: the MCP SDK takes a lifespan and enters it
inside `run()`. The Web channel's mechanism was chosen when that decision was implemented and was
never recorded, so three things are in the code with no document behind them: a direct dependency
on `fastapi` and `uvicorn`, an ASGI lifespan as the window, and a second framework command.

The Web technology's own hooks cannot carry a window. It documents `app.on_startup` and
`app.on_shutdown` and nothing that passes state between them, and its documentation says when a
hook runs and nothing about a hook that raises — so a refusal to open would leave a server
answering for an App that never started.

ASGI defines the meaning that is missing. A lifespan that fails sends `lifespan.startup.failed`,
and "if a server sees this it should log/print the message provided and then exit"
(<https://asgi.readthedocs.io/en/latest/specs/lifespan.html>). A window that will not open then
fails the process rather than being swallowed.

Reaching the window from a request is not available and is not needed. The same spec passes
lifespan state to requests as a shallow copy of a namespace, but the Web technology mounts as a
sub-application and no source promises that state reaches one. A page builder is a callable the
adapter constructs, so it closes over the runtime it renders through — a language guarantee
rather than a library one, which is the argument ADR-020 already made.

The dependency adds nothing to an App. The Web technology itself requires `fastapi`, `starlette`
and `uvicorn[standard]`, so all three are in an App's tree already; declaring `fastapi` states
what this package imports rather than adding weight. `starlette` alone would serve the lifespan,
but the mounting call the Web technology documents takes a FastAPI application.

## Decision

The Web channel's window is the lifespan of the ASGI application the framework hands back.
`build_web_app` returns that application and runs nothing.

The framework depends on `fastapi` and `uvicorn` directly, as `vibepy-core[web]` under ADR-025.

`python -m vibepy.serve` runs one App's Web channel under that App's own interpreter, reading its
configuration from standard input. It is the twin of `python -m vibepy.describe`, which ADR-023
established for the same reason: what requires an import happens on the App's side of a process
boundary.

## Consequences

- a window that refuses to open exits the process with a non-zero status, which is what makes a
  refusal legible to whatever started it
- the framework holds no server object and no port. Whoever owns the process chooses both
- a second framework command exists, so `docs/architecture/packaging.md` owns two command
  contracts rather than one
- the Web channel's routes are registered on the technology's process-global table inside the
  window, and this decision does not make them leave with it. What the window owns is the
  resource, not the routes
