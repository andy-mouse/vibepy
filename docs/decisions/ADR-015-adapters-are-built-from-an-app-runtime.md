# ADR-015: Channel adapters are built from an AppRuntime

Status: Superseded by ADR-021

## Context

Both adapters of one running App must receive the same AppRuntime instance.

Adapter signatures that take a registry and a runtime separately cannot express that
requirement. A registry and a runtime that do not belong together type-check, and the
resulting App has two backends. ADR-013 makes both parameters generic in `DepsT`, so
both signatures change regardless.

## Decision

Each adapter is constructed from one AppRuntime.

The MCP server takes its name and version from the AppDefinition, with `app_id` as the name
because it is the App's stable identifier.

## Consequences

- one App, one AppRuntime, two channels is a type-level guarantee rather than a convention a
  caller must follow
- the adapters read `tool_registry`, `tool_runtime`, `page_registry`, `page_runtime` and
  `definition` from the AppRuntime; nothing else is exposed, and the application-scoped
  resource is not
- an App reaches a channel by being passed to that channel's adapter, so an App with no Agent
  channel simply never has a server built for it
