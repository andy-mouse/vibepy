# ADR-001: Tools are channel-neutral canonical backend operations

Status: Accepted

## Context

The same application domain must be usable by humans through Web UI and by agents through MCP.

## Decision

Framework Tools are application-level backend operations independent of transport/channel.

MCP Tools are projections of framework Tools. Pages invoke the same framework Tools through ToolRuntime.

## Consequences

- business operations are implemented once
- MCP SDK types cannot define the framework Tool model
- Page business state changes must go through Tools
- future channels can reuse the same Tool surface
