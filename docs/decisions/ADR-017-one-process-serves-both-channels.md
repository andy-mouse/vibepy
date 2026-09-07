# ADR-017: One process serves both channels of an installed App

Status: Proposed

## Context

`docs/architecture/app-model.md` requires that both adapters of one running App receive the
same AppRuntime, and `docs/architecture/lifecycle.md`'s startup step 4 has AppRuntime start
the channel adapters. Under ADR-010 the agent platform owns the stdio server process, so it
spawns a process that builds its own AppRuntime. Whether the two channels of an installed
App share one operating-system process is undecided, and read literally that answer is no.

Two processes cost little on business state, since an App's dependencies sit over an external
store either way. They cost control. The Hub is the control plane for installed Apps, and
a process the agent platform spawned is not the one the Hub started, so its status lies and
its `stop` does not reach it. In-memory state splits with it: caches, idempotency keys,
single-writer stores such as SQLite, and schedulers that then run every job twice.

One process is also the precondition for the handoff `docs/architecture.md`'s product intent
is built around, and both directions already have a mechanism that needs it. A module-scope
`@ui.refreshable` collects a target per client and `refresh()` iterates all of them, so a
Tool invocation can update a page a human has open
([NiceGUI - User fixture](https://nicegui.io/documentation/user)). MCP URL-mode elicitation
hands the client a URL, lets the interaction happen out of band, and reports completion with
`ElicitCompleteNotification`, so an agent can hand work to a Page and be told when the human
finished. Neither crosses a process boundary without a broker the framework would have to
require of every App.

Local hosting is the favourable case for this. The browser and the App share a host, so a
Page URL is a localhost URL, which the specification anticipates by recommending that a
local server bind only to 127.0.0.1
([MCP - Transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)),
and `ElicitRequestURLParams` constrains the URL not at all, so plain HTTP is valid. The
capability also degrades in steps: updating an open page and handing over a URL need nothing
from the agent client, and only the automatic completion callback needs URL-mode
elicitation, which the SDK dates to protocol version 2025-11-25 and which polling a status
Tool substitutes for.

## Decision

One installed App is one operating-system process, owned by the Hub.

That AppRuntime's startup starts both channel adapters, as lifecycle step 4 already
describes, and the Agent channel is served from that process as MCP over Streamable HTTP.

The command the framework supplies to an agent platform is a stdio proxy that forwards to
the running App's endpoint, holding no AppRuntime and no business logic. A platform that
speaks HTTP MCP may address the endpoint directly instead.

## Consequences

- Hub lifecycle becomes truthful: one runtime to start, stop and observe, covering both
  channels
- application-scoped state means what the invariants say, rather than reducing to connection
  pooling over an external store
- the cross-channel handoff is available to an App without a message broker, and one
  connection budget, audit stream and set of invocation ids serves each App
- ADR-003, ADR-010 and ADR-015 are unaffected: building an MCP server is still not running
  one, and both adapters are still built from one AppRuntime. Only transport ownership moves
- isolation between installed Apps is unaffected, and one process per App is a form of it
- the Hub must be running for the Agent channel to exist, so an agent can no longer obtain
  an App on demand by spawning it
- HTTP has a wider surface than a spawned stdio process: the specification requires `Origin`
  validation and recommends localhost binding and authentication
- the stdio proxy is code the framework must supply, and under local hosting it is the path
  most agent platforms take rather than an exception
- the cross-channel mechanisms are enabled, not implemented, and whether a client opens a
  plain-HTTP localhost URL is that client's policy
- three questions stay open for whatever accepts this: how the endpoint is authenticated,
  whether the Hub or the App owns and publishes the port, and whether the stdio proxy ships
  with the framework or with each package
