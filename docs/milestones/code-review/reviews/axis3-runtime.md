# Axis 3 review — Runtime, lifecycle, and configuration

HEAD 05d602750328f723354823b8fb97c6bf5862ba03, branch main, clean tree.

Read for this review: `AGENTS.md`, `docs/architecture.md`, all ten `docs/architecture/*.md`,
ADR titles 001–024 and the full text of ADR-004/006/013/015/017/018/019/020/021/022,
`docs/roadmap.md` M10, and the source of `src/vibepy/**`, `hub/src/vibepy_hub/**`,
`samples/**`, plus `tests/test_app_composition.py`, `tests/test_app_config.py`,
`tests/test_execution_semantics.py`, `tests/test_serve_command.py`,
`tests/test_nicegui_adapter.py`, `tests/test_errors.py`, `tests/test_app_isolation.py`,
`hub/tests/test_runtime.py`, `hub/tests/tests_support.py`. NiceGUI's own
`nicegui/page.py` docstring was read to verify a route-registration claim.

---

## Strengths

- **The declaration genuinely holds no factory.** `src/vibepy/app/model.py:20-42` carries
  `app_id`, `name`, `version`, `config`, `tools`, `pages` and nothing callable. The lifespan
  lives on `AppEntrypoint` (`src/vibepy/app/entrypoint.py:53-58`), which packaging.md and
  ADR-021 name as the composition root. `AppEntrypoint.describe()` (entrypoint.py:60-83)
  reads only declarations and enters no lifespan, and `tests/test_app_isolation.py:11`
  proves discovery leaves `sys.modules` untouched. ADR-021 is satisfied as written.

- **Configuration is validated before anything is acquired.**
  `src/vibepy/app/composition.py:80-83` calls `_validated` *before* `async with lifespan(...)`,
  and `page_runtime_for` delegates to `tool_runtime_for` so there is exactly one validation
  site. `tests/test_app_config.py:81-94` asserts the lifespan was never entered. This is
  ADR-022's central requirement, met precisely.

- **The window is a block, and there is no object for a runtime that is not running.**
  `composition.py:71-101` yields the runtime and nothing else; no lifecycle state, no
  transition errors, and errors.md records `lifecycle.transition_forbidden` /
  `lifecycle.not_running` as retired codes. ADR-020 is honoured to the letter, including the
  deletion of what it superseded.

- **Both hosts own their own window by the mechanism their own library documents.**
  Agent: `Server(lifespan=server_lifespan)` and the runtime read from
  `ctx.lifespan_context` (`adapters/mcp/server.py:85-104`). Web: the window is the ASGI
  application's lifespan (`adapters/nicegui/application.py:43-49`), so a window that refuses
  to open fails uvicorn's startup — and `tests/test_serve_command.py:79-96` proves it as a
  real process with a non-zero exit code. That is the strongest lifecycle test in the repo.

- **Release is correct on both paths, and it is tested at the right level.**
  `tests/test_app_composition.py:145-181` covers the failing-acquisition row and the
  "earlier resource released when a later one fails" row of lifecycle.md's cleanup table,
  through the public `tool_runtime_for` rather than through internals.

- **ToolRuntime owns only generic invocation semantics.** `tool/runtime.py:82-89` resolves,
  builds a fresh `ToolContext` with a fresh `uuid4`, and awaits. No branch on channel, no
  business logic, no serialization. Input/output validation lives in the closure a `Tool`
  builds (runtime.py:47-59), so ToolRuntime carries no per-Tool knowledge.

- **App-scoped state reaches a handler only through ToolContext.** `PageRuntime` holds a
  `ToolInvoker` (`page/runtime.py:21-22`) and `PageContext` carries `tools` alone
  (`page/model.py:25-29`); `DepsT` never enters the Page package. Page/session state stays in
  the NiceGUI builder closure (`samples/todo/src/todo_app/entry.py:80-95`). This matches
  app-model.md's three scopes exactly.

- **`tests/test_execution_semantics.py` is a genuinely good constitutional test.** The
  barrier is reached *through* `ctx.dependencies`, so overlap and resource sharing are proven
  by one event, and each of the four layers is driven the way its library documents. It
  asserts nothing about elapsed time. runtime.md demands exactly this and gets it.

---

## Findings

### Critical

**1. Hub Tool handlers run blocking filesystem, subprocess-tree and metadata work directly on
the event loop.**

`AGENTS.md` (Python conventions): "Blocking calls inside async code are wrapped in
`asyncio.to_thread`." `docs/architecture/runtime.md` (Concurrency) states the consequence in
its own words: "a Tool handler that blocks the event loop serializes every channel in its
process, and that is exactly the case where ToolRuntime's absence of a lock delivers
nothing."

Unwrapped blocking calls inside `async def` handlers and inside an async lifespan:

| Site | Blocking work |
| --- | --- |
| `hub/src/vibepy_hub/entry.py:38` | `config.root.mkdir(parents=True, exist_ok=True)` inside `hub_lifespan` |
| `hub/src/vibepy_hub/tools/runtime.py:28,44` | `installed_facts` (`is_dir`/`is_file`/`read_text`), `read_state` |
| `hub/src/vibepy_hub/tools/configuration.py:27,40,42` | `installed_facts`, `read_state`, `write_state` (`mkdir` + `write_text` + two `os.chmod`) |
| `hub/src/vibepy_hub/tools/packages.py:30,42,52,11,22` | `read_state`, `write_state`, and `candidates()` — `iterdir` plus a `read_text` + `tomllib.loads` per subfolder of every registered source |
| `hub/src/vibepy_hub/tools/installation.py:102,115,159` | `shutil.rmtree` over a whole virtual environment (thousands of files) |
| `hub/src/vibepy_hub/tools/installation.py:58,61` | `envs.iterdir()` and `discover_apps(path=[metadata])` — `importlib.metadata.distributions()` walks an environment's `dist-info` — **once per installed App, in a loop** |
| `hub/src/vibepy_hub/internals/processes.py:155` | `free_port()` binds a synchronous socket |

Why it matters: the Hub is an App like any other (ADR-024), so its Tools run on the one loop
that also serves its channel. `list_apps` and `remove_app` are the two operations a Hub UI
calls most, and both stall every other in-flight invocation for the duration of a filesystem
walk or a recursive delete. M11 puts a NiceGUI UI on that same loop, where NiceGUI's own
documentation (quoted in runtime.md) says blocking "freezes the application for every user".

This is not an oversight of an unknown rule: `hub/src/vibepy_hub/internals/installer.py:68`
wraps `_is_runnable` in `asyncio.to_thread`, and `hub/tests/tests_support.py:27` explains that
`urlopen` is threaded "so it runs in a thread rather than on the loop the test shares with the
Hub". The rule is understood; it is applied in two places and skipped in a dozen.

Fix: wrap the synchronous helpers at their call sites in the Tool handlers —
`await asyncio.to_thread(read_state, deps.root)`, `await asyncio.to_thread(write_state, ...)`,
`await asyncio.to_thread(installed_facts, ...)`, `await asyncio.to_thread(candidates, source)`,
`await asyncio.to_thread(shutil.rmtree, env, ignore_errors=True)`,
`await asyncio.to_thread(discover_apps, path=[metadata])`, and
`await asyncio.to_thread(free_port)`. Keep the helpers themselves synchronous; the threading
belongs at the async boundary, which is where `installer.py` already puts it.

### Important

**2. `src/vibepy/serve.py:33` — `AppNotDeclared(Exception)` is a framework exception outside
the framework's exception hierarchy, with no code and a plain-text stderr contract.**

`AGENTS.md`: "Framework exceptions derive from a single base class. Exception types are the
contract, not message strings." `docs/architecture/errors.md`: "Every framework exception
therefore also carries a code." The class derives from `Exception`, declares no `code`, has no
row in errors.md's code table and no entry in `_CATEGORIES`.

It also escapes the repo's own guard. `tests/test_errors.py:32-39` walks
`VibepyError.__subclasses__()` recursively, and its docstring says a milestone "must not be
able to skip the rule by not editing this file" — but a class that does not inherit
`VibepyError` is invisible to that walk. The catalogue test gives false assurance here.

The consequence is visible in one function: `serve.py:97` writes `f"{absent}\n"` — a bare
English sentence — while `serve.py:100-101` writes `{"code": ..., "message": ...}` for the two
neighbouring failures. A caller parsing the command's stderr sees two shapes for the same
class of failure, which is precisely what ADR-019 exists to prevent.

Fix: make it `class AppNotDeclaredError(VibepyError)` with code `package.app_not_declared`,
category `declaration`, an `app_name` detail, a row in errors.md's table and a row in
`_CATEGORIES`; then fold `serve.py:96-98` into the JSON branch below it.

**3. `src/vibepy/serve.py:92` — `serve.config_invalid` is a hand-written code string belonging
to no exception and no table.**

errors.md: "A milestone that adds an exception declares its code on the class and maps its
category in `vibepy/errors.py`", and "A code is stable. The same code always means the same
failure". This code is emitted as a literal inside a `sys.stderr.write`, appears nowhere in
`errors.py` or errors.md, and is unreachable by the catalogue test. It is also inconsistent
with `config.invalid`, the code the App's own window raises for the adjacent failure — an
agent now sees two different codes for "the configuration was wrong", one of which is not
in the published table.

Fix: give it a real exception and a table row, or reuse an existing declared code; either way
it must be reachable from `errors.py` rather than typed inline.

**4. `hub/src/vibepy_hub/internals/processes.py:198-201` — `aclose()` leaks children if it is
cancelled or if one `stop()` raises.**

`hub/src/vibepy_hub/entry.py:35-36` promises "a window that closes leaves no child behind" and
cites ADR-018. lifecycle.md's cleanup table makes release the framework's whole cleanup story.

`stop()` sends `terminate()` synchronously and then *awaits* `wait_for(process.wait())`.
`aclose()` awaits `stop()` once per child, sequentially. If the window is closed by
cancellation — the normal shutdown path for an anyio/uvicorn host — the first `await` inside
the first `stop()` raises `CancelledError` and children 2..n never receive `terminate()` at
all. The same is true for any unexpected exception from one child's stop.

`hub/tests/test_runtime.py:78-94` covers only the single-child, non-cancelled case, so the
gap is untested.

Fix: in `aclose()`, send `terminate()` to every child first, then await their exits (e.g.
`asyncio.gather(..., return_exceptions=True)` inside a
`contextlib.suppress`/shielded block), so no child's release depends on a previous child's
await completing.

**5. `src/vibepy/adapters/nicegui/web.py:1-6` and `docs/architecture/adapters.md` claim routes
are "left with" the window; they are not.**

web.py's module docstring: "Registration therefore happens inside that window, and a builder
holds its runtime for exactly as long as the window lasts." application.py:39-41 repeats it.
adapters.md repeats it a third time.

`ui.page` registers into `nicegui.core.app.router`, which is process-global — NiceGUI's own
docstring (`nicegui/page.py`) says "The page route is determined by the `path` argument and
registered globally". `register_pages` adds routes and nothing removes them when the window
closes. After the `async with` in `application.py:45-47` exits, the route table still holds
builders closed over a `PageRuntime` whose `DepsT` resource has been released; a request then
runs a Page against a closed resource.

The repository already knows this: `tests/test_nicegui_adapter.py:3-6` says the NiceGUI
fixture "is what resets NiceGUI's process-global route table around each test". So the
cleanup exists only in the test harness, and the architecture document states it as a
property of the framework.

In production this is masked by ADR-017 (one process per channel, one window per process), but
`build_web_app` and `register_pages` are public API with no stated once-per-process
restriction, and app-model.md's "Two windows over one definition are isolated by default" is
false for the Web channel inside one process.

Fix: state the real boundary rather than an unearned one. Either say plainly in adapters.md
and web.py that route registration is process-global and `build_web_app` may be called once
per process (and enforce or document that), or unregister the routes on window close and make
the docstring true.

**6. `hub/src/vibepy_hub/tools/runtime.py:47-53` — the Hub discards the `config.invalid` code
and field list that ADR-022 exists to produce.**

ADR-022's stated consequence: "a configuration failure carries a code and a category like
every other framework failure", and `AppConfigInvalidError` names *every* field that failed
(`errors.py:139-146`). At the one boundary where a host starts an App, all of that is thrown
away: `processes.start` redirects only stdin (`processes.py:156-165`), so the child's stderr —
which carries the framework's own message — is never captured, and the agent receives
`hub.start_failed` with the text `"the App exited with 3"`
(`processes.py:111`, `tools/runtime.py:53`).

`hub/tests/test_runtime.py:97-115` asserts exactly that degraded outcome, so the test locks in
the loss rather than catching it.

Worse, the Hub already holds everything needed to answer properly *before* starting:
`is_configured(facts, held)` (`internals/configuration.py:54-57`) is computed for `list_apps`
but never consulted by `start_app`.

Fix: (a) call `is_configured` in `start_app` and return a `hub.not_configured` diagnostic
naming the missing fields before spawning anything; and (b) capture the child's stderr
(`stderr=asyncio.subprocess.PIPE`) so `StartFailed` can carry the framework's `code` and
`message` instead of an exit number.

### Minor

**7. `src/vibepy/serve.py:37-44` — `_is_entrypoint` is a cast in disguise.**
The `TypeGuard[AppEntrypoint[object, BaseModel]]` widens an `AppEntrypoint[TodoStore,
TodoConfig]` to a pair no `isinstance` check can verify: `Tool[DepsT]` is invariant (its handler
takes `ToolContext[DepsT]` contravariantly), and `Lifespan[object, BaseModel]` claims the
lifespan accepts a bare `BaseModel`. `AGENTS.md` bars `Any` and `cast` from the public API;
a `TypeGuard` asserting an unverifiable type argument is the same operation under another
name. The docstring reasons about why it is contained (the command never constructs a
definition or calls the lifespan itself), and the containment does hold today — but the
soundness rests on `build_web_app` passing the two values together and on nothing else ever
touching them. Worth an explicit note in the docstring that the pair must stay opaque, or a
narrower helper that keeps the two values coupled without naming `object`.

**8. `src/vibepy/app/composition.py:65` — configuration validation ignores undeclared fields.**
`model_validate` with Pydantic's default `extra="ignore"` means a misspelled configuration key
validates cleanly and the App runs on a default. Combined with `configure_app`, which by design
"does not validate" (`tools/configuration.py:20-24`), a typo'd field name is reported by
nothing anywhere in the chain. ADR-022 does not require strictness, so this is a gap rather
than a violation — but "what an App requires of its host" is only half-checked while the
declaration could support `model_config = {"extra": "forbid"}` or an explicit unknown-field
report.

**9. `src/vibepy/describe.py:16` and `src/vibepy/serve.py:27` declare loggers they never use,
and the window lifecycle logs nothing at all.**
Across the whole framework only three `logger.` calls exist (`app/package.py:58`,
`adapters/mcp/server.py:110,114`). Opening and closing a window — the event an operator most
needs to see when `start_app` reports "the App did not answer" — emits nothing. Not a stated
invariant, but it is the observability the Hub's own failure path depends on. Either use the
declared loggers (a `debug` on window open/close in `composition.py`) or drop the two unused
declarations.

**10. `src/vibepy/__init__.py` omits `tool_registry_for` and `page_registry_for`, which
`src/vibepy/app/__init__.py:31,33` exports.**
`AGENTS.md`: "The public API is a product." The MCP adapter imports `tool_registry_for` from
`vibepy.app.composition` (`adapters/mcp/server.py:25`), so it is used framework-internally,
but a caller reading `vibepy.__all__` sees an inconsistent surface between the two `__init__`
files. Decide whether they are public and say so in one place.

**11. `python -m vibepy.serve <page-less app>` opens a Web window for an App that has no Web
channel.**
ADR-017: "An App declaring no Pages has no Web channel and therefore no runtime for the Hub to
start." The Hub enforces it (`tools/runtime.py:34-39`, `hub.no_web_channel`); the framework
command does not, so serving `notes-app` acquires that App's resource and serves zero routes.
This mirrors packaging.md's stated division ("the framework states the contract, the host
implements it"), so it is defensible — but nothing states it for *this* contract, and the cost
of a check in `_serve` is one line.

**12. `hub/src/vibepy_hub/internals/processes.py:166` — `if process.stdin is not None` is
unreachable.** `create_subprocess_exec` was called with `stdin=asyncio.subprocess.PIPE`, so
`stdin` is always present. `AGENTS.md`: "No error handling for situations that do not
actually occur" (user-level rule; the repository's own preference for explicit over defensive
code points the same way). Silently skipping the write would also hang the child forever in
`sys.stdin.read()`, so a failure here would be invisible rather than reported.

---

## Cross-boundary assumptions

Every point where my conclusion depended on another module, and what I did about it:

| Assumption | Verified? | Where I checked |
| --- | --- | --- |
| The MCP adapter enters the window through the SDK rather than owning a lifecycle | Yes | `src/vibepy/adapters/mcp/server.py:85-90,122-127` — `Server(lifespan=server_lifespan)`, runtime read from `ctx.lifespan_context` at line 104 |
| The Web adapter registers routes inside the window and holds no runtime of its own | Partly — see finding 5 | `adapters/nicegui/application.py:43-49`, `adapters/nicegui/web.py:34-57`, and NiceGUI's `nicegui/page.py` docstring ("registered globally") |
| `PageRuntime`'s `ToolInvoker` is really `ToolRuntime`, so no second invocation path exists | Yes | `page/model.py:10-22` (Protocol) against `tool/runtime.py:82` (signature matches; positional-only Protocol is satisfied by named params) |
| No Page type carries `DepsT`, so app-scoped state cannot leak through the Page model | Yes | `page/model.py` and `page/runtime.py` are entirely free of `DepsT`; `page_runtime_for` (composition.py:99-101) hands only the invoker across |
| `uvicorn.run` actually exits non-zero when the lifespan refuses to open | Yes, empirically | `tests/test_serve_command.py:79-96` runs the real process and asserts `returncode != 0` and `config.invalid` on stderr |
| The Hub, not the framework, owns package installation lifecycle (ADR-006) | Yes | `hub/src/vibepy_hub/tools/installation.py` vs `tools/runtime.py` are separate modules and separate Tools; the framework has no install concept anywhere in `src/vibepy` |
| The Hub's lifespan releases its children on both paths | Only on the uncancelled path — see finding 4 | `hub/src/vibepy_hub/entry.py:40-43` (`try/finally`) against `internals/processes.py:181-201` |
| `tests/test_errors.py` would catch a framework exception added without a code | No — it walks `VibepyError.__subclasses__()` only | `tests/test_errors.py:32-39` against `src/vibepy/serve.py:33` |
| Configuration reaches the child without a file, env var or argv | Yes | `processes.py:146-168` writes JSON to stdin; `serve.py:90` reads it back through `TypeAdapter(dict[str, object])` |
| `AppDefinition` holds nothing callable | Yes | `app/model.py:37-42`, all six fields are data; the lifespan is on `AppEntrypoint` |

## Rule concerns

None. Every finding above is measured against `AGENTS.md`, an ADR, or a
`docs/architecture/*` statement, and I found no repository rule I would argue against. The one
place where I would flag the *documents* rather than the code is finding 5: three documents
state a guarantee (routes leave with the window) that the underlying library cannot provide,
and the honest fix is to change the documents, not only the code.

## Assessment

The core of this axis is in very good shape. The separation ADR-020 and ADR-021 demand is real
rather than nominal — there is no runtime object, no lifecycle state, no factory in the
declaration, and the configuration gate sits at exactly the one point ADR-022 specifies, with a
test that proves the lifespan was never entered. `ToolRuntime` is as thin as runtime.md asks,
and `tests/test_execution_semantics.py` is a genuinely strong constitutional test.

The weaknesses are all at the edges where the framework meets a host. One is systematic and
should be fixed before M11 puts a UI on the Hub's loop: async Tool handlers do synchronous
filesystem and process-tree work, against a convention `AGENTS.md` states flatly and that the
same codebase applies correctly two files away. Two more are error-model regressions inside
`serve.py`, where an exception and a code slipped outside the hierarchy that ADR-019 built and
that `tests/test_errors.py` cannot see. The remaining two Important findings are guarantees
stated more strongly in prose than the code delivers — child-process release under
cancellation, and route lifetime — both of which are currently masked by the one-process-per-
channel deployment ADR-017 mandates, and neither of which should be left resting on that.
