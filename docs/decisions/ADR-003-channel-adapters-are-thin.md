# ADR-003: NiceGUI and MCP are thin channel adapters

Status: Accepted

## Decision

NiceGUI and MCP SDK integrations translate channel-specific interaction into framework abstractions.

They do not own domain business logic.

## Consequences

- MCP adapter projects ToolDefinition and forwards calls to ToolRuntime
- NiceGUI adapter projects PageDefinition and constructs PageContext
- channel-specific SDK types stay out of core contracts
