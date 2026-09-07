# ADR-017: One process serves both channels of an installed App

Status: Proposed

## Context

`docs/architecture/app-model.md` requires that the Web and MCP adapters of one running App
receive the same AppRuntime instance, and ADR-015 makes that a type-level guarantee.
`docs/architecture/lifecycle.md`'s startup step 4 has AppRuntime "initialize/start channel
adapters" — both of them, as part of one runtime's startup.

ADR-010 carved stdio out of that. Over stdio the agent platform spawns the server process,
so an AppRuntime cannot start it, and the executable entrypoint became package metadata.
That was the right call for transport ownership, but it leaves a question no document
answers: when an App is installed and running, do its two channels share one operating-system
process?

Read literally, ADR-010 says they do not. The agent platform spawns its own process, which
builds its own AppRuntime and its own application-scoped resource. `tests/test_dual_channel.py`
proves the two channels share one AppRuntime in-process, which is an architectural
requirement about composition, not a claim about deployment.

### What two processes actually cost

Business state is not the problem. A real App's `create_dependencies` returns a repository or
connection pool over an external store, and two processes over one database share state.

What breaks is in-process state and, more seriously, control:

- The Hub loses the Agent channel. M10 requires that installed Apps "can be started,
  stopped, and queried for status". A process the agent platform spawned is not the process
  the Hub started: the Hub reports STOPPED while that copy serves Tool calls, and `stop`
  does not reach it. The control plane stops controlling.
- Anything that only exists in memory is duplicated or split: caches, rate-limit counters,
  idempotency keys (M20), in-flight job registries, and background schedulers — two
  schedulers run the same job twice.
- Single-writer resources contend: a SQLite file, a local file store, an embedded index.
  These are what a small App reaches for first.
- Connection budget doubles per App, which is an operational failure mode at enterprise
  scale.
- Observability and audit (M15) split into two streams, and invocation ids correlate only
  within one of them. Permission and actor state (M14) is duplicated.

### What one process makes possible

`docs/architecture.md`'s product intent is one domain behind two first-class channels. The
interaction that makes that intent worth having is a handoff between them, and both
directions already have a documented mechanism that requires one process.

Agent to human. A module-scope `@ui.refreshable` collects a target for every client that
rendered it, and `refresh()` iterates all of them, so a Tool invocation can update the page
a human already has open. This is how NiceGUI's own documented multi-user example works.

Human to agent. MCP defines URL-mode elicitation: a server hands the client a URL for the
user to visit, "the actual interaction happens out-of-band", and when it finishes the server
sends an `ElicitCompleteNotification`. The SDK carries `ElicitRequestURLParams`,
`UrlElicitationCapability` and `ElicitCompleteNotification`. So an agent can be told to
continue in a Page, and be notified when the human is done — provided the Page's completion
reaches the same server that holds the MCP session.

Both mechanisms are the libraries' own. Neither is available across a process boundary
without a broker the framework would have to require of every App.

## Decision

One installed App is one operating-system process, owned by the Hub.

Both channel adapters are started by that AppRuntime's startup, as
`docs/architecture/lifecycle.md` step 4 already describes. The Agent channel is served from
that process as MCP over Streamable HTTP.

Where an agent platform supports only stdio, the command the framework supplies is a proxy
that forwards to the running App's endpoint. It holds no AppRuntime and no business logic.

## Consequences

- Hub lifecycle becomes truthful: `start`, `stop` and `status` cover both channels, because
  there is one runtime to start, stop and observe
- application-scoped state means what the invariants say it means, rather than reducing to
  connection pooling over an external store
- the cross-channel handoff is available to an App without requiring a message broker
- one connection budget, one audit stream and one set of invocation ids per App
- ADR-003, ADR-010 and ADR-015 are unaffected. Building an MCP server is still not running
  one, `build_mcp_server()` still constructs no transport, and both adapters are still built
  from one AppRuntime. What changes is who owns the transport
- M17 is unaffected. Its isolation is between Apps, and one process per App is that
- the Hub must be running for the Agent channel to exist. An agent can no longer obtain an
  App on demand by spawning it, which is a heavier operational model for a single-user
  desktop install
- HTTP has a wider surface than stdio. The MCP specification requires `Origin` validation,
  recommends binding to localhost when local, and recommends authentication; none of that is
  needed for a spawned stdio process
- the stdio proxy is code the framework must supply and support
- the cross-channel mechanisms above are enabled, not implemented. URL-mode elicitation also
  depends on the agent client declaring `UrlElicitationCapability`

## Open questions

- how the Agent channel endpoint is authenticated
- whether the Hub or the App owns the listening port, and how it is discovered
- whether the stdio proxy ships with the framework or with each package

## Sources

- <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>
- <https://nicegui.io/documentation/user>
