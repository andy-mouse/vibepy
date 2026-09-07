# ADR-017: One process serves both channels of an installed App

Status: Proposed

## Context

Both adapters of one running App receive the same AppRuntime, and runtime startup starts
them. Yet the agent platform owns the stdio server process, and the process it spawns builds
an AppRuntime of its own. Whether an installed App's two channels share one operating-system
process is undecided.

Business state survives either arrangement, since an App's dependencies sit over an external
store. Control does not. The Hub starts, stops and reports installed Apps, and a process the
agent platform spawned is not the one the Hub started, so its status is wrong and its stop
does not reach it. In-memory state divides with the process: caches, idempotency keys,
single-writer stores, and schedulers that then run every job twice.

One process is also what the cross-channel handoff needs, and both of its directions are
mechanisms the channel technologies already provide. A refreshable declared once refreshes
every client that rendered it, so a Tool invocation reaches a page a human already has open
([NiceGUI - User fixture](https://nicegui.io/documentation/user)). URL-mode elicitation hands
the agent client a URL, lets the interaction happen out of band, and reports its completion,
so an agent can hand work to a Page and learn when the human finished.

Two arrangements answer this. Each installed App can run as one process the Hub owns, with
the Agent channel served from it over HTTP. Or the agent platform can keep spawning its own
process, in which case every App must externalize all state and reach a broker for the
handoff, and the Hub can observe only the channel it started.

## Decision

One installed App is one operating-system process, owned by the Hub. Its startup starts both
channel adapters, and the Agent channel is served from that process over HTTP.

The command the framework supplies to an agent platform is a stdio proxy that forwards to the
running App, holding no AppRuntime and no business logic. A platform that speaks HTTP
addresses the App directly instead.

The second arrangement is rejected because it makes a broker and fully external state a
condition of writing any App, and leaves the control plane unable to report or stop half of
what it installed.

## Consequences

- the control plane becomes truthful: one runtime to start, stop and observe, and one
  connection budget, audit stream and set of invocation identifiers per App
- application-scoped state means what the invariants say, rather than reducing to connection
  pooling over an external store
- the handoff becomes available to an App without a broker
- the Hub must be running for the Agent channel to exist, so an agent can no longer obtain an
  App on demand by spawning one
- HTTP requires origin validation and recommends loopback binding and authentication, none of
  which a spawned stdio process needed
- the stdio proxy is code the framework must supply and support
- the handoff is enabled rather than implemented, and its completion callback additionally
  needs an agent client that supports URL-mode elicitation
- authentication, port ownership and the proxy's home stay open for whatever accepts this
