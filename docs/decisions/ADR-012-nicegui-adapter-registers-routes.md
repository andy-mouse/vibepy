# ADR-012: The NiceGUI adapter registers routes and does not run the server

Status: Accepted

## Context

`docs/architecture/lifecycle.md`'s startup step 4 initializes and starts channel adapters,
and ADR-010 confirms that this step covers the NiceGUI Web server, which unlike a stdio
MCP server does live inside the app process. So the Web channel could legitimately own its
own startup.

It has nothing to start it from. AppRuntime is M5A and the lifecycle is M6, so an adapter
that ran a server today would define startup where no lifecycle exists to own it, and M6
would have to take it back.

NiceGUI also registers routes on a process-global app object. `ui.page.__call__` begins by
removing any route already at that path, so a second registration of one path silently
replaces the first and no collision is ever reported.

## Decision

Registering routes is separated from running a server. `register_pages()` projects a
PageRegistry onto NiceGUI routes and returns; the framework starts no Web server and holds
no server object.

Route format and uniqueness are validated by the adapter before any route is registered.
The framework does not rely on NiceGUI to report a route collision, because NiceGUI does
not report one.

## Consequences

- the Web channel is testable in-process through `nicegui.testing.user_simulation`, with no
  server and no browser
- what M6 adds is a call to `ui.run()` at startup step 4, not a rewrite of this adapter
- two Pages declaring one route fail loudly at registration rather than one silently
  disappearing
- registration is process-global, so one process serves one App's Pages. Isolating several
  installed Apps is M17 and this decision does not prejudge it
