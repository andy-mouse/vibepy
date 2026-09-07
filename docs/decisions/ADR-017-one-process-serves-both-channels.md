# ADR-017: One process serves both channels of an installed App

Status: Proposed

## Context

Both adapters of one running App are built from the same AppRuntime, and runtime startup
starts the adapters that live inside the app process. Over stdio, though, the agent platform
spawns the MCP server process, and that process builds an AppRuntime of its own. An installed
App may therefore be running as two processes, and nothing decides whether it should.

Business state is indifferent to the answer, because an App's dependencies sit over an
external store and two processes read the same rows. Control is not. The Hub starts, stops
and reports installed Apps, and a process the agent platform spawned is not the one the Hub
started, so its status is wrong and a stop does not reach it. State held only in memory
divides with the process: caches, idempotency keys, a SQLite file that admits one writer, and
schedulers that then run every job twice.

The handoff between the two channels also needs one process, and both of its directions are
mechanisms the channel technologies already provide. A refreshable defined in global scope
shares one state across the clients that rendered it, so refreshing it updates every open tab
simultaneously ([NiceGUI - ui.refreshable](https://nicegui.io/documentation/refreshable)).
MCP's URL elicitation mode covers "out-of-band interaction via URL navigation", where the
interaction "occurs out of band and the client is not aware of the outcome until and unless
the server sends a notification indicating completion"
([MCP - Elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation)).
Across a process boundary each direction would instead need a broker.

Local hosting favours serving the Agent channel over HTTP: a Page URL is already a localhost
address, and "when running locally, servers SHOULD bind only to localhost (127.0.0.1)"
([MCP - Transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)).
It pulls the other way too. URL mode belongs to a protocol version later than the one this
repository otherwise cites, and the specification hands navigation to the client, so whether
a client opens such an address is that client's policy. Every agent platform speaks stdio and
few speak MCP over HTTP.

The alternative is to leave the agent platform spawning its own process. Every App then has
to externalize all of its state and reach a broker for the handoff, and the Hub can report
and stop only the channel it started.

## Decision

One installed App is one operating-system process, owned by the Hub. Its startup starts both
channel adapters, and the Agent channel is served from that process over HTTP. The command
the framework supplies to an agent platform is a stdio proxy that forwards to the running
App, holding no AppRuntime and no business logic.

## Consequences

- start, stop and status describe an App as a whole, and one connection budget, audit stream
  and set of invocation identifiers belong to it
- application-scoped state means what the invariants say it means, rather than reducing to
  connection pooling over an external store
- the handoff becomes available to an App without a broker, enabled rather than implemented;
  its completion callback additionally needs a client that declares the URL elicitation
  capability, and an agent polling a status Tool substitutes where that is missing
- the Hub must be running for the Agent channel to exist, so an agent can no longer obtain an
  App on demand by spawning one
- serving MCP over HTTP widens the exposed surface, and the specification requires Origin
  validation and recommends loopback binding and authentication
- the stdio proxy is code the framework supplies and supports, and it is the path most agent
  platforms take
- authentication of the endpoint, ownership and discovery of the listening port, and where
  the proxy ships are left undecided
