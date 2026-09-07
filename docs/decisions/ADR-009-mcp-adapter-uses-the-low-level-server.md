# ADR-009: The MCP adapter is built on the low-level SDK server

Status: Accepted

## Context

The official MCP Python SDK offers two surfaces: a high-level server where a decorator turns
a Python function into an MCP Tool, and a low-level server whose request handlers return
protocol result objects
([MCP Python SDK - Low-level server](https://py.sdk.modelcontextprotocol.io/v2/advanced/low-level-server)).

The architecture fixes the projection direction from framework ToolDefinition to MCP and
forbids MCP decorators or SDK types being the source of truth for what a Tool is.

## Decision

The adapter is built on the low-level server.

The decorator surface is rejected: it derives a Tool's input schema and its result
conversion from a Python function signature, which would put the source of truth in the SDK.
The low-level server returns the schemas it is given and generates no structured content of
its own, which is what a projection requires.

## Consequences

- an MCP schema is always the declaration's own
- the adapter maps results and framework errors onto the protocol by hand, a cost accepted
  in exchange for the projection direction
- the SDK's handler signatures rather than its decorators are the integration surface, so an
  SDK change is confined to the adapter
