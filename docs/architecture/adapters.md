# Channel Adapter Architecture

## Principle

Channel adapters translate a channel protocol/runtime into framework semantics. They do not own business logic.

An adapter is built from a declaration and a lifespan, and reads its runtime from the window its
own host opens. Every adapter builds the object its channel is served through and runs nothing:
`build_mcp_server` returns an SDK server, `build_web_app` returns an ASGI application, and
whoever owns the process runs it. The mechanism each window is opened with is the one that
channel's host documents, and differs between them. See
`docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md`.

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

`build_mcp_server(definition, lifespan, *, config=…, principal=…)` enumerates the declaration for
discovery, and reads the server's name and version from it. Discovery is a filter over that same
declaration: `list_tools` projects the Tools whose `channels` contains the Agent channel, and a
Tool declaring `read_only` is projected with `annotations.readOnlyHint`, which is the only
annotation this adapter sets. A Tool the list omits is refused by name too — ToolRuntime decides
that, and the adapter reports the refusal as it reports every Tool failure, an `isError` result
carrying the `tool.forbidden` payload. It builds no registry of its own, so a running App holds the
one its window created and the list an agent is shown cannot be a different object from the map
its call resolves in. The ToolRuntime a call goes through is read from the SDK's
request context, which carries whatever the lifespan yielded, so the adapter holds no running
state of its own.

The principal every call is invoked as is the host's, given once at build time and carried into
every `invoke`. The process serves whoever launched it, so the principal is fixed for the
server's life rather than read off a request; the adapter decides nothing about it.
`docs/architecture/runtime.md` says why.

The adapter builds an SDK server object; it does not run one. `vibepy_core.mcp` is the command
that runs it over stdio, and `docs/architecture/packaging.md` owns it. Over stdio the agent
platform owns the server process, so the executable entrypoint is package metadata rather than
part of the runtime lifecycle. See
`docs/decisions/ADR-010-agent-platform-owns-the-mcp-process.md`.

## NiceGUI Adapter

NiceGUI is the Web channel technology.

Responsibilities:

1. project/register PageDefinitions as Web routes
2. construct PageContext
3. execute PageHandlers in the NiceGUI lifecycle
4. connect Page interaction to ToolRuntime through ToolInvoker, which ToolRuntime satisfies

`register_pages(definition, pages, *, principal=…)` projects every PageDefinition the declaration
carries onto a NiceGUI route whose builder awaits `PageRuntime.render(name, principal=…)`, so
every render is for the principal the host named. A Page is addressed by name, so a
route change never reaches PageRuntime, and the adapter constructs no PageContext: PageRuntime
owns that.

Registration happens inside the caller's window and each builder closes over the PageRuntime, so
a builder holds its runtime for exactly as long as that window lasts. Nothing reads request
state: NiceGUI documents no lifespan and mounts as a sub-application, and Starlette does not
document lifespan state reaching one, so a closure is used because it is a language guarantee
rather than a library one.

A declaration reaching the adapter already conforms; the adapter registers.

Errors are not translated. A Tool error or a handler exception propagates into NiceGUI,
which renders it. The MCP adapter wraps failures in a result because the MCP protocol
demands an answer to every call; the Web channel makes no such demand.
`docs/architecture/errors.md` describes what the MCP adapter sends.

`build_web_app(definition, lifespan, *, config=…, principal=…)` returns the ASGI application
those routes are served through, with the running window as that application's own lifespan: a
window that refuses to open fails the application's startup rather than leaving a server
answering for nothing. What
the window bounds is the PageRuntime each builder closes over, not the routes themselves — those
are registered on the Web technology's process-global table and stay there, which is why one
process serves one App's Pages. See
`docs/decisions/ADR-026-the-web-window-is-the-served-applications-lifespan.md`.

The adapter registers routes and starts no server; building the application it hands back is not
running one. `vibepy_core.serve` owns the process and runs it. See
`docs/decisions/ADR-012-nicegui-adapter-registers-routes.md`.

The app owns the actual Page UI implementation. The framework owns the integration/runtime
mechanism.

## Future adapters

The architecture should permit additional channels without redefining backend operations:

- REST
- CLI
- webhook
- scheduler/automation

These remain projections or entrypoints over the same ToolRuntime.
