# ADR-010: The agent platform owns the MCP server process

Status: Accepted

## Context

Over stdio the agent platform spawns the MCP server process and speaks to it over that
process's standard streams, so the client and the transport are owned outside the framework.

Runtime startup initializes and starts channel adapters. Read as covering stdio MCP that is
a contradiction: an AppRuntime cannot start the process that starts it.

## Decision

Building an MCP server is separated from running one. The framework returns the SDK server
object and builds no transport.

Startup covers only adapters that live inside the app process.

What the framework supplies for stdio is a command the platform executes, which is package
metadata rather than runtime behaviour, so the executable entrypoint belongs to the package
layer.

## Consequences

- a server object is testable in-process, without a transport
- one object serves both a stdio entrypoint and an in-process HTTP server, and neither reuse
  changes the adapter
