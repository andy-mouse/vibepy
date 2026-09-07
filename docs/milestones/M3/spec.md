# M3 - MCP Adapter: Design

## Scope

`docs/roadmap.md` M3 says to use the official MCP Python SDK, with four acceptance criteria:

- framework Tools appear in MCP discovery
- MCP schema derives from ToolDefinition/Pydantic
- MCP calls go through ToolRuntime
- MCP SDK types do not leak into the core Tool model

Nothing else is built. No transport, no server process, no lifecycle wiring, no Pages, no
AppRuntime.

## Sources

| Contract | Source |
| --- | --- |
| `Framework ToolDefinition -> MCP projection`, never the reverse | `docs/architecture/adapters.md` |
| The adapter projects definitions, discovers Tools, translates arguments and translates results/errors | `docs/architecture/adapters.md` (MCP Adapter responsibilities 1-4) |
| MCP-specific types must not leak into the core Tool package | `docs/architecture/adapters.md`, `docs/decisions/ADR-003-channel-adapters-are-thin.md` |
| An MCP Tool is a projection of a framework Tool | `docs/architecture.md` ("Key distinctions") |
| `Agent -> MCP client -> MCP server -> MCP adapter -> ToolRuntime -> Tool` | `docs/architecture.md` ("Agent channel") |
| Channel adapters invoke Tools through ToolRuntime; adapters own no business logic | `AGENTS.md`, ADR-003 |
| `invoke(name, raw_input)` returns the validated output model; serialization belongs to the adapter | `docs/architecture/tool-model.md` |
| A channel never constructs the invocation context itself | `docs/architecture/runtime.md`, `docs/decisions/ADR-004-definition-runtime-separated.md` |
| Framework errors are the three Tool errors; handler exceptions propagate unchanged | `docs/architecture/tool-model.md` |
| Tool behaviour must not branch on channel | ADR-001, `docs/architecture/tool-model.md` |
| stdio entrypoint belongs to package metadata, not to the runtime | `docs/roadmap.md` M9 ("manifest, entrypoint"), `docs/architecture/lifecycle.md` |

External behaviour comes from the official SDK documentation
(<https://py.sdk.modelcontextprotocol.io/v2/advanced/low-level-server>) and was verified
against the installed `mcp` 2.1.1 package. Each verified fact is marked below.

Two questions no repository document answered were decided with the owner:

1. Which SDK surface the adapter is built on. See "SDK surface".
2. Which layer owns running an MCP server over stdio. See "Transport ownership".

## SDK surface

The adapter is built on the low-level `mcp.server.Server`, with `on_list_tools` and
`on_call_tool` handlers supplied as constructor arguments (verified: `Server.__init__` in
`mcp` 2.1.1 accepts `name`, keyword-only `version` and keyword-only `on_*` handlers).

The high-level `MCPServer` with `@mcp.tool()` was rejected. It derives a Tool's schema and
result conversion from a Python function signature, which would make the SDK the source of
truth for what a Tool is. `docs/architecture/adapters.md` fixes the direction as
`Framework ToolDefinition -> MCP projection` and forbids making MCP decorators the source
of truth. The low-level server returns schemas exactly as given and generates no
structured content on its own, which is what a projection needs.

The cost is accepted deliberately: the adapter constructs `CallToolResult` and maps errors
by hand.

## Transport ownership

M3 builds no transport. `build_mcp_server()` returns the SDK `Server` object and does not
run it.

In stdio, the agent platform (Claude Desktop, Codex) spawns the server process. The two
leftmost links of `docs/architecture.md`'s Agent channel chain — `Agent -> MCP client` —
are owned outside the framework, so `docs/architecture/lifecycle.md`'s startup step 4
("initialize/start channel adapters") does not describe stdio MCP: an AppRuntime cannot
start the process that starts it. That step describes adapters living inside the app
process, such as the NiceGUI Web server or MCP served over HTTP.

What the framework must supply is therefore a command the platform can execute, which is
package metadata. `docs/roadmap.md` M9 owns "manifest, **entrypoint**, source/dependency
metadata"; M10 owns installation and the control plane. The `Server` object M3 produces is
what an M9 entrypoint wraps in stdio, and what M6 starts in-process if MCP over HTTP is
ever served from the app runtime. Neither reuse requires changing M3's output.

This is recorded as an ADR so the boundary survives the deletion of this folder on
integration.

## The M1 omission this milestone repairs

`ToolRegistry` currently binds each Tool at registration and keeps only the bound callable;
the `ToolDefinition` is discarded. Discovery needs the declarations, so registration must
keep them.

This is not a new decision layered over ADR-008 but a correction of its reach. ADR-008
erases the typed Tool because a type parameter in a callable parameter position is
contravariant, so `Tool[BaseModel, BaseModel]` would mean a Tool accepting any model. That
argument is about the handler. `ToolDefinition` holds no callable: its fields are `name`,
`description`, `type[InputT]` and `type[OutputT]`, all read positions. Under PEP 695
inferred variance a frozen `ToolDefinition` is covariant in both parameters, so a
`ToolDefinition[In, Out]` is assignable to `ToolDefinition[BaseModel, BaseModel]` with no
`Any` and no `cast` (verified with the repository's strict pyright configuration). The
definition was erased as collateral because it shared a dataclass with the handler, and no
consumer existed before M3 to reveal it.

`docs/architecture/tool-model.md` already describes the registry as mapping "a Tool name to
the Tool bound under it", so the document and the code disagree today. M3 makes them agree.

The change is confined to storage and enumeration:

- `ToolRegistry.register` also stores `tool.definition` under the same name.
- `ToolRegistry.definitions() -> tuple[ToolDefinition[BaseModel, BaseModel], ...]` returns
  every registered declaration in registration order, mirroring
  `PageRegistry.definitions()`.

Unchanged: the `Tool`, `ToolDefinition`, `ToolHandler` and `ToolContext` models; `bind()`
and its three validation steps; `ToolRuntime.invoke`'s signature and behaviour; every
existing test in `tests/test_tool_core.py`. ADR-008's binding decision stands.

ADR-008 is Accepted, so it is superseded by a new ADR rather than rewritten, per
`AGENTS.md`.

## Package layout

```text
src/vibepy/adapters/
├─ __init__.py
└─ mcp/
   ├─ __init__.py       public exports
   ├─ projection.py     ToolDefinition -> mcp.types.Tool
   └─ server.py         build_mcp_server, the handlers, error mapping
```

Adapters are nested one level deeper than the core packages so that the channel boundary is
visible in the import path and so that M4's NiceGUI adapter has an obvious sibling. The
dependency direction is one-way: `vibepy.adapters.mcp` imports from `vibepy.tool`, and
nothing under `vibepy/tool/` or `vibepy/page/` imports `mcp`.

`vibepy.adapters.mcp` is not re-exported from the top-level `vibepy` package. Importing
`vibepy` must not require the MCP SDK to be importable, and a channel adapter is reached by
its own name.

## Contracts

### Projection

```python
def to_mcp_tool(definition: ToolDefinition[BaseModel, BaseModel]) -> types.Tool
```

| MCP field | Source |
| --- | --- |
| `name` | `definition.name` |
| `description` | `definition.description` |
| `input_schema` | `definition.input_model.model_json_schema()` |
| `output_schema` | `definition.output_model.model_json_schema()` |

Schemas are derived, never written by hand. Pydantic emits `$defs`/`$ref` for nested
models; the SDK carries the schema through unaltered and the client validates structured
content against it (verified: a nested model's schema survives a `list_tools` round trip
byte-identical, and structured content shaped by it is accepted).

No other MCP field is populated. `title`, `icons`, `annotations` and `execution` have no
source in `ToolDefinition`, and `tool-model.md` forbids adding definition metadata before a
milestone requires it.

### The server

```python
def build_mcp_server(
    *, name: str, version: str, registry: ToolRegistry, runtime: ToolRuntime
) -> Server[None]
```

Two collaborators rather than one, because discovery and invocation are different
operations: the registry answers "what Tools exist", which is enumeration, and ToolRuntime
answers "run this one", which `AGENTS.md` requires to be the only invocation path. This
mirrors M2, where the Web adapter is to enumerate `PageRegistry.definitions()` while
invoking through PageRuntime.

`Server[None]` requires passing an explicit lifespan that yields `None`, because the SDK's
default lifespan is typed as yielding `dict[str, Any]`, which would put `Any` into the
adapter's public return type (verified: `Server[None]` fails strict pyright with the
default lifespan and passes with a `None` lifespan). The lifespan does nothing; app-scoped
state is AppRuntime's, from M5A.

`list_tools` returns `ListToolsResult(tools=[to_mcp_tool(d) for d in registry.definitions()])`.

`call_tool` performs exactly one framework operation:

```python
result = await runtime.invoke(params.name, params.arguments or {})
```

It does not validate arguments, does not construct a `ToolContext` and does not touch a
handler. `runtime.md` and ADR-004 reserve context creation for the runtime.

On success it returns

```python
CallToolResult(
    content=[TextContent(type="text", text=json.dumps(data))],
    structured_content=data,
)
```

where `data = result.model_dump(by_alias=True, mode="json")`. `by_alias` matches the dump
that `bind()` already round-trips through the output model (ADR-007); `mode="json"` makes
the payload JSON-safe. The text block carries the same JSON so that a client which ignores
structured content still receives the result.

### Error mapping

The MCP specification distinguishes a tool's own failure, reported inside the result with
`is_error`, from a protocol-level failure such as failing to locate a tool, reported as an
MCP error.

| Framework outcome | MCP representation |
| --- | --- |
| `ToolNotFoundError` | `MCPError(types.INVALID_PARAMS, str(error))` |
| `ToolInputValidationError` | `CallToolResult(is_error=True)` with the error message |
| `ToolOutputValidationError` | `CallToolResult(is_error=True)`, logged at ERROR |
| any other exception from a handler | `CallToolResult(is_error=True)`, logged with `logger.exception` |

An unknown name is a protocol error because the caller addressed something that does not
exist. Invalid input is not: the agent can read the message and correct itself, which is
the reason the specification puts tool failures in the result. Output validation failure
and an unexpected handler exception are app defects; the agent still receives a failed
result, and the traceback goes to the log rather than over the wire.

Raising a bare exception is not an option: the SDK converts it to a generic
`Internal server error` and discards the message, while a raised `MCPError` reaches the
client with its code and message intact (verified: `-32602` and the framework's message
arrive at the client unchanged).

`str(error)` is used only as a human-readable message. Exception types remain the contract;
`docs/roadmap.md` M7 introduces machine-readable codes, and this table moves under them.

Logging uses `logging.getLogger(__name__)`.

## Data flow

```text
Agent -> MCP client -> Server (stdio/HTTP, owned elsewhere)
  list_tools
    -> ToolRegistry.definitions()          -> tuple[ToolDefinition, ...]
    -> to_mcp_tool per definition          -> input_schema/output_schema from Pydantic
  call_tool(name, arguments)
    -> ToolRuntime.invoke(name, arguments)
         -> resolve -> validate input -> ToolContext -> handler -> validate output
    -> CallToolResult(structured_content=dump, content=[TextContent(json)])
```

## Dependency

`mcp>=2.1` joins `[project].dependencies` in `pyproject.toml`. MCP is the Agent channel
technology of a dual-channel framework, not an optional feature, so it is not split into an
extra. `mcp` 2.1.1 requires Python >= 3.10 and the project requires >= 3.12.

## Testing

`tests/test_mcp_adapter.py`, testing public contracts only, driven through an in-memory
`mcp.client.Client(server)` so that assertions travel the real protocol rather than a mock.
The fixture is the Todo sample from `docs/roadmap.md`.

1. **Acceptance 1, discovery.** `list_tools()` reports the registered Tools' names and
   descriptions.
2. **Acceptance 2, derived schema.** Each listed `input_schema` and `output_schema` equals
   the corresponding `model_json_schema()`, including a Tool whose output model nests
   another model.
3. **Acceptance 3, ToolRuntime path.** A Tool's handler records the `ToolContext` it
   received; after an MCP call the recorded context carries the runtime's `app_id` and a
   non-empty `invocation_id`, proving the adapter did not construct the context.
4. **Acceptance 3, result.** `structured_content` equals the validated output model's
   `model_dump(by_alias=True, mode="json")`, and the text block parses to the same object.
5. **Acceptance 4, no leak.** Every module under `src/vibepy/tool/` and
   `src/vibepy/page/` is parsed with `ast` and asserted to contain no import of `mcp` or
   any submodule of it. A test rather than a convention.
6. An unknown Tool name raises `MCPError` at the client with `types.INVALID_PARAMS`.
7. Input the Tool's model rejects yields `is_error=True` and no exception.
8. An exception raised inside a handler yields `is_error=True`.
9. `ToolRegistry.definitions()` returns the registered declarations in registration order,
   and re-registering a name replaces the earlier declaration as well as its callable.

`make lint typecheck test` passes, with no `Any` and no `cast`.

## Public API

`vibepy.adapters.mcp` exports `build_mcp_server` and `to_mcp_tool`. `vibepy.tool` and
`vibepy` gain nothing; `ToolRegistry.definitions()` is a method on an already-exported
class.

## Documents

- ADR: the adapter is built on the low-level MCP `Server`.
- ADR: the agent platform owns the stdio MCP process, so the entrypoint belongs to package
  metadata (M9) rather than to the runtime lifecycle.
- ADR: superseding ADR-008, keeping its handler binding decision and correcting its reach so
  that ToolRegistry stores declarations alongside bound callables.
- `docs/architecture/adapters.md`: the transport ownership boundary in the MCP Adapter
  section.
- `docs/architecture/tool-model.md`: the registry's declaration storage and `definitions()`.

## Not in M3

stdio or HTTP transport, a server process or entrypoint, lifecycle wiring, MCP resources,
prompts, elicitation, progress or cancellation, pagination of discovery, per-channel Tool
exposure or permissions, structured error codes, AppDefinition and AppRuntime, Pages and
NiceGUI.
