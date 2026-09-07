# ADR-009: The MCP adapter is built on the low-level SDK server

Status: Accepted

## Context

The MCP Python SDK offers a decorator-driven MCPServer and a low-level Server whose handlers
return protocol result objects
([MCP Python SDK - Low-level server](https://py.sdk.modelcontextprotocol.io/v2/advanced/low-level-server)).
MCP SDK types cannot define the framework Tool model.

## Decision

The MCP adapter is built on the low-level Server.

MCPServer is rejected because it derives a Tool's input schema and its result conversion from
a Python function signature.

## Consequences

- an MCP schema is always the declaration's own
- the adapter maps results and framework errors onto the protocol by hand
- the SDK's handler signatures rather than its decorators are the integration surface
