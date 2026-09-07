# ADR-017: One process serves both channels of an installed App

Status: Proposed

## Context

Both adapters of one running App receive the same AppRuntime, and runtime startup starts
them. Yet the agent platform owns the stdio server process, so it spawns a process that
builds an AppRuntime of its own. Whether an installed App's two channels share one
operating-system process is undecided, and read literally that answer is no.

Two processes cost little on business state, which sits over an external store either way.
They cost control: the Hub is the control plane for installed Apps, and a process the agent
platform spawned is not the one the Hub started, so its status lies and its stop does not
reach it. In-memory state splits with it — caches, idempotency keys, single-writer stores,
and schedulers that then run every job twice.

One process is also what the cross-channel handoff needs, and both directions of it are
mechanisms the channel technologies already provide. A refreshable declared once refreshes
every client that rendered it, so a Tool invocation can update a page a human has open
([NiceGUI - User fixture](https://nicegui.io/documentation/user)). URL-mode elicitation hands
the agent client a URL, lets the interaction happen out of band, and reports completion, so an
agent can hand work to a Page and be told when the human finished. Neither crosses a process
boundary without a broker the framework would have to require of every App. Local hosting
makes it the easy case, since a Page URL is a localhost URL and the specification recommends
that a local server bind only to the loopback address
([MCP - Transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)).

## Decision

One installed App is one operating-system process, owned by the Hub. Its startup starts both
channel adapters, and the Agent channel is served from that process over HTTP.

The command the framework supplies to an agent platform is a stdio proxy that forwards to the
running App, holding no AppRuntime and no business logic. A platform that speaks HTTP
addresses the App directly instead.

## Consequences

- the control plane becomes truthful: one runtime to start, stop and observe, with one
  connection budget, audit stream and set of invocation identifiers per App
- application-scoped state means what the invariants say, and the handoff needs no broker
- transport ownership moves; building a server is still not running one, and both adapters are
  still built from one AppRuntime
- the Hub must be running for the Agent channel to exist, so an agent can no longer obtain an
  App on demand by spawning one
- HTTP has a wider surface than a spawned process, requiring origin validation and
  recommending loopback binding and authentication, so the stdio proxy is the path most agent
  platforms take rather than an exception
- the handoff is enabled, not implemented; its completion callback additionally needs a client
  that supports URL-mode elicitation, which polling substitutes for
- three questions stay open for whatever accepts this: how the endpoint is authenticated,
  which side owns and publishes the port, and where the stdio proxy ships
