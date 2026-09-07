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
does not reach it. In-memory state divides with the process: caches, rate-limit counters,
idempotency keys, in-flight job registries, single-writer stores such as a SQLite file or an
embedded index, and schedulers that then run every job twice. Connection budget, audit stream
and actor state each double, and invocation identifiers correlate only within one half.

One process is also what the cross-channel handoff needs, and both of its directions are
mechanisms the channel technologies already provide. A refreshable declared once refreshes
every client that rendered it, so a Tool invocation reaches a page a human already has open
([NiceGUI - Refreshable UI functions](https://nicegui.io/documentation/refreshable),
[NiceGUI - User fixture](https://nicegui.io/documentation/user)). URL-mode elicitation hands
the agent client a URL, the interaction then "occurs out of band", and the server MAY send a
completion notification when it finishes
([MCP - Elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation)),
so an agent can hand work to a Page and learn when the human is done. Both mechanisms end at
a process boundary: across one, an App would need a broker the framework does not provide.

Local hosting is the favourable case for that handoff. Pages are served on the machine the
human uses, so a Page URL is a localhost URL, which is also what the specification
recommends a local server bind to. Nothing in a URL-mode elicitation request constrains the
URL, so a plain unencrypted localhost address is valid at the protocol level, with no
certificate or tunnel involved. Two limits are worth recording rather than assuming away.
URL mode is newer than the protocol version this repository otherwise cites, so client
support will be narrow for some time; and whether a given client opens such a URL is that
client's own policy, which the specification leaves to it. Neither limit blocks a decision,
because the capability degrades in steps: a Tool invocation updating an open page needs
nothing from the agent client, handing the human a Page needs only a URL in a Tool's result,
and only the completion callback needs URL mode, for which an agent polling a status Tool
substitutes. Local hosting also changes how a stdio entrypoint reads. Every agent platform
speaks stdio, so a proxy forwarding to an App on localhost is the likely primary path rather
than a fallback for platforms lacking HTTP.

Two arrangements answer the question. Each installed App can run as one process the Hub owns,
with the Agent channel served from it over HTTP. Or the agent platform can keep spawning its
own process, in which case every App must externalize all state and reach a broker for the
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
- ADR-003, ADR-010 and ADR-015 are unaffected. Building an MCP server is still not running
  one, the framework still constructs no transport, and both adapters are still built from
  one AppRuntime. What changes is who owns the transport
- isolating installed Apps from one another is unaffected, because one process per App is
  that isolation
- the Hub must be running for the Agent channel to exist, so an agent can no longer obtain an
  App on demand by spawning one, which is a heavier model for a single-user desktop install
- HTTP requires origin validation and recommends loopback binding and authentication, none of
  which a spawned stdio process needed
- the stdio proxy is code the framework must supply and support, and under local hosting it is
  the path most agent platforms take rather than an exception
- the handoff is enabled rather than implemented, and its completion callback additionally
  needs an agent client declaring the URL elicitation capability; without it the handoff still
  works, only without the automatic callback
- authentication, port ownership and the proxy's home stay open for whatever accepts this
