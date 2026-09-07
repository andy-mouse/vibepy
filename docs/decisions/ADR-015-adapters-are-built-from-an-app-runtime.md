# ADR-015: Channel adapters are built from an AppRuntime

Status: Accepted

## Context

Both adapters of one running App must receive the same AppRuntime instance.

Adapter signatures that take a registry and a runtime separately cannot express that. A
registry and a runtime that do not belong together type-check, and the resulting App has two
backends.

## Decision

Each adapter is constructed from one AppRuntime.

The MCP server's name and version come from the AppDefinition, with the app id as the name
because it is the App's stable identifier.

## Consequences

- one App, one AppRuntime, two channels is a type-level guarantee rather than a convention a
  caller must follow
- the adapters read the AppRuntime's read-only properties and nothing else; the
  application-scoped resource is not among them
- an App reaches a channel by being passed to that channel's adapter, so an App with no Agent
  channel simply never has a server built for it
