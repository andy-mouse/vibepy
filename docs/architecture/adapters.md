# Channel Adapter Architecture

## Principle

Channel adapters translate a channel protocol/runtime into framework semantics. They do not own business logic.

## MCP Adapter

MCP is the Agent channel technology.

Responsibilities:

1. project framework ToolDefinitions into MCP Tool definitions
2. register/discover Tools through the MCP SDK
3. translate MCP arguments into ToolRuntime invocation
4. translate validated Tool results/errors into MCP-compatible responses

The direction is always:

```text
Framework ToolDefinition -> MCP projection
```

Never make MCP decorators or MCP SDK types the source of truth for framework Tools.

MCP-specific types must not leak into the core Tool package.

`build_mcp_server(app)` takes the AppRuntime, reading the registry it enumerates and the
ToolRuntime it invokes through from one object, and taking the server's name and version
from the AppDefinition. See
`docs/decisions/ADR-015-adapters-are-built-from-an-app-runtime.md`.

The adapter builds an SDK server object; it does not run one. Over stdio the agent platform
owns the server process, so the executable entrypoint is package metadata rather than part
of the runtime lifecycle. See
`docs/decisions/ADR-010-agent-platform-owns-the-mcp-process.md`.

## NiceGUI Adapter

NiceGUI is the Web channel technology.

Responsibilities:

1. project/register PageDefinitions as Web routes
2. construct PageContext
3. execute PageHandlers in the NiceGUI lifecycle
4. connect Page interaction to ToolRuntime through ToolInvoker, which ToolRuntime satisfies

`register_pages(app)` takes the AppRuntime and projects every PageDefinition it declares
onto a NiceGUI route whose builder awaits `PageRuntime.render(name)`. A Page is addressed by name, so a route
change never reaches PageRuntime, and the adapter constructs no PageContext: PageRuntime
owns that.

Route format and route uniqueness are validated here, which is where
`docs/architecture/page-model.md` places them. Every declaration is checked before any
route is registered, so a rejected registry leaves no half-registered app behind.

Errors are not translated. A Tool error or a handler exception propagates into NiceGUI,
which renders it. The MCP adapter wraps failures in a result because the MCP protocol
demands an answer to every call; the Web channel makes no such demand.

The adapter registers routes and starts no server. See
`docs/decisions/ADR-012-nicegui-adapter-registers-routes.md`.

The app owns the actual Page UI implementation. The framework owns the integration/runtime mechanism.

NiceGUI-specific types must not leak into the core Page model unless required at the app UI implementation boundary.

## Future adapters

The architecture should permit additional channels without redefining backend operations:

- REST
- CLI
- webhook
- scheduler/automation

These remain projections or entrypoints over the same ToolRuntime.
