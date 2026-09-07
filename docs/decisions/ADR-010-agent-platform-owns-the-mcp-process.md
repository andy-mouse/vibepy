# ADR-010: The agent platform owns the MCP server process

Status: Accepted

## Context

`docs/architecture.md` describes the Agent channel as
`Agent -> MCP client -> MCP server -> MCP adapter -> ToolRuntime -> Tool`. Over stdio the
agent platform — Claude Desktop, Codex — spawns the server process and speaks to it over
that process's standard streams, so the two leftmost links are owned outside the framework.

`docs/architecture/lifecycle.md`'s startup step 4 initializes and starts channel adapters.
Read as covering stdio MCP it is a contradiction: an AppRuntime cannot start the process
that starts it.

## Decision

Building an MCP server is separated from running one. `build_mcp_server()` returns the SDK
`Server` object and never runs it; the framework builds no transport.

Startup step 4 describes only adapters that live inside the app process, such as the
NiceGUI Web server, or MCP served over HTTP.

What the framework supplies for stdio is a command the platform executes, which is package
metadata rather than runtime behaviour. The executable entrypoint therefore belongs to the
App Package layer.

## Consequences

- an MCP server object is constructed from a `ToolRegistry` and a `ToolRuntime` and is
  testable in-process without a transport
- the same object is what a package entrypoint wraps for stdio, and what a runtime starts
  in-process if MCP is ever served over HTTP; neither reuse changes this adapter
