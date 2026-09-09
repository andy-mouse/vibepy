# ADR-005: Tool handlers are async-first

Status: Accepted

## Decision

The canonical ToolHandler contract is asynchronous.

ToolRuntime permits concurrent invocations by default and does not add a global execution lock.

## Consequences

- MCP/NiceGUI integrations fit naturally
- cancellation/timeout can be added later
- consistency remains the responsibility of domain services/repositories/storage
