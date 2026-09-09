# ADR-005: Tool handlers are async-first

Status: Accepted

## Context

A Tool handler is reached from both channels, and both reach it from inside a coroutine. The MCP
adapter's call-tool handler is one, and a NiceGUI page builder is awaited when a visitor arrives.

A synchronous canonical contract would therefore make the framework offload every invocation to a
thread on both channels, to serve handlers that are almost always awaiting a database or an HTTP
client themselves. Supporting both shapes instead would put two invocation paths in ToolRuntime,
which is the single canonical path ADR-001 depends on.

Concurrency is the second question the contract has to answer, because an async contract permits
overlap that a synchronous one hides.

## Decision

The canonical ToolHandler contract is asynchronous.

ToolRuntime permits concurrent invocations by default and does not add a global execution lock.

## Consequences

- MCP/NiceGUI integrations fit naturally
- cancellation/timeout can be added later
- consistency remains the responsibility of domain services/repositories/storage
