# ADR-015: Channel adapters are built from an AppRuntime

Status: Accepted

## Context

`docs/architecture/app-model.md` requires that "Web and MCP adapters for one running app
must receive the same AppRuntime instance". Until M5A there was no AppRuntime, so each
adapter took the pieces it needed: `build_mcp_server(name, version, registry, runtime)` and
`register_pages(registry, runtime)`.

Those signatures cannot express the requirement. A registry and a runtime that do not belong
together type-check, and the resulting App has two backends. ADR-013 also makes both
parameters generic in `DepsT`, so both signatures change in this milestone regardless.

## Decision

Each adapter is constructed from one AppRuntime.

```python
def build_mcp_server[DepsT](app: AppRuntime[DepsT]) -> Server[None]: ...
def register_pages[DepsT](app: AppRuntime[DepsT]) -> None: ...
```

The MCP server's name and version come from the AppDefinition, with `app_id` as the name
because it is the App's stable identifier.

## Consequences

- "one App, one AppRuntime, two channels" is a type-level guarantee rather than a
  convention a caller must follow
- the adapters read `tool_registry`, `tool_runtime`, `page_registry`, `page_runtime` and
  `definition` from the AppRuntime; nothing else is exposed, and the application-scoped
  resource is not
- ADR-010 and ADR-012 are unaffected. Building an MCP server is still not running one, and
  registering routes is still not starting a Web server
- an App reaches a channel by being passed to that channel's adapter, so an App with no
  Agent channel simply never has a server built for it
