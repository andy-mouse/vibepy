# ADR-009: The MCP adapter is built on the low-level SDK server

Status: Accepted

## Context

The Agent channel is exposed with the official MCP Python SDK, which offers two surfaces
([MCP Python SDK - Low-level server](https://py.sdk.modelcontextprotocol.io/v2/advanced/low-level-server)):

- a high-level `MCPServer` where `@mcp.tool()` turns a Python function into an MCP Tool
- a low-level `mcp.server.Server` whose request handlers return protocol result objects

`docs/architecture/adapters.md` fixes the projection direction as
`Framework ToolDefinition -> MCP projection` and forbids making MCP decorators or MCP SDK
types the source of truth for framework Tools.

## Decision

The adapter is built on the low-level `mcp.server.Server`, with `on_list_tools` and
`on_call_tool` supplied as constructor arguments.

`MCPServer` with `@mcp.tool()` is rejected. It derives a Tool's input schema and its result
conversion from a Python function signature, which would make the SDK the source of truth
for what a Tool is. The low-level server returns the schemas it is given and generates no
structured content of its own, which is what a projection requires.

## Consequences

- discovery is an enumeration of `ToolRegistry.definitions()` projected through
  `to_mcp_tool`, so an MCP schema is always the declaration's own
  `model_json_schema()`
- the adapter constructs `CallToolResult` and maps framework errors onto MCP by hand; this
  cost is accepted in exchange for the projection direction
- the SDK's handler signatures, not decorators, are the integration surface, so an SDK
  change is confined to the MCP adapter
