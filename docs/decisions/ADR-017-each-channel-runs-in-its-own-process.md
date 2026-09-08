# ADR-017: Each channel of an installed App runs in its own process

Status: Accepted

## Context

Both adapters of one running App are built from the same AppRuntime, and runtime startup starts
the adapters that live inside the app process. Over stdio, though, the agent platform spawns the
MCP server process, and that process builds an AppRuntime of its own. An installed App therefore
runs as more than one process, and the earlier proposal recorded here read that as an open
question to be closed by merging the processes.

It is not open. The MCP specification decides it for stdio: "The client launches the MCP server
as a subprocess", and "Clients **SHOULD** support stdio whenever possible"
(<https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>). Only the
Streamable HTTP transport describes a server that "operates as an independent process that can
handle multiple client connections", and reaching it would mean asking every agent platform to
speak the transport the specification tells clients to avoid.

The Web channel is a single process for its own reasons. NiceGUI "operates on a single uvicorn
worker, leveraging full async support to eliminate the need for multi-process synchronization",
and runs "as a single Python process, meaning module-level variables are shared across all users"
(<https://github.com/zauberzeug/nicegui/blob/main/README.md>).

What the earlier proposal correctly identified was the cost of two processes: state held only in
memory divides with the process, taking caches, idempotency keys, a SQLite file that admits one
writer, and schedulers that then run every job twice. The industry answer to that cost is not to
merge processes. Twelve-factor states that "twelve-factor processes are stateless and
share-nothing", that any data which must persist "must be stored in a stateful backing service",
and that an app "must not assume cached data will be accessible in future requests, since
multiple processes likely exist" (<https://12factor.net/processes>).

Control remains. The Hub starts, stops and reports installed Apps, and a process the agent
platform spawned is not one the Hub started. Merging the processes would make one report cover
everything, at the price of an Agent channel that cannot exist unless the Hub is running.

## Decision

Each channel of an installed App runs in its own operating-system process, and neither channel
depends on the other.

The Hub owns the package lifecycle — install, remove, update — and the Web channel runtime. Its
start, stop and status describe that runtime, which is how `docs/roadmap.md` M10 is to be read.

The Agent channel process is launched by the MCP client, as the specification requires. What the
framework supplies to an agent platform is the command to run, which is package metadata, as
ADR-010 already decided.

An App declaring no Pages has no Web channel and therefore no runtime for the Hub to start. It is
installable, and it is complete for an agent.

Because one installed App may run as several runtimes, an app-scoped resource must be
share-nothing. `docs/architecture/app-model.md` carries what that admits and what it excludes.

## Consequences

- the Agent channel is available whether or not the Hub runs, and an agent may obtain an App on
  demand
- Hub status and stop describe the Web channel; a process the agent platform spawned ends when
  that client ends it
- an App that needs coordination across its runtimes reaches a backing service for it, and the
  framework provides none
- the handoff between the two channels needs a broker: a `ui.refreshable` in global scope updates
  the tabs of one process only, so a Tool invocation cannot refresh an open Page directly
- the Hub UI must express an App with no Web channel, which its current mockup cannot: the
  lifecycle track ends at Installed and reads as "not started yet". M11 owns the affordance
- MCP over HTTP is not required, so the Origin validation, loopback binding and endpoint
  authentication that transport would have demanded are not incurred
- whether capabilities are declared and resolved across Apps is a separate decision, belonging
  to the packaging and Hub milestones
