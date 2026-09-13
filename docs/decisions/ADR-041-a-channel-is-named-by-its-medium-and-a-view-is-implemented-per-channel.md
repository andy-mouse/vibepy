# ADR-041: A channel is named by its medium, and a View is declared once and implemented per channel

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
statement about media; it was a statement about audiences that happened to be true while
each medium had one.

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
- Introduce a channel-neutral `View` identity carrying only a name and a title (a proposal
  reviewed on 2026-09-13). The shape and the name are what this record adopts; the fields are
  not. The proposed fields omit `tools`, the one field both renderings share that the framework
  acts on: construction-time validation of the View↔Tool relation and the `visibility`
  projection both read it.
- A third declaration kind in `AppDefinition` beside Tools and Pages, for the MCP surface. It
  repeats name, title and tools under a second name and leaves "Page != NiceGUI primitive"
  false by making Page the NiceGUI one.
- A field on `ToolDefinition` naming a presentation asset. One consumer, and the relation runs
  the other way: a surface names the Tools that open it, as a Page names the Tools it calls.
- Naming the channels by who runs their process, `app` for the one Studio starts and `mcp` for
  the one an agent platform starts (owner, 2026-09-14). The distinction is real and is already
  owned: ADR-020 gives the channel's host the runtime lifecycle and ADR-010 gives the agent
  platform the stdio MCP process. It is a deployment fact, not what the adapter is written
  against, and the two axes coincide only while MCP is stdio; over streamable HTTP Studio could
  host an MCP process. `App` is also the framework's word for the unit of packaging and the
  specification's word for the embedded UI. The host stays the lifecycle document's axis.
- Keeping the name Page for the channel-neutral declaration. The specification does not use
  the word and calls its own embedded UI an "embedded page", and `docs/architecture.md` had
  claimed the word since M4 with "Page != NiceGUI Page primitive". The owner decided against it
  (2026-09-14): a page is what a browser shows, and a declaration that is equally an embedded
  card in a conversation should not be named for one of its renderings. Every other candidate
  collides with an authority or with this repository's prose (`nicegui.testing.Screen`,
  `ui.scene`, `ui.tab_panel`, `UI`, `surface`), so the choice was between Page and View.

## Decision

A channel is the medium an App is served through, and is named by that medium and not by who
is on it. `Channel` names the two the framework serves, `WEB` and `MCP`, and says nothing about
who is on the other end; one medium may carry a human and an agent. "Protocol" is not the
word: `web` is a medium reached over HTTP, and the future adapters `docs/architecture/adapters.md`
lists — REST, CLI, webhook, scheduler — are media too, of which only two are protocols. The word
"channel" is kept, and this record fixes what it means.
The optional-dependency extras, the records a process writes and what `describe` publishes
carry the same two names.

A View is declared once and implemented per channel. `ViewDefinition` is `name`, `title` and
`tools`, and is channel-neutral. A `View` pairs that declaration with one implementation per
channel that renders it, at least one: the Web channel's is a `route` and a handler, and is a
Page — the word keeps that one meaning, a View as a browser shows it; the MCP channel's is an
HTML asset, as a `PurePath` beside the declaring module, and the names of the Tools that open
it. A View's declared Tools must exist and be exposed on every channel the View has an
implementation for. A Tool opens at most one View.

`View` is also the specification's word for the rendered iframe. Where the adapter's
documentation means that, it uses the specification's other name for it, the App's guest UI
("App (Guest UI)" in the capability section), and never coins a third.

Rendering, context and lifecycle belong to the channel that renders. The Web channel keeps
`PageRuntime`, which refuses a Tool the View did not declare and binds the render's principal.
The MCP channel projects the declaration: the `ui://<app_id>/<view name>` resource, the
`_meta.ui.resourceUri` on each opening Tool, `visibility` from `tools`, and the HTML's MIME type
are the adapter's to derive and are emitted only to a client that advertised the extension. The
host renders and refuses; the framework declares and projects.

No channel-neutral rendering, UI abstraction or shared View context is introduced. An
implementation is written against its channel's technology and against nothing else.

## Consequences

- `docs/architecture.md` is rewritten from the core outward: Tools and Views declared once,
  ToolRuntime as the one execution path, each adapter supplying a Tool exposure and a View
  implementation in its medium's terms. The audience lines are removed. `docs/architecture/
  page-model.md` becomes `view-model.md`; ADR-002 "Pages consume Tools" takes an amendment
  naming the View, its decision unchanged
- `Channel.AGENT` becomes `Channel.MCP` with value `mcp`; `vibepy-core[agent]` becomes
  `vibepy-core[mcp]`; `InvocationRecord`, `WindowRecord` and `ToolDescription` change value
  with it. Nothing outside this repository reads them yet, which is why the value changes now
  (ADR-025 took the extras split on the same ground)
- `PageDefinition`, `Page`, `PageContext`, `PageRegistry` and `AppDefinition.pages` take their
  View names; `PageRuntime` and `PageHandler` stay, being the Web implementation's. `route`
  leaves the declaration for the Web implementation, and `ViewDescription` describes a View as
  declared: the declaration and one sub-model per channel implementation. The `page.*` error
  codes become `view.*` where they are the declaration's (`name_conflict`, `tool_unresolved`,
  `tool_undeclared`, `not_found`) and stay `page.*` where they are the Web implementation's
  (`route_invalid`, `route_conflict`); `tool_unresolved` is raised per channel the View is
  implemented for. No shim: nothing has been published
- every shipped View (Studio's board, `todo-app`, `timer-app`) is renamed and moves its `route`
  one level down
- an App with Tools and no Web channel can now declare a View, implemented for MCP only, and its
  dependency tree carries no Web technology. `fixtures/notes-app` is the witness, because the
  roadmap already defines it as the Agent-only App
- "a View reaches only the Tools its declaration names" stays true and is refused by a different
  party per channel: `PageRuntime` for Web, the host for MCP by the `visibility` the adapter
  projected. `docs/architecture/view-model.md` states this; the framework does not pretend to
  refuse what the protocol gives the host
- a human in an MCP App acts as the process's principal, which is the host's (ADR-034,
  `docs/architecture/runtime.md`); a human on the Web channel acts as the render's. Both are
  already the channels' rules; the View document names the difference
- a Tool hidden from the agent and callable only from the View (`visibility: ["app"]`) is
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
  View split first, the MCP implementation of a View second, so dogfooding is done on the
  contract that will stand. Later milestones say View where they name the contract; delivered
  milestones keep Page as a statement of their date
