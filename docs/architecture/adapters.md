# Channel Adapter Architecture

## Principle

Channel adapters translate a channel protocol/runtime into framework semantics. They do not own business logic.

An adapter is built from a declaration and a lifespan, and reads its runtime from the window its
own host opens. Each channel uses the mechanism that host documents, so the two adapters differ;
giving them a common shape would mean inventing one. See
`docs/decisions/ADR-021-the-channel-host-owns-the-runtime-lifecycle.md`.

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

`build_mcp_server(definition, lifespan)` reads the registry it enumerates, and the server's name
and version, from the declaration. The ToolRuntime a call goes through is read from the SDK's
request context, which carries whatever the lifespan yielded, so the adapter holds no running
state of its own.

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

`register_pages(definition, pages)` projects every PageDefinition the declaration carries onto a
NiceGUI route whose builder awaits `PageRuntime.render(name)`. A Page is addressed by name, so a
route change never reaches PageRuntime, and the adapter constructs no PageContext: PageRuntime
owns that.

Registration happens inside the caller's window and each builder closes over the PageRuntime, so
a builder holds its runtime for exactly as long as that window lasts. Nothing reads request
state: NiceGUI documents no lifespan and mounts as a sub-application, and Starlette does not
document lifespan state reaching one, so a closure is used because it is a language guarantee
rather than a library one.

Route format and route uniqueness are validated here, which is where
`docs/architecture/page-model.md` places them. Every declaration is checked before any
route is registered, so a rejected registry leaves no half-registered plugin behind.

Errors are not translated. A Tool error or a handler exception propagates into NiceGUI,
which renders it. The MCP adapter wraps failures in a result because the MCP protocol
demands an answer to every call; the Web channel makes no such demand.
`docs/architecture/errors.md` describes what the MCP adapter sends.

The adapter registers routes and starts no server. See
`docs/decisions/ADR-012-nicegui-adapter-registers-routes.md`.

The plugin owns the actual Page UI implementation. The framework owns the integration/runtime mechanism.

NiceGUI-specific types must not leak into the core Page model unless required at the plugin's UI implementation boundary.

## Future adapters

The architecture should permit additional channels without redefining backend operations:

- REST
- CLI
- webhook
- scheduler/automation

These remain projections or entrypoints over the same ToolRuntime.
