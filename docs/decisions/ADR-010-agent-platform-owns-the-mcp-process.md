# ADR-010: The agent platform owns the MCP server process

Status: Accepted

## Context

Over stdio the agent platform spawns the MCP server process and speaks to it over that
process's standard streams. An AppRuntime cannot start the process that starts it.

## Decision

Building an MCP server is separated from running one. build_mcp_server returns the SDK Server
object and never runs it.

The stdio command the platform executes is package metadata, so the executable entrypoint
belongs to the package layer.

## Consequences

- a Server object is exercised without a transport
- one Server object serves a stdio entrypoint and an in-process HTTP server alike
- runtime startup covers only adapters living inside the app process
