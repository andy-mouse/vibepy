# ADR-012: The NiceGUI adapter registers routes and does not run the server

Status: Accepted

Amendment, appended: `register_pages` has always taken an `AppDefinition` and enumerated
`definition.pages`, never a `PageRegistry`. The decision this record states — registering routes
is separated from running a server — is unaffected; only the sentence describing it was wrong on
arrival. `docs/architecture/page-model.md` and `docs/architecture/adapters.md` carry the shape as
it is.

Amendment, appended (ADR-037): route format and uniqueness are validated as the `AppDefinition`
is constructed, not by the adapter. The decision this record states — registering routes is
separated from running a server — stands as recorded.

## Context

The Web server lives inside the app process, unlike a stdio MCP server, so the Web channel
could legitimately own its own startup.

It has nothing to start it from. No runtime lifecycle exists to own startup, so an adapter
that ran a server would define startup itself and the lifecycle would have to take it back.

NiceGUI registers routes on a process-global app object, and `ui.page.__call__` begins by
removing any route already at that path, so a second registration of one path silently replaces the first and no
collision is reported.

## Decision

Registering routes is separated from running a server. register_pages projects a PageRegistry
onto NiceGUI routes and returns; the framework starts no Web server and holds no server
object.

The adapter validates route format and uniqueness before any route is registered, because
NiceGUI reports no collision of its own.

## Consequences

- the Web channel is exercised in-process through `nicegui.testing.user_simulation`, with no
  server and no browser
- the runtime lifecycle adds a call to `ui.run()` at startup, not a rewrite of this adapter
- two Pages declaring one route fail loudly at registration rather than one disappearing
  silently
- registration is process-global, so one process serves one App's Pages
