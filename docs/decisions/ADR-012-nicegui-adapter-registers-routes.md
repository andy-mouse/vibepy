# ADR-012: The NiceGUI adapter registers routes and does not run the server

Status: Accepted

## Context

The Web server lives inside the app process, so the adapter could own its own startup, but no
runtime lifecycle exists to own it. NiceGUI removes any route already registered at a path, so
a duplicate replaces the first and no collision is reported.

## Decision

Registering routes is separated from running a server. register_pages projects a PageRegistry
onto NiceGUI routes and returns; the framework starts no Web server.

The adapter validates route format and uniqueness before registering any route.

## Consequences

- the Web channel is exercised with no server and no browser
- the runtime lifecycle adds the call that starts the Web server, not a rewrite of this adapter
- two Pages declaring one route fail loudly rather than one disappearing
- registration is process-global, so one process serves one App's Pages
