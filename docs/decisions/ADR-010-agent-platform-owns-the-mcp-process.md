# ADR-010: The agent platform owns the MCP server process

Status: Accepted

## Context

Over stdio the agent platform spawns the MCP server process and speaks to it over that
process's standard streams, so the client and the transport are owned outside the framework.

Runtime startup initializes and starts channel adapters. Read as covering stdio MCP that is a
contradiction: an AppRuntime cannot start the process that starts it.

## Decision

Building an MCP server is separated from running one. build_mcp_server returns the SDK Server
object and never runs it; the framework builds no transport.

Startup covers only adapters that live inside the app process.

What the framework supplies for stdio is a command the platform executes, which is package
metadata rather than runtime behaviour, so the executable entrypoint belongs to the package
layer.

## Consequences

- a Server object is constructed from a registry and a runtime and is exercised without a
  transport
- one Server object serves a stdio entrypoint and an in-process HTTP server alike, and
  neither reuse changes the adapter
