# ADR-041: A channel is a protocol, and a Page is declared once and implemented per channel

Status: Proposed

## Context

`docs/architecture.md` draws the product as two lines, one per channel:

```text
Human -> NiceGUI -> Page        -> ToolRuntime -> Tool
Agent -> MCP     -> MCP Adapter -> ToolRuntime -> Tool
```

The lines are named by who is on them. `Channel` says the same in code: `WEB` and `AGENT`, one
named for a technology and one for an audience. Every human-facing surface the framework knows
is a Page, a Page is Python run by the Web channel, and `PageDefinition` carries the `route` the
Web channel serves it at.

MCP Apps (SEP-1865, an extension of MCP identified as `io.modelcontextprotocol/ui`, Draft as of
2026-09-13, `github.com/modelcontextprotocol/ext-apps/specification/draft/apps.mdx`) puts a
human on the MCP line. The facts that bind this record, each from the specification:

- a Tool names a UI through `_meta.ui.resourceUri`; the UI is "a valid HTML5 document" served
  as an MCP resource under the `ui://` scheme with MIME type `text/html;profile=mcp-app`, read
  through `resources/read`;
- the host renders it in a sandboxed iframe when a tool call completes, delivers the call's
  arguments and result to it, and tears it down; the UI calls Tools only as `tools/call`
  proxied by the host;
- `_meta.ui.visibility` lists who may call a Tool, `"model"` and/or `"app"`; the host "MUST
  NOT include" a Tool without `"model"` in the agent's list and "MUST reject" a call from the
  UI to a Tool without `"app"`;
- the client advertises support under `capabilities.extensions["io.modelcontextprotocol/ui"]`
  and a server "SHOULD check client capabilities before registering UI-enabled tools"; a Tool
  "MUST return meaningful content" without the UI.

The official client matrix lists Claude, ChatGPT, VS Code, Goose and Cursor as hosts. The
Python MCP SDK in use (2.1.1) carries the extension's value types and the `client_supports_apps`
judgement; its `Apps` registration helper derives a Tool's schema from a Python function, which
ADR-009 already refused for the reason it gives.

So a human now reaches an App's Tools through MCP, and a Tool can exist for that human and be
hidden from the agent. Neither fits a line labelled "Agent". The two-line drawing was never a
statement about protocols; it was a statement about audiences that happened to be true while
each protocol had one.

Three of the framework's own sentences already say the other thing. `docs/architecture.md`:
"Page != NiceGUI Page primitive. NiceGUI is the rendering/entry technology for framework Pages"
and "Tool != MCP Tool. An MCP Tool is a projection of a framework Tool". `docs/architecture/
adapters.md` lists REST, CLI, webhook and scheduler as future adapters, none of which is an
audience. The first of these sentences has had one witness since M4; a claim that Page is
independent of its rendering technology is untested while there is one technology.

Alternatives considered and not taken:

- Treat MCP Apps as a detail of the Agent channel, a `_meta` projection of a Tool. It puts a
  human surface on the Agent line and gives it no declaration: the set of Tools the surface
  may call, which `visibility` requires, would have to be written into the adapter beside the
  App rather than in the App (ADR-027 says a channel enumerates the declaration).
- Introduce a channel-neutral `View` identity beside or instead of Page, carrying only a name
  and a title, with Page as the Web adapter's rendering of a View (a proposal reviewed on
  2026-09-13). The shape is right and is what this record adopts; the name and the fields are
  not. `View` is the specification's own word for the rendered iframe, so the adapter's
  documentation would use one word for two things. The proposed fields omit `tools`, the one
  field both renderings share that the framework acts on: construction-time validation of the
  Page↔Tool relation and the `visibility` projection both read it.
- A third declaration kind in `AppDefinition` beside Tools and Pages, for the MCP surface. It
  repeats name, title and tools under a second name and leaves "Page != NiceGUI primitive"
  false by making Page the NiceGUI one.
- A field on `ToolDefinition` naming a presentation asset. One consumer, and the relation runs
  the other way: a surface names the Tools that open it, as a Page names the Tools it calls.
- Renaming Page. The specification does not use the word, and calls its own embedded UI an
  "embedded page". Every candidate with no collision in this repository collides with an
  authority (`nicegui.testing.Screen`, `ui.scene`, `ui.tab_panel`) or with the repository's own
  prose (`surface`). The word was never the problem; the axis was.

## Decision

A channel is a protocol. `Channel` names the two the framework speaks, `WEB` and `MCP`, and
says nothing about who is on the other end; the same protocol may carry a human and an agent.
The optional-dependency extras, the records a process writes and what `describe` publishes
carry the same two names.

A Page is declared once and implemented per channel. `PageDefinition` is `name`, `title` and
`tools`, and is channel-neutral. A `Page` pairs that declaration with one implementation per
channel that renders it, at least one: the Web channel's is a `route` and a `PageHandler`; the
MCP channel's is an HTML asset, as a `PurePath` beside the declaring module, and the names of
the Tools that open it. A Page's declared Tools must exist and be exposed on every channel the
Page has an implementation for. A Tool opens at most one Page.

Rendering, context and lifecycle belong to the channel that renders. The Web channel keeps
`PageRuntime`, which refuses a Tool the Page did not declare and binds the render's principal.
The MCP channel projects the declaration: the `ui://<app_id>/<page name>` resource, the
`_meta.ui.resourceUri` on each opening Tool, `visibility` from `tools`, and the HTML's MIME type
are the adapter's to derive and are emitted only to a client that advertised the extension. The
host renders and refuses; the framework declares and projects.

No channel-neutral rendering, UI abstraction or shared Page context is introduced. An
implementation is written against its channel's technology and against nothing else.

## Consequences

- `docs/architecture.md` is rewritten from the core outward: Tools and Pages declared once,
  ToolRuntime as the one execution path, each adapter supplying a Tool exposure and a Page
  implementation in its protocol's terms. The audience lines are removed
- `Channel.AGENT` becomes `Channel.MCP` with value `mcp`; `vibepy-core[agent]` becomes
  `vibepy-core[mcp]`; `InvocationRecord`, `WindowRecord` and `ToolDescription` change value
  with it. Nothing outside this repository reads them yet, which is why the value changes now
  (ADR-025 took the extras split on the same ground)
- `route` leaves `PageDefinition` for the Web implementation, and `PageDescription` describes a
  Page as declared: the declaration and one sub-model per channel implementation. The errors
  `page.route_invalid` and `page.route_conflict` keep their codes and are raised over the Web
  implementation; `page.tool_unresolved` is raised per channel the Page is implemented for
- every shipped Page (Studio's board, `todo-app`, `timer-app`) moves its `route` one level down.
  No shim: nothing has been published
- an App with Tools and no Web channel can now declare a Page, implemented for MCP only, and its
  dependency tree carries no Web technology. `fixtures/notes-app` is the witness, because the
  roadmap already defines it as the Agent-only App
- "a Page reaches only the Tools its declaration names" stays true and is refused by a different
  party per channel: `PageRuntime` for Web, the host for MCP by the `visibility` the adapter
  projected. `docs/architecture/page-model.md` states this; the framework does not pretend to
  refuse what the protocol gives the host
- a human in an MCP App acts as the process's principal, which is the host's (ADR-034,
  `docs/architecture/runtime.md`); a human on the Web channel acts as the render's. Both are
  already the channels' rules; the Page document names the difference
- a Tool hidden from the agent and callable only from the Page (`visibility: ["app"]`) is
  expressible by the protocol and not by this decision, which projects `visibility` from
  `tools` alone. It is a change to how a Tool is exposed and is the owner's, with M14 as its
  home; recorded here so it is not read as forgotten
- an HTML asset needs no external origin in this decision, so the host's restrictive default
  CSP applies and the framework declares none; CSP and sandbox permissions are the MCP
  adapter's to add when an App needs them
- `docs/architecture/packaging.md` states that non-Python files inside an App's package ship in
  its wheel, which `hatchling` already does and `board.css` already relies on
- ADR-002, ADR-003, ADR-009, ADR-012, ADR-017, ADR-025 and ADR-027 stand. ADR-032's "Agent
  channel" is the MCP channel under this record's vocabulary, and its decision is unchanged
- `docs/roadmap.md` gains two milestones ahead of Agent dogfooding: the channel axis and the
  Page split first, the MCP implementation of a Page second, so dogfooding is done on the
  contract that will stand
