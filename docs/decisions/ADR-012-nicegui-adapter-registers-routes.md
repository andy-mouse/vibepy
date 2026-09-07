# ADR-012: The NiceGUI adapter registers routes and does not run the server

Status: Accepted

## Context

The Web server lives inside the app process, unlike a stdio MCP server, so the Web adapter
could legitimately own its own startup. It has nothing to start it from: no runtime lifecycle
exists to own startup, so an adapter that ran a server would define startup itself and the
lifecycle would have to take it back.

NiceGUI registers routes on a process-global object and removes any route already at a path
before registering, so a second registration of one path silently replaces the first and no
collision is reported.

## Decision

Registering routes is separated from running a server. The adapter projects Page declarations
onto routes and returns, holding no server object.

Route format and uniqueness are validated by the adapter before any route is registered,
because NiceGUI reports no collision of its own.

## Consequences

- the Web channel is testable in-process, with no server and no browser
- the runtime lifecycle adds a call that starts the server, not a rewrite of this adapter
- two Pages declaring one route fail loudly rather than one disappearing silently
- registration is process-global, so one process serves one App's Pages
