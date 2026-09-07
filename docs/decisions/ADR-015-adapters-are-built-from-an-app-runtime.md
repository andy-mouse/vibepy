# ADR-015: Channel adapters are built from an AppRuntime

Status: Accepted

## Context

Both adapters of one running App must receive the same AppRuntime. Signatures taking a
registry and a runtime separately cannot express that: pieces that do not belong together
type-check, and the resulting App has two backends.

## Decision

Each adapter is constructed from one AppRuntime.

The MCP server takes its name and version from the AppDefinition, with the app id as the name
because it is the App's stable identifier.

## Consequences

- one App, one AppRuntime, two channels is a type-level guarantee rather than a convention
- the adapters read the AppRuntime's read-only properties and nothing else
- the application-scoped resource stays unexposed
- an App with no Agent channel never has a server built for it
