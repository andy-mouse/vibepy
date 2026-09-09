# Axis 2 — Channel adapter boundaries and leakage

HEAD 05d602750328f723354823b8fb97c6bf5862ba03, branch main.

Read: `AGENTS.md`; `docs/architecture.md`; `docs/architecture/adapters.md`, `page-model.md`,
`errors.md`; ADR titles 001–024 in full listing, bodies of ADR-001, 003, 007, 009, 010, 012,
013, 015, 016, 018, 019, 020; `src/vibepy/adapters/**`, `src/vibepy/{tool,page,app}/**`,
`src/vibepy/{errors,serve,describe}.py`, `tests/test_mcp_adapter.py`,
`tests/test_nicegui_adapter.py`, `tests/test_dual_channel.py`, `tests/test_execution_semantics.py`,
`tests/test_serve_command.py`, `samples/todo/src/todo_app/entry.py`,
`hub/src/vibepy_hub/internals/processes.py`. Library behaviour checked against the installed
sources of `mcp` 2.1.1 (`mcp/server/lowlevel/server.py`, `mcp/server/runner.py`,
`mcp_types/_types.py`) and `nicegui` 3.16.0 (`ui_run_with.py`, `page.py`, `nicegui.py`,
`app/app.py`).

## Strengths

- **The projection direction is real, not asserted.** `to_mcp_tool` (projection.py:13-20) sets
  only fields that have a source in `ToolDefinition`, and both schemas are
  `model_json_schema()` of the declared models — ADR-009's "an MCP schema is always the
  declaration's own `model_json_schema()`". Nothing in `src/vibepy/{tool,page,app}` imports
  `mcp` or `nicegui`, and two AST guard tests hold that (with a gap, see Minor 4).
- **The low-level SDK server is used the way ADR-009 requires.** `Server(name, version=,
  lifespan=, on_list_tools=, on_call_tool=)` is exactly the constructor-based handler surface
  documented in `mcp/server/lowlevel/server.py` (module docstring and the `__init__` overload
  at lines 120-200). No decorator, no `MCPServer`, no hand-rolled capability negotiation — the
  SDK derives capabilities from the registered handlers (`get_capabilities`, server.py:551).
- **The adapter holds no running state.** The ToolRuntime comes from `ctx.lifespan_context`,
  which the SDK enters inside `run()` and propagates as `LifespanResultT`; this is the
  mechanism ADR-020 cites, used as documented.
- **Neither adapter constructs a context or touches a handler.** MCP calls
  `ToolRuntime.invoke`; the Web builder calls `PageRuntime.render(name)` and nothing else.
  `PageContext` is built by `PageRuntime` (page/runtime.py:27), `ToolContext` by `ToolRuntime`
  (tool/runtime.py:84). No adapter bypasses ToolRuntime — verified by reading every call site.
- **Addressing a Page by name, not by route** (web.py:48-58) genuinely keeps route knowledge
  inside the adapter: `PageRuntime` never sees a route.
- **`src/vibepy/adapters/__init__.py` exports nothing**, and `vibepy/__init__.py` re-exports no
  adapter symbol, so `import vibepy` pulls in neither NiceGUI nor the MCP SDK. That is a real
  boundary, not a stylistic one.
- **`docs/architecture/errors.md`'s two MCP paths are implemented exactly as written**: JSON-RPC
  `data` for the protocol error, a JSON text block plus `isError` for the rest, and never
  `structuredContent` on a failure — with a test that pins that last point
  (test_mcp_adapter.py:289).
- **The broad `except Exception` in `call_tool` is a deliberate override of an SDK behaviour,
  not ignorance of it.** `mcp/server/runner.py:534-548` maps an unmapped handler exception to a
  generic INTERNAL_ERROR protocol error; the adapter catches first so an app defect reaches the
  agent as a readable result. That matches `CallToolResult`'s own docstring in
  `mcp_types/_types.py:1462-1468`.

## Findings

### Critical

None.

### Important

**1. `register_pages` enumerates the declaration, not the registry the renderer resolves
against — duplicate Page names silently serve the wrong Page.**

`src/vibepy/adapters/nicegui/web.py:34-45` iterates `definition.pages`, while the
`PageRuntime` it was handed resolves through a `PageRegistry` built by `page_registry_for`
(app/composition.py:46-53), which is keyed by name and where "registering a name twice
replaces the earlier registration" (`docs/architecture/page-model.md`, PageRegistry section;
page/registry.py:17-18). Two Pages with one name and two routes therefore produce two
registered routes that both render the second handler. Verified by running the adapter:

```
routes: ['/a', '/b']
render('dup') ran: ['second']
```

ADR-012 exists precisely because a silent replacement is unacceptable: "two Pages declaring one
route fail loudly at registration rather than one disappearing silently". The same disappearance
is reachable through the name, and the adapter — the only place that sees every declaration
before anything is registered — does not check it. `page-model.md` also states that the
registry "enumerates its declarations, because a Web channel adapter projects every
PageDefinition into a route", and `PageRegistry.definitions()` carries the same claim in its
docstring (page/registry.py:26-32); no adapter calls it, so that method is dead and the adapter
uses a second, larger source instead.

Why it matters: an App author gets `/a` serving `/b`'s page with no diagnostic, and the framework
guarantee that a rejected declaration leaves nothing half-registered does not extend to it.

Fix: in the pre-registration validation loop, claim names as well as routes and raise on a
duplicate name (a new declaration-category error, per `docs/architecture/errors.md`), or give
`register_pages` the registry (`PageRegistry.definitions()`) so that one enumeration serves both
registration and resolution.

### Minor

**2. The MCP adapter builds a second ToolRegistry rather than reading the one the runtime owns.**
`server.py:83` calls `tool_registry_for(definition)` for discovery, while `tool_runtime_for`
(composition.py:80) builds another from the same declaration for invocation. Same root cause as
finding 1: a runtime exposes no enumeration, so an adapter re-derives it. Harmless today —
`ToolRegistry` deduplicates by name identically both times, so discovery and dispatch cannot
disagree — but it means the list an agent is shown and the map a call resolves in are two
objects, which is the invariant "ToolRuntime owns generic invocation semantics" being upheld by
coincidence rather than by construction. Fix: expose the declarations through the runtime the
window yields, or accept and document the duplication in `adapters.md` (which currently says the
adapter "reads the registry it enumerates … from the declaration", so the doc is at least
honest).

**3. `list_tools` ignores the pagination cursor.** `server.py:92-98` takes
`types.PaginatedRequestParams | None` and never reads `params`, always returning the full list
and never a `nextCursor`. `ListToolsResult` extends `PaginatedResult` (`mcp_types/_types.py:1438`)
and the low-level server does no paging for a handler, so a client that sends any cursor —
including a stale one — is answered with the whole list as if it were page one. Small Apps make
this invisible; it is still the adapter answering a protocol parameter it did not read. Fix:
either return everything and reject a non-null cursor with INVALID_PARAMS, or implement the
cursor. A one-line decision either way, but it should be a decision.

**4. Route validation covers only the App's own Pages, while registration can silently unregister
NiceGUI's.** `web.py:36-41` validates that a route starts with `/` and that no two Pages claim
one route. But `nicegui.page.__call__` begins with `core.app.remove_route(self.path)`
(nicegui/page.py:110), and `remove_route` drops every route with that exact path
(nicegui/app/app.py:375-377), including NiceGUI's own `/_nicegui/<version>/…` endpoints
registered in `nicegui/nicegui.py:68-109` and the `/favicon.ico` route added at startup. An App
declaring such a path removes framework internals with no error. ADR-012 says the adapter
validates "because NiceGUI reports no collision of its own"; that reasoning covers this case and
the implementation does not. Fix: reject a route in NiceGUI's reserved namespace, or check the
path against `nicegui.app.routes` before registering.

**5. "Routes are left when the window closes" is doc wording the code does not implement.**
`docs/architecture/adapters.md` (build_web_app paragraph) and
`src/vibepy/adapters/nicegui/application.py:38-41` both say routes are "registered inside the
window and left with it". Nothing deregisters them: `register_pages` mutates the process-global
`nicegui.app`, and after `page_runtime_for` exits, the builders still close over a PageRuntime
whose lifespan resource was released. In practice the process ends with the window
(`vibepy.serve`, ADR-017), so the leak is not reachable — but `docs/architecture*` is "current
truth" per AGENTS.md and this sentence reads as a guarantee that is not made. Fix: reword to say
the process outlives no window, or actually remove the routes on exit.

**6. The channel-leak guard tests have a hole at the package root.**
`tests/test_mcp_adapter.py:312-327` and `tests/test_nicegui_adapter.py:149-164` walk
`src/vibepy/{tool,page,app}/*.py` only. `src/vibepy/__init__.py`, `errors.py` and `describe.py`
are unchecked, so an `import mcp` added to the package root — the one place that would make
`import vibepy` drag a channel SDK into every consumer's process — passes both guards. The
invariant being protected ("MCP-specific types and behavior must not leak into the core Tool
model") is a public contract, which is the kind AGENTS.md says tests must verify. Fix: walk
every module under `src/vibepy` except `adapters/` and `serve.py`.

**7. `UNHANDLED_CODE` is not part of the public API although the Agent channel emits it.**
`vibepy/errors.py:17` defines it, `docs/architecture/errors.md` documents it as the code for a
failure the framework did not define, the MCP adapter puts it on the wire through
`to_error_info`, and `tests/test_mcp_adapter.py:17` imports it from `vibepy.errors` — but
`vibepy/__init__.py` exports `ErrorInfo`, `ErrorCategory` and `to_error_info` and not this. A
consumer branching on the payload the adapter produces has to reach into a submodule for one of
the values that payload can carry. Fix: export it alongside the rest of the error contract.

**8. `build_web_app` has no direct test, and the claim `serve.py` makes about it is untested.**
`src/vibepy/serve.py:6-8` says "the adapter builds the application this serves; the command owns
the process and runs it. `tests/test_serve_command.py` holds both to that." That file has three
tests: a page is served, an unknown App fails, a refused window stops the server. None of them
touch `build_web_app` directly, and none assert that building starts nothing. The end-to-end
subprocess tests do prove the substance, so this is a test-quality and doc-accuracy note rather
than a coverage hole: either add an in-process test that `build_web_app` returns without binding
a socket, or drop the sentence.

## Cross-boundary assumptions

Each of these is a guarantee an adapter depends on and does not itself enforce. All were read,
not assumed.

- *The adapter may dump a handler result straight onto the wire because ToolRuntime already
  validated it against the declared output model (ADR-007).* Verified: `tool/runtime.py:47-59`
  revalidates from `model_dump(by_alias=True)`; `server.py:116` then dumps with
  `mode="json"`, so the wire value is JSON-safe and schema-conformant.
- *No adapter needs to build a context.* Verified: `ToolContext` only in `tool/runtime.py:84`,
  `PageContext` only in `page/runtime.py:27`. Neither adapter file constructs either.
- *The Web adapter reaches Tools only through ToolRuntime.* Verified: `web.py` imports
  `PageRuntime` and nothing from `vibepy.tool`; `page_runtime_for` (composition.py:100) wraps
  the same `tool_runtime_for` the Agent channel uses, and `PageRuntime` takes the `ToolInvoker`
  Protocol that `ToolRuntime` satisfies structurally (page/model.py:10-22, ADR-016).
- *Classification of framework failures belongs to the core, not the adapter (ADR-019).*
  Verified: `errors.py:207-225`; the adapter reads `code`/`category` and adds nothing. The
  remaining `except ToolNotFoundError` in `server.py:105` is protocol routing, which
  `docs/architecture/errors.md` explicitly sanctions ("a channel adapter catches a type and
  decides what its protocol does with it") and which `CallToolResult`'s own docstring requires.
- *The SDK enters the server lifespan and exposes it to handlers.* Verified in installed
  `mcp/server/lowlevel/server.py` (the `lifespan:` parameter typed
  `Callable[[Server[T]], AbstractAsyncContextManager[T]]`) and `mcp/server/runner.py:820-840`
  (`serve_one` threads `lifespan_state` into `ServerRunner`).
- *The SDK does not need help with capabilities or error-to-wire mapping.* Verified:
  `get_capabilities` (server.py:551) derives from registered handlers;
  `modern_error_data`/`handler_exception_to_error_data` (runner.py:534-548, 793-800) own the
  wire mapping. The adapter re-implements neither.
- *`ui.run_with` lets the framework window be the served application's lifespan.* Verified:
  `nicegui/ui_run_with.py` captures `app.router.lifespan_context` and wraps it as
  `_startup()` → the captured window → `_shutdown()`, so `FastAPI(lifespan=window)` set before
  the call is honoured, and routes registered inside the window are added to the mounted global
  app after its startup — which Starlette resolves per request, so late registration works.
- *NiceGUI reports no route collision (ADR-012's premise).* Verified: `nicegui/page.py:110` plus
  `nicegui/app/app.py:375-377`. The premise is true, and see finding 4 for where the adapter's
  answer to it stops short.
- *Registries deduplicate by name.* Verified: `tool/registry.py:23-24`, `page/registry.py:17-18`.
  This is the mechanism behind finding 1.
- *No Tool behaviour branches on channel.* Verified by reading `tool/runtime.py`,
  `tool/model.py`, `samples/todo/src/todo_app/entry.py` and `hub/src/vibepy_hub/tools/*`: no
  channel identity exists anywhere in the Tool path — `ToolContext` carries `app_id`,
  `invocation_id`, `dependencies` and nothing else, so the branch is not even representable.
- *No adapter is reachable from the Hub or a sample.* Verified: a grep across `hub/src`,
  `samples`, `src/vibepy/app` and `describe.py` finds exactly one channel import, `from nicegui
  import ui` in the Todo sample's Page handler — which `adapters.md` permits at "the app's UI
  implementation boundary". The Hub starts Web channels only as `python -m vibepy.serve`
  subprocesses (`hub/src/vibepy_hub/internals/processes.py:156-165`).

Observation, not a finding: ADR-010 states the framework supplies a command the agent platform
executes for stdio, and no such module or console script exists at this SHA — only
`vibepy.serve` for the Web channel. No milestone through M10 asks for it and
`docs/roadmap.md` is not to be pre-empted, so the gap is a decision recorded ahead of its
milestone rather than an unmet one. Worth knowing that no App is reachable by an agent today
outside a test that constructs a `Client(server)` in-process.

## Rule concerns

None on this axis. ADR-015's "adapters are built from an AppRuntime" is superseded by ADR-020,
and the current `(definition, lifespan, *, config)` signatures follow ADR-020 and `adapters.md`
rather than ADR-015 — that is the documents working, not drifting.

## Assessment

The adapter boundary is in good condition and is the part of this repository that most visibly
matches its own documents. Both adapters are thin in the sense ADR-003 means: neither holds
business logic, neither builds a context, neither reaches a handler, and both converge on
`ToolRuntime`. Leakage is clean in both directions — the core imports no channel SDK, the core's
public types expose no channel type, and `import vibepy` costs nothing from either channel. The
MCP adapter uses the SDK's documented low-level surface and re-implements nothing the library
provides; its one deliberate divergence (catching before the SDK's INTERNAL_ERROR mapping) is
justified by the protocol and pinned by tests.

The one finding that will bite a user is the Page-name gap: `register_pages` projects a set of
declarations that the runtime it renders through may not be able to address, and the result is a
route quietly serving another Page. It is the same structural gap that makes the MCP adapter
build its own registry — a runtime does not expose what it holds, so adapters re-derive it — and
fixing that once would close both.
