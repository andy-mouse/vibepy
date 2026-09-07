# ADR-017: One process serves both channels of an installed App

Status: Proposed

## Context

Both adapters of one running App receive the same AppRuntime, and runtime startup starts them,
yet the agent platform owns the stdio server process and spawns one that builds an AppRuntime
of its own. Whether an installed App's two channels share one operating-system process is
undecided.

Business state survives either arrangement, since an App's dependencies sit over an external
store. Control does not: the Hub starts, stops and reports installed Apps, and a process the
agent platform spawned is not the one it started. In-memory state divides with the process —
caches, idempotency keys, single-writer stores, and schedulers that then run every job twice.

One process is also what the cross-channel handoff needs, and both of its directions are
mechanisms the channel technologies already provide. A refreshable declared once refreshes
every client that rendered it, so a Tool invocation reaches a page a human has open
([NiceGUI - User fixture](https://nicegui.io/documentation/user)). URL-mode elicitation hands
the agent client a URL, lets the interaction happen out of band, and reports its completion.
Neither crosses a process boundary without a broker every App would then have to require.

## Decision

One installed App is one operating-system process, owned by the Hub. Its startup starts both
channel adapters, and the Agent channel is served from that process over HTTP.

The command the framework supplies to an agent platform is a stdio proxy that forwards to the
running App, holding no AppRuntime and no business logic.

## Consequences

- the control plane becomes truthful, with one runtime to start, stop and observe
- one connection budget, audit stream and set of invocation identifiers serves each App
- application-scoped state means what the invariants say, and the handoff needs no broker
- the Hub must run for the Agent channel to exist, so an agent cannot obtain an App on demand
- HTTP requires origin validation and recommends loopback binding and authentication, which a
  spawned process needed neither of
- the handoff is enabled rather than implemented, and its completion callback needs a client
  supporting URL-mode elicitation
- authentication, port ownership and the proxy's home stay open for whatever accepts this
