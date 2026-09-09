# ADR-003: NiceGUI and MCP are thin channel adapters

Status: Deprecated

This record states no decision between alternatives: it has no Context, and what it asserts is
held by ADR-001 and ADR-002 as decisions and by `docs/architecture/adapters.md` as current
truth. It is kept because ADR-020 cites it.

## Decision

NiceGUI and MCP SDK integrations translate channel-specific interaction into framework abstractions.

They do not own domain business logic.

## Consequences

- MCP adapter projects ToolDefinition and forwards calls to ToolRuntime
- NiceGUI adapter projects PageDefinition and constructs PageContext
- channel-specific SDK types stay out of core contracts
