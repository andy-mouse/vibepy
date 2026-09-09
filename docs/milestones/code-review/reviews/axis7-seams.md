# Axis 7 — Seam tracing (HEAD 05d6027)

## Traced paths

### Human -> NiceGUI -> Page -> ToolRuntime -> Tool -> App Domain

1. `src/vibepy/serve.py:main` — argparse, `_CONFIG.validate_json(sys.stdin.read())`
2. `src/vibepy/serve.py:_entrypoint` — `discover_apps()` -> `EntryPoint.load()` -> `_is_entrypoint`
3. `src/vibepy/serve.py:_serve` — `build_web_app(entrypoint.definition, entrypoint.lifespan, config=…)` then `uvicorn.run`
4. `src/vibepy/adapters/nicegui/application.py:build_web_app` -> `window` (ASGI lifespan) + `ui.run_with(served)`
5. `src/vibepy/app/composition.py:page_runtime_for` -> `page_registry_for` -> `tool_runtime_for`
6. `src/vibepy/app/composition.py:tool_runtime_for` -> `tool_registry_for` -> `_validated` -> `lifespan(validated)`
7. `samples/todo/src/todo_app/entry.py:todo_lifespan` -> `TodoStore(config.db_path)`
8. `src/vibepy/tool/runtime.py:ToolRuntime.__init__`, `src/vibepy/page/runtime.py:PageRuntime.__init__`
9. `src/vibepy/adapters/nicegui/web.py:register_pages` -> route validation -> `ui.page(route,…)(_builder(pages, name))`
10. `src/vibepy/adapters/nicegui/web.py:_builder.build` -> `PageRuntime.render(name)`
11. `src/vibepy/page/runtime.py:PageRuntime.render` -> `PageRegistry.resolve` -> `PageContext(tools=self._tools)` -> `page.handler(ctx)`
12. `samples/todo/src/todo_app/entry.py:todos_page` -> `ctx.tools.invoke("list_todos", {})` / `add()` -> `invoke("create_todo", {...})`
13. `src/vibepy/tool/runtime.py:ToolRuntime.invoke` -> `ToolRegistry.resolve` -> `ToolContext(app_id, uuid4, dependencies)` -> `Tool.bound`
14. `src/vibepy/tool/runtime.py:Tool.__init__.bound` -> `input_model.model_validate` -> handler -> `model_dump(by_alias=True)` -> `output_model.model_validate`
15. `samples/todo/src/todo_app/entry.py:list_todos` / `create_todo` -> `ctx.dependencies.TodoStore.list_all/create`

### Agent -> MCP -> MCP Adapter -> ToolRuntime -> Tool -> App Domain

1. MCP client (`tests/test_dual_channel.py` uses `mcp.client.Client`; over stdio the platform launches the process)
2. `src/vibepy/adapters/mcp/server.py:build_mcp_server` — `tool_registry_for(definition)` at build time; `Server(definition.app_id, version=…, lifespan=server_lifespan, on_list_tools=…, on_call_tool=…)`
3. `server_lifespan` -> `src/vibepy/app/composition.py:tool_runtime_for` -> steps 6–8 above (identical)
4. discovery: `list_tools` -> `ToolRegistry.definitions()` -> `src/vibepy/adapters/mcp/projection.py:to_mcp_tool` -> `model_json_schema()`
5. call: `call_tool` -> `ctx.lifespan_context.invoke(params.name, params.arguments or {})` -> `ToolRuntime.invoke` (steps 13–15, identical)
6. result: `result.model_dump(by_alias=True, mode="json")` -> `CallToolResult(content=[TextContent], structured_content=data)`
7. failure: `_payload`/`_failure` -> `vibepy/errors.py:to_error_info` -> `{code, category, message, details}`

### Hub (platform tier)

`hub/src/vibepy_hub/entry.py:APP` -> `hub_lifespan` -> `HubDeps(root, Processes)` -> `hub/src/vibepy_hub/tools/runtime.py:start_app` -> `installed_facts` -> `hub/src/vibepy_hub/internals/processes.py:Processes.start` -> `asyncio.create_subprocess_exec(interpreter, "-m", "vibepy.serve", facts.declared_name, "--port", …)` + config on stdin -> re-enters the Web path above inside the App's own environment.

## Strengths

- **ToolContext is genuinely symmetric.** Both channels reach `ToolRuntime.invoke` (`src/vibepy/tool/runtime.py:82`) and neither constructs a context. `app_id`, `invocation_id` and `dependencies` are populated by one code path with no channel-conditional field. There is no `channel` field to branch on, so `docs/architecture/tool-model.md`'s "Channel neutrality" section is enforced by absence rather than by discipline.
- **One name end to end.** `ToolRegistry` keys on `tool.definition.name` (`src/vibepy/tool/registry.py:24`), `to_mcp_tool` publishes `definition.name` verbatim (`projection.py:16`), `call_tool` forwards `params.name` unchanged (`server.py:104`), and `todos_page` calls `ctx.tools.invoke("list_todos", …)`. No per-channel casing, prefixing or namespacing anywhere. ADR-016 holds.
- **No Page bypasses a Tool.** Every business state change reachable from `todos_page` goes through `ctx.tools.invoke`; `TodoStore` is unreachable from the Page. The Hub declares no Pages. ADR-002 holds.
- **The Web window is the ASGI lifespan**, so a refused configuration is a server that does not serve (`application.py:44-49`, proven by `tests/test_serve_command.py:test_a_window_that_will_not_open_stops_the_server`). Acquisition happens after validation on both channels (`composition.py:80-83`).
- **Error normalization is shared.** `to_error_info` lives in the core, and the MCP adapter reads it on both of its paths rather than classifying itself. ADR-019's "one classification for all channels" is real for Tool-level failures.

## Findings

### Critical

None. No path mutates domain state outside a Tool, and no ToolContext field differs between channels.

### Important

**I1. A framework error's stable code does not survive the Web channel's process boundary, which is exactly the boundary the Hub reads.**
- Seam sides: `src/vibepy/app/composition.py:63-68` (`_validated` raises `AppConfigInvalidError`, code `config.invalid`) and `hub/src/vibepy_hub/internals/processes.py:156-176` (`Processes.start` inherits the child's stderr and reports only `f"the App exited with {process.returncode}"`), surfacing at `hub/src/vibepy_hub/tools/runtime.py:52-53` as `hub.start_failed`.
- What's wrong: on the Agent channel a `config.invalid` reaches nobody either — it escapes `server_lifespan` into `run()` — but the Agent channel's host is a platform whose contract covers a dead process. The Web channel's host is the Hub, a first-class caller in this repo, and it reads the failure as an integer. `tests/test_serve_command.py:92` even accepts either `config.invalid` **or** `AppConfigInvalidError` in stderr, i.e. a traceback, confirming no structured form is emitted. `src/vibepy/serve.py:99-102` already writes `{"code", "message"}` JSON for entrypoint failures, so the command is internally inconsistent about the same class of failure.
- Violates: ADR-019 ("an agent reads `code` and `category` rather than a sentence"; "one classification exists for all channels"), `docs/architecture/errors.md` §Codes (`config.invalid`, category `caller`).
- Why it matters: `caller` means a different call could succeed — the Hub could re-prompt for configuration. It cannot tell that apart from a crash, so `start_app` gives an agent an unactionable diagnostic for the one failure that is most likely and most fixable.
- Fix: validate the configuration in `vibepy/serve.py:main` against `entrypoint.definition.config` before `_serve`, and on `AppConfigInvalidError` write the same `{"code","message","details"}` JSON to stderr and exit 1 — the shape the module already uses. Optionally have `Processes.start` capture stderr and carry it in `StartFailed.reason`.

**I2. `register_pages` never unregisters, so the documented "left when it closes" is not true, and a second window in one process silently steals the routes of the first.**
- Seam sides: `src/vibepy/adapters/nicegui/application.py:43-47` (`window` claims routes are "registered as the window opens and left when it closes", per `docs/architecture/adapters.md:77-80`) and `src/vibepy/adapters/nicegui/web.py:45` (`ui.page(...)` mutates NiceGUI's process-global route table; nothing removes it on exit).
- What's wrong: when the window closes, the routes remain on the global app and each builder still closes over a `PageRuntime` whose `ToolRuntime` holds a released resource. `tests/test_nicegui_adapter.py:1-6` documents that only NiceGUI's `user` fixture resets that table — i.e. the test suite is the only thing performing the cleanup the docstring attributes to the window. ADR-012 already records that `ui.page.__call__` removes any route already at that path, so a second `register_pages` for the same route replaces the first with no error; `register_pages` validates uniqueness only *within* one definition, never across passes.
- Violates: `docs/architecture/adapters.md` (NiceGUI section, "routes are registered as the window opens and left when it closes"); ADR-012's stated consequence "two Pages declaring one route fail loudly at registration rather than one disappearing silently" — which holds inside a pass and fails across passes.
- Why it matters: this is the one place where a resource-lifetime claim is asymmetric between channels. The MCP adapter holds no process-global state; the NiceGUI adapter leaves state behind that outlives the window it belongs to. Any host that opens two windows in one process (a test, a future in-process Hub UI, a restart-on-config-change) serves pages backed by a closed window.
- Fix: either make the claim true — have `window` remove the routes it registered on exit (record the paths and drop them from `nicegui.app.routes`) — or correct `docs/architecture/adapters.md` and the `build_web_app` docstring to say registration is process-global and irreversible, as ADR-012 actually says.

**I3. A cancelled `Processes.start` orphans a child the window then cannot release.**
- Seam sides: `hub/src/vibepy_hub/internals/processes.py:170-177` (`except StartFailed:` only) and `hub/src/vibepy_hub/entry.py:40-43` (`finally: await processes.aclose()`, which iterates `self._running`).
- What's wrong: the child is inserted into `self._running` only *after* `_wait_until_answering` returns. If the awaiting task is cancelled — the Hub's own window closing, an MCP request cancellation, a client disconnect — `CancelledError` is not `StartFailed`, so the child is neither killed nor registered, and `aclose()` has nothing to release. The same hole exists between `create_subprocess_exec` and the `try` for a stdin `BrokenPipeError` when the child dies immediately.
- Violates: `hub/src/vibepy_hub/entry.py:34-36` docstring ("a window that closes leaves no child behind"), ADR-018 (acquisition bound to release), ADR-024 (the Hub is subject to every rule an App is).
- Why it matters: an orphaned `vibepy.serve` keeps a port and an App's resource after the Hub is gone, and no Hub Tool can see or stop it — `running()` only knows what `_running` holds.
- Fix: wrap everything after `create_subprocess_exec` in `try/except BaseException:` (or `finally` with a success flag) that kills and reaps the child before re-raising, or register the process in `_running` immediately and let `aclose()`/`stop()` own it from birth.

**I4. Installing an App by its project name creates a second identity, and `list_apps` then reports one App as two rows.**
- Seam sides: `hub/src/vibepy_hub/tools/installation.py:42-48` (`_candidate_folder` matches `app_name in {row.name, row.folder.name}`) and `hub/src/vibepy_hub/tools/installation.py:141-151` (`list_apps` keys available rows by `row.folder.name` only), with `installation.py:97` naming the environment after whatever alias was passed.
- What's wrong: `install_app({"app_name": "vibepy-notes"})` is accepted and creates `envs/vibepy-notes`, while the available listing continues to offer the same folder under `notes`. `_installed` yields a row `vibepy-notes` (installed) and the candidate loop adds a row `notes` (available). Every subsequent Tool — `configure_app`, `start_app`, `remove_app` — is keyed on whichever alias the caller happened to use.
- Violates: `docs/architecture/app-model.md` ("An App is the unit of packaging and declaration"); ADR-016's principle of one name for one addressable thing, applied at the Hub's own seam.
- Why it matters: an agent that reads `list_apps` and then installs the `name` it saw ends up with an App it can never see as installed under the name it installed by, and a duplicate row it will try to install again.
- Fix: resolve the alias to the folder in `install_app` and file the installation under `row.folder.name` unconditionally (the `Candidate` is already in hand), so one App has exactly one Hub-facing name.

**I5. The Hub publishes a second, uncategorized error vocabulary through the same channel edge as the framework's.**
- Seam sides: `hub/src/vibepy_hub/models.py:13-18` (`Diagnostic` = `code`, `message`, `details` — no `category`) and `src/vibepy/errors.py:193-204` (`ErrorInfo` = `code`, `category`, `message`, `details`), both arriving at an agent through `src/vibepy/adapters/mcp/server.py` — the former inside a *successful* `CallToolResult`, the latter inside one marked `is_error`.
- What's wrong: `hub.not_installed`, `hub.already_running`, `hub.start_failed`, `hub.candidate_absent`, `hub.no_web_channel`, `hub.install_failed`, `hub.source_unreadable`, `hub.declaration_missing` are codes in no table and carry no category. An agent calling `start_app` must read `is_error` *and* an optional `diagnostic` field, and cannot ask of a Hub failure the one question `category` exists to answer.
- Violates: `docs/architecture/errors.md` ("A category says what kind of failure this is… A caller reads it to learn whether a different call could succeed") read together with ADR-024 ("the Hub is subject to every rule an App is subject to").
- Why it matters: M11's Hub UI and any agent both have to hand-code retryability per Hub code. No regional reviewer owns this: the errors reviewer sees only the framework table, the Hub reviewer sees only a consistent local convention.
- Fix: give `Diagnostic` a `category` field carrying `ErrorCategory`'s values, and state in `docs/architecture/errors.md` that an App may publish expected failures as data provided it uses that shape — or say explicitly that it may not.

**I6. `docs/architecture/packaging.md` promises an Agent-channel entrypoint that no package in this repo supplies.**
- Seam sides: `docs/architecture/app-model.md` §"The composition root" and `docs/architecture/packaging.md` §"Running a channel" (Web channel: `python -m vibepy.serve`; "The Agent channel's is a command the MCP client launches") and the code: `src/vibepy/` has `describe.py` and `serve.py` and no MCP counterpart; `samples/todo/pyproject.toml`, `samples/notes/pyproject.toml` and `hub/pyproject.toml` declare no `[project.scripts]`.
- What's wrong: `build_mcp_server` is only ever reached in-process, by tests. An installed `todo-app` cannot be launched by Claude Desktop or Codex, so the Agent half of the framework's headline diagram is unreachable end to end for a real installation. No roadmap milestone (M11–M19) names this work.
- Violates: `AGENTS.md` ("`docs/architecture*` = current truth"), ADR-010 ("What the framework supplies for stdio is a command the platform executes"), ADR-023's symmetry between the two commands.
- Why it matters: `samples/notes` exists specifically to demonstrate ADR-017's "complete for an agent" App, and today that App is complete for nobody.
- Fix: either add `python -m vibepy.serve_mcp <app-name>` mirroring `serve.py` (stdin config, stdio transport, same entrypoint resolution), or amend `packaging.md` to say the Agent-channel command is not yet supplied and name the milestone that will supply it.

**I7. The declared output schema an agent reads is the validation schema; the payload it receives is the serialization dump.**
- Seam sides: `src/vibepy/adapters/mcp/projection.py:19` (`output_schema=definition.output_model.model_json_schema()` — Pydantic's default `mode="validation"`) and `src/vibepy/adapters/mcp/server.py:116` (`result.model_dump(by_alias=True, mode="json")` — the serialization shape), with `src/vibepy/tool/runtime.py:54-57` choosing the by-alias round trip.
- What's wrong: for any output model where the two schemas differ — a field with distinct `validation_alias`/`serialization_alias`, or a `computed_field`, which appears only in the serialization schema — `structured_content` will not conform to the `outputSchema` the same adapter published. `docs/architecture/errors.md` itself cites the MCP requirement that structured results conform to the declared output schema.
- Violates: ADR-007 (the framework guarantees the published schema and the returned value cannot diverge) and ADR-009 (the projection direction is the declaration's own schema).
- Why it matters: latent today (no in-repo output model uses aliases or computed fields), but it is exactly the kind of divergence ADR-007 exists to prevent, and it fails only at a client's validator, far from either side of the seam.
- Fix: publish `model_json_schema(mode="serialization")` as the MCP `output_schema`, since serialization is what travels; or add a projection-time check that the two schemas agree and fail the declaration loudly.

**I8. The Web channel loses a Tool's declared output type and the sample re-narrows it with `assert`.**
- Seam sides: `src/vibepy/page/model.py:22` (`ToolInvoker.invoke(...) -> Awaitable[BaseModel]`) and `samples/todo/src/todo_app/entry.py:90,94` (`assert isinstance(refreshed, TodoList)`).
- What's wrong: the Agent channel keeps the declaration's meaning (it publishes the output schema and serializes the model); the Web channel receives `BaseModel` and the App recovers the type with a bare `assert`, which `python -O` removes — after which `rendered()` is called with an unchecked value. `docs/architecture/page-model.md` says the narrow signature exists so "no second validation path exists"; an `assert isinstance` in every Page is precisely a second, weaker one.
- Violates: ADR-001 (a Tool's meaning should survive both projections identically) as it lands in `docs/architecture/page-model.md` §ToolInvoker.
- Why it matters: this is the pattern every App author will copy from the sample, and it is the framework's only guidance for consuming a Tool result on the Web side.
- Fix: the sample should narrow with a real check the interpreter cannot strip — `TodoList.model_validate(result)` (which `tests/test_dual_channel.py:titles` already models as "the output model is the contract") — and `page-model.md` should say so. A typed overload of `invoke` is a larger question that belongs in an ADR.

**I9. `AppNotDeclared` is a framework exception outside the framework's exception hierarchy.**
- Seam sides: `src/vibepy/serve.py:33-34` (`class AppNotDeclared(Exception)`) and `src/vibepy/errors.py:33` (`class VibepyError(Exception)` with `code: ClassVar[str]`, plus the `_CATEGORIES` table at `errors.py:180`).
- What's wrong: a published framework command raises an exception with no `code`, no category, and no `details()`, and reports it at `serve.py:96-98` as a bare sentence on stderr while the two failures beside it write JSON. `tests/test_serve_command.py:73` asserts only that the app name appears in stderr.
- Violates: `AGENTS.md` §Python conventions — "Framework exceptions derive from a single base class. Exception types are the contract, not message strings"; ADR-019 ("Every framework exception carries a stable `code`"; "a test that walks every subclass enforces both" — this class escapes that test by not being a subclass).
- Why it matters: a Hub or agent reading `vibepy.serve`'s stderr gets JSON for two failures and prose for the third, at the same edge.
- Fix: make it `AppNotDeclaredError(VibepyError)` with a code (e.g. `package.app_not_declared`, category `caller`) mapped in `_CATEGORIES`, and report it through the same JSON writer.

**I10. Hub state is read-modify-written per invocation with no serialization, and `ToolRuntime` explicitly permits overlap.**
- Seam sides: `src/vibepy/tool/runtime.py:82` / `docs/architecture/runtime.md` §Concurrency ("ToolRuntime permits concurrent invocations by default… ToolRuntime must not serialize all calls") and `hub/src/vibepy_hub/internals/state.py:31-65` used by `tools/configuration.py:40-45`, `tools/packages.py:30-44,51-58` and `tools/installation.py:160-169` as read -> mutate -> `write_state`.
- What's wrong: every one of those handlers awaits nothing between the read and the write *except* in `configure_app`… but `register_package_source` and `remove_app` do await (`processes.stop`), and more importantly the MCP SDK spawns `tools/call` requests concurrently (runtime.md's own reading of the SDK). Two overlapping `configure_app`/`register_package_source` calls lose one update, and `write_state` truncates and rewrites the whole file — a crash mid-write loses everything, including held secrets.
- Violates: `docs/architecture/runtime.md` §"Where concurrency is owned" — the domain row is the App's own responsibility, and ADR-024 makes the Hub an App bound by it.
- Why it matters: the lost value is configuration including secrets, and the Hub is the one App in this repo that is guaranteed to receive concurrent calls from an agent.
- Fix: guard state mutation with an `asyncio.Lock` held in `HubDeps` (application-scoped, which is where the window's state belongs), and write through a temporary file plus `os.replace` so a partial write cannot destroy the state.

### Minor

**M1. The Agent channel builds two `ToolRegistry` objects per running channel.**
`src/vibepy/adapters/mcp/server.py:83` builds one for discovery at build time; `src/vibepy/app/composition.py:80` builds another inside the window for invocation. Discovery therefore enumerates a registry that no call goes through. They are built from the same frozen declarations so they agree today, but ADR-015's "one App, one backend is a type-level guarantee" no longer has an object to attach to. Fix: have `tool_runtime_for` expose (or `build_mcp_server` enumerate) the one registry the runtime holds, or state in `docs/architecture/adapters.md` that discovery reads the declaration rather than the runtime's registry.

**M2. Declaration errors are raised after the resource is acquired on the Web channel only.**
`src/vibepy/app/composition.py:81-83` validates configuration before entering the lifespan ("a window that cannot run acquires nothing", `docs/architecture/app-model.md`), but `src/vibepy/adapters/nicegui/application.py:45-46` calls `register_pages` — which raises `PageRouteInvalidError`/`PageRouteConflictError`, both category `declaration` — *after* `page_runtime_for` has entered the lifespan. The Agent channel has no post-acquisition declaration check at all. ADR-018's consequences acknowledge this ("route validation runs behind startup… no milestone has required" a definition-only path), so it is deferred rather than unnoticed; recording it because it is the one ordering difference between the two channels' windows.

**M3. `_installed` compares an entry-point name against a directory name when facts are missing.**
`hub/src/vibepy_hub/tools/installation.py:62` — `wanted = facts.declared_name if facts else env.name`. For `todo` (env dir `todo`, entry-point name `todo-app`) a lost or unreadable `.vibepy-facts.json` produces a spurious `hub.declaration_missing`, because `read_facts` returns `None` on a `ValidationError` (`internals/installer.py:125-127`). Fix: when facts are absent, report "facts unreadable" rather than asserting the declaration is gone.

**M4. Entry-point name, `app_id`, project name and Hub folder name are four independent identities and the samples disagree about them.**
`samples/todo/pyproject.toml` declares `todo-app = "todo_app.entry:APP"` with `app_id="todo-app"`; `samples/notes/pyproject.toml` declares `notes = "notes_app.entry:APP"` with `app_id="notes-app"`; `hub/pyproject.toml` declares `hub = …` with `app_id="vibepy-hub"`. `build_mcp_server` names the MCP server `app_id` (`server.py:123`) while `vibepy.serve` is addressed by the entry-point name (`serve.py:50`). Nothing is broken, but the samples model three different conventions for what is nominally one App's name. Fix: make the samples consistent, or have `packaging.md` state which name is which and why they need not match.

**M5. `install_app` files the description of whichever App an environment happens to list first.**
`hub/src/vibepy_hub/tools/installation.py:113,124` — `next(iter(described), None)` and `declared[0].app_name`. `discover_apps` is sorted, so this is deterministic, but an environment holding two declared Apps (which packaging.md admits is representable) is silently reduced to one. Fix: match the described entry to the declared ref by name, and diagnose a folder that installs more than one App.

## Seam-by-seam verdict

- **Page -> ToolRuntime**: sound. `PageRuntime.render` builds `PageContext(tools=self._tools)` where `_tools` is the window's `ToolRuntime` satisfying `ToolInvoker` structurally; no adapter, no second validation path, no `DepsT` leak into the Page package. One caveat (I8): the declared output type is erased to `BaseModel` and the sample recovers it with a strippable `assert`.
- **MCP -> ToolRuntime**: sound. `call_tool` forwards `params.name` and `params.arguments or {}` to `ctx.lifespan_context.invoke` and adds nothing. Discovery reads a second registry instance (M1) and publishes the validation schema for a serialized payload (I7).
- **ToolRuntime -> Tool**: sound. One `invoke`, one `ToolContext` per call with a fresh `uuid4`, no lock, no channel argument. Identical bytes on both paths.
- **Tool -> App Domain**: sound. `Tool.bound` validates in, calls the handler, dumps and revalidates out; `TodoStore`/`HubDeps` are reachable only through `ctx.dependencies`. ADR-007 and ADR-013 both hold in code.
- **Entry point -> AppRuntime -> adapter**: suspect. `AppEntrypoint` is a value, `describe()` acquires nothing, and no runtime object exists outside a window — all as ADR-020/021 require. But `serve.py:_entrypoint` re-implements `package.py:describe_app`'s load-and-check with a different exception hierarchy (I9), and the Agent channel has no entrypoint command at all (I6).
- **Error propagation**: suspect. Tool-level failures reach an MCP client with code, category, message and details, and reach a Web user as an unaltered exception — both by doctrine. Window-level failures do not: `config.invalid` degrades to an exit code before the Hub sees it (I1), and the Hub publishes a parallel, category-less vocabulary through the same edge (I5).
- **Resource lifetime**: suspect. Both windows are `async with` over one lifespan, acquisition follows validation on both, and `AsyncExitStack` semantics apply as `lifecycle.md` claims. But the NiceGUI adapter leaves process-global routes behind that outlive the window (I2), and the Hub's child processes have a cancellation window in which they are owned by nobody (I3).

## Rule concerns

`docs/architecture/adapters.md` says the Web channel "translates nothing" because "the MCP protocol demands an answer to every call; the Web channel makes no such demand." That is true of a render, but the Hub is a Web-side *caller* that does demand an answer, and I1 is the consequence: the doctrine written for a browser is applied to a process boundary the framework itself defines. The rule may be right; the boundary it covers should be stated as "a rendered page", not "the Web channel".

## Assessment

The two call paths genuinely converge. `ToolContext` is built in exactly one place, the invocation name is one string from the Page's literal to the registry key to the MCP tool listing, and nothing in `src/vibepy/tool/` or `src/vibepy/page/` imports a channel SDK — the invariants the architecture is built around hold where it counts. The defects are all at the outer rings, and they cluster in one shape: **a failure or a resource that crosses a process boundary loses the guarantees that hold inside one.** A stable error code becomes an exit code (I1), a window's routes outlive the window (I2), a child process falls out of its owner's hands under cancellation (I3), an App acquires a second name at the Hub (I4), and the Agent channel has no boundary-crossing command at all (I6). None of these is visible from inside a single region — the framework reviewer sees a clean `to_error_info`, the Hub reviewer sees a consistent `Diagnostic`, and neither sees that they meet.
