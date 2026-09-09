# Axis 4 review — Packaging, the Hub, and the sample apps

HEAD 05d602750328f723354823b8fb97c6bf5862ba03, branch main, clean tree.

Baseline read: `AGENTS.md` in full; `docs/architecture.md`; `docs/architecture/packaging.md`,
`app-model.md`, `errors.md`, `authoring.md`; all 24 ADR titles plus ADR-006, 010, 017, 021, 023,
024 in full; `docs/roadmap.md` M10/M11/M17.

Code read in full: `src/vibepy/app/package.py`, `src/vibepy/app/entrypoint.py`,
`src/vibepy/describe.py`, `src/vibepy/serve.py`, `src/vibepy/__init__.py`,
`src/vibepy/app/composition.py`, `src/vibepy/tool/runtime.py`, `src/vibepy/page/runtime.py`,
`src/vibepy/adapters/nicegui/application.py`; the root, hub, todo and notes `pyproject.toml`;
`hub/src/vibepy_hub/**` in full; `samples/todo` and `samples/notes` in full;
`hub/tests/**`; `tests/test_app_isolation.py`, `tests/test_app_package.py`,
`tests/test_todo_distribution.py`.

---

## Strengths

- **The entry-point declaration is exactly ADR-023.** `discover_apps`
  (`src/vibepy/app/package.py:39`) goes through `distributions()` and
  `dist.entry_points.select(group=...)` and never touches `EntryPoint.load`. `describe_app` is the
  only loader and it is confined to the App's own interpreter via `python -m vibepy.describe`.
  `tests/test_app_isolation.py:11` proves `sys.modules` is untouched. I grepped `src/vibepy/` for
  `vibepy_hub` and `hub` — no hits. The distribution boundary in `AGENTS.md` /
  ADR-024 ("the framework never depends on the Hub") holds in the shipped code.

- **The Hub really is an App.** `hub/src/vibepy_hub/entry.py` declares `HubConfig`, a lifespan
  yielding `HubDeps`, and `HUB_TOOLS`; `hub/pyproject.toml:11` declares it in `vibepy.apps` like
  any other package. Every Hub test drives it through `tool_runtime_for` + `ToolRuntime.invoke`
  (`hub/tests/tests_support.py:17`), so the tests verify the public contract, not internals — the
  `AGENTS.md` test rule, honoured. There is no privileged back door: nothing in the Hub reaches a
  framework private, and it never imports a third-party App.

- **The internals/Tools split matches ADR-024.** `installer`, `processes`, `projects`, `state`,
  `configuration` are behind `internals/` and reachable only through a Tool handler's
  `ToolContext`, which is precisely what ADR-024's first consequence asks for. The module
  docstrings cite the document that justifies each choice.

- **`processes.py` is careful where it matters.** `child_environment()` strips the variables that
  describe the Hub's own process — that is a genuine isolation guarantee that a naive launcher
  would have lost. `_wait_until_answering` waits for an HTTP *answer* rather than a TCP accept,
  and its docstring gives the right reason: the ASGI lifespan is the App's window
  (`src/vibepy/adapters/nicegui/application.py:44`), so an accepted socket does not prove the
  window opened. I verified that guarantee on the other side: `composition._validated` runs before
  `lifespan(...)` is entered, so bad config really does fail startup. `aclose()` on the lifespan's
  `finally` and `hub/tests/test_runtime.py:78` close the leaked-child question honestly.

- **`purelib()` is asked of the child interpreter** rather than derived from the Hub's own
  `sysconfig`. That is the correct answer and the docstring explains why.

- **Cross-platform basics are handled** where they were thought about: `interpreter()` branches on
  `sys.platform`, `write_state` documents what `os.chmod` does and does not mean on Windows, and
  `hub/tests/test_configuration.py:90` skips the POSIX-bit assertion instead of asserting a lie.

- **`samples/notes` earns its place.** It is the ADR-017 "App with no Web channel" case and the
  ADR-022 "secret declared by type" case in one file, and `secret_fields()` reads it back out of
  the projected JSON Schema without importing it — the packaging invariant demonstrated end to
  end.

---

## Findings

### Critical

**F1. `remove_app` deletes any directory the Hub's user can delete —
`hub/src/vibepy_hub/tools/installation.py:159`**

```python
shutil.rmtree(environment(deps.root, payload.app_name), ignore_errors=True)
```

`app_name` arrives straight from `AppName`, a Tool input model with no constraint, and
`environment()` (`internals/installer.py:37`) is `root / "envs" / app_name`. Nothing checks that
`app_name` is a single path segment, and unlike `configure_app` / `start_app` there is no
`installed_facts` gate first — `remove_app` acts unconditionally.

I confirmed the behaviour: `shutil.rmtree(root/"envs"/"../../victim", ignore_errors=True)` removes
`victim`. So `remove_app {"app_name": "../../.ssh"}` — or any relative or absolute-ish traversal —
destroys data outside the Hub root.

Why this is worse here than in an ordinary web app: `AGENTS.md` makes Tools "the canonical public
backend operations of an App", and ADR-024 makes the Hub's Tools "its whole public surface". The
Agent channel exposes every Tool to an MCP client by construction, so this is a
model-controlled string reaching `rmtree`. `docs/architecture/app-model.md` states that "An App
declares what it requires of its host as a type" — the type here declares nothing.

The same unvalidated name reaches the filesystem on the write path:
`installation.py:97` builds the env from `payload.app_name` after
`_candidate_folder` matched it against `row.name` (line 46), and `row.name` is the `[project] name`
string read out of a *registered folder's* `pyproject.toml` (`internals/projects.py:39`). A source
folder containing `name = "../../x"` therefore causes `uv venv` — and, on failure,
`shutil.rmtree` (`installation.py:102`, `:115`) — to run outside the Hub root.

Fix: constrain the name at the model boundary, e.g. `AppName.app_name` / `ConfigureRequest.app_name`
/ `StartRequest.app_name` as a `constr`-style single segment, and make `environment()` refuse a
name whose resolved path is not under `root / "envs"`. Given the Hub is the control plane, the
check belongs in `environment()` so no future caller can forget it.

---

### Important

**F2. Blocking filesystem I/O runs on the event loop throughout the Hub's async handlers**

`AGENTS.md`, Python conventions: "Blocking calls inside async code are wrapped in
`asyncio.to_thread`." The Hub knows the rule — `internals/installer.py:68` wraps `_is_runnable`
in `asyncio.to_thread` — and then breaks it everywhere else:

| Async caller | Blocking call |
| --- | --- |
| `entry.py:38` `hub_lifespan` | `config.root.mkdir(...)` |
| `tools/installation.py:44,57` | `read_state` → `path.read_text` (`internals/state.py:37`) |
| `tools/installation.py:45,142` | `candidates(source)` → `iterdir` + `read_text` (`projects.py:67,53`) |
| `tools/installation.py:58,59` | `envs.iterdir()`, `read_facts` → `read_text` |
| `tools/installation.py:102,115,159` | `shutil.rmtree` |
| `tools/installation.py:125` | `write_facts` → `write_text` |
| `tools/installation.py:161` | `write_state` → `write_text` + two `os.chmod` |
| `tools/configuration.py:28,40,42` | `installed_facts`, `read_state`, `write_state` |
| `tools/packages.py:12,31,42,53` | `read_state`, `is_dir`, `write_state`, `candidates` |
| `tools/runtime.py:29,44` | `installed_facts`, `read_state` |

`ToolRuntime` explicitly permits concurrent invocations ("Concurrent invocations are permitted.
Nothing here serializes them" — `src/vibepy/tool/runtime.py:72`), and M11 will put a NiceGUI Page
on this same loop, where NiceGUI is documented single-worker. `list_apps` walks every environment
and every registered source synchronously; on a slow or network-mounted root it stalls every other
Page and every concurrent agent call in the process.

Fix: push the filesystem work behind `asyncio.to_thread` at the internals boundary — one
`await asyncio.to_thread(read_state, root)` style wrapper per internal, rather than sprinkling it
at 20 call sites.

**F3. A child process is leaked if writing configuration to its stdin fails —
`hub/src/vibepy_hub/internals/processes.py:166-169`**

```python
if process.stdin is not None:
    process.stdin.write(json.dumps(dict(config)).encode())
    await process.stdin.drain()
    process.stdin.close()
```

The `try/except StartFailed` that kills the child starts on the *next* line (`:170`). If the child
dies before reading stdin — a broken installation, a missing `vibepy.serve`, a config large enough
to fill the pipe before the child exits — `drain()` raises `BrokenPipeError` /
`ConnectionResetError`. That is not `StartFailed`, so it escapes `start_app` uncaught, the process
is never killed and never awaited, and it is never entered into `self._running`, so `aclose()`
cannot reach it either. The module docstring's own premise — "a child is this window's resource,
released when the window closes" — is violated on exactly this path.

It also defeats the diagnostic contract: `start_app` (`tools/runtime.py:52`) only catches
`StartFailed`, so the caller gets an `app.unhandled` instead of `hub.start_failed`.

Fix: move the stdin write inside the same `try`, and convert `OSError` there into `StartFailed`.

**F4. A half-installed environment is left behind, and the diagnostic is lost —
`hub/src/vibepy_hub/tools/installation.py:111`**

```python
    except InstallFailed as failure:
        shutil.rmtree(env, ignore_errors=True)
        ...
    metadata = await purelib(env)          # <- outside the try
```

`purelib()` calls `_run()` (`installer.py:55`), which raises `InstallFailed` when the child
interpreter cannot answer. Because line 111 sits outside the `except`, that failure escapes the
handler as an unhandled exception, leaving the created environment on disk with no facts file. The
next `list_apps` then sees an env directory with no facts, takes the `await purelib(env)` branch
(`installation.py:60`), and raises `InstallFailed` out of `list_apps` too — so one bad install
makes the Hub's *listing* Tool throw. Every other failure in this module is reported as a
`Diagnostic`; this one is not.

Fix: bring `purelib(env)`, `write_facts` and the `discover_apps` read inside the same `try`, and
make `_installed` tolerate an environment it cannot interrogate (a `hub.*` diagnostic on the row,
which `AppRow.diagnostic` already exists for).

**F5. `list_apps` and `_listing` raise on a source folder that has since disappeared —
`hub/src/vibepy_hub/internals/projects.py:67`**

`candidates()` calls `source.iterdir()` with no guard. `register_package_source` checks `is_dir()`
once at registration (`tools/packages.py:31`) and then persists the path in `state.json`, which
outlives the window (`hub/tests/test_package_sources.py:56` proves persistence). A removed or
unmounted source folder therefore makes `list_apps`, `register_package_source`, `remove_package_source`
and `install_app` all raise `FileNotFoundError`, including `remove_package_source` — the one Tool
a user would call to fix the problem.

The Hub already has the right vocabulary for this: `hub.source_unreadable`. Fix: have `candidates()`
return `()` for an unreadable source and let the caller attach the diagnostic.

**F6. `declared_name` is paired positionally with `describe`'s output —
`hub/src/vibepy_hub/tools/installation.py:113,124`**

```python
found = next(iter(described), None)
...
facts = found.model_copy(update={"purelib": metadata, "declared_name": declared[0].app_name})
```

`described` comes from the child's `python -m vibepy.describe`, which iterates the child's
`discover_apps()` over `sys.path`. `declared` comes from the Hub's `discover_apps(path=[purelib])`.
Both sort by `(app_name, distribution)`, which is what makes index 0 line up *today* — but they
enumerate different search paths, and nothing in `describe.py` or `AppDescription` carries the
declared name that would let the two be joined by identity. `declared_name` is what `start_app`
passes to `vibepy.serve` (`tools/runtime.py:47`), so a mispairing silently starts a different App
than the one whose facts were recorded.

Separately, `next(iter(described), None)` silently drops every App after the first. Both
`discover_apps` and `vibepy.describe` are plural by design (`describe.py:22` writes a JSON array),
so a distribution declaring two Apps installs as one with no diagnostic.

Fix: put the declared entry-point name into `AppDescription` (or have `installer.describe` return
it) and join on it; report a folder that declares more than one App explicitly rather than
truncating.

**F7. `HeldConfig` cannot be fed back into `configure_app` without destroying the secret —
`hub/src/vibepy_hub/tools/configuration.py:41,47`**

`configure_app` merges `{**stored, **payload.values}` and returns `masked(kept, secrets)`, where a
secret reads as the literal string `"set"` (`internals/configuration.py:48`). There is no read-only
Tool for held configuration, so the only way any client — the M11 Page, or an agent — learns the
current values is this Tool's own output. The natural round trip (read the form, edit one field,
send it back) writes `"set"` over the real secret, and nothing detects it: the Hub deliberately
does not validate (`configuration.py:22`), so the corruption surfaces later as a failed start.

This is a Tool-contract problem, not an implementation detail: `AGENTS.md` says the public API is a
product, and here the output type is not safe as the input type.

Fix: either drop masked secret fields from `values` entirely rather than substituting a sentinel,
or reject `SET` as an incoming value for a declared secret field.

**F8. `install_app` accepts two names for one App but `list_apps` only knows one —
`hub/src/vibepy_hub/tools/installation.py:46` vs `:143`**

`_candidate_folder` matches `app_name in {row.name, row.folder.name}` — either the distribution
name or the folder name. The environment is then created under whichever string the caller used
(`:97`). `list_apps`, however, keys available rows by `row.folder.name` only (`:143`). Install
`vibepy-todo` and the listing shows two Apps: `vibepy-todo` (installed) and `todo` (available), the
same folder twice. `remove_app`/`start_app`/`configure_app` then only work under the first name.

`docs/architecture/packaging.md` is clear that "the name on the left is the App's name inside its
distribution" and `hub/tests/test_installation.py:51` makes the point that a folder's name is not a
declaration — but the Hub accepts three different naming schemes and reconciles none of them.

Fix: pick one identity for a candidate (folder name, per the tests) and match on that alone.

**F9. `AppRow.state` and `RunningApp.state` are unconstrained `str`**

`hub/src/vibepy_hub/models.py:64,71,117`. The docstring justifies it as "a string because an output
model round-trips through JSON" — but `Literal["available", "installed", "running"]` round-trips
through JSON just as well, and Pydantic projects it into the JSON Schema as an `enum`. Because
`AppDefinition` publishes `output_model.model_json_schema()` through `AppEntrypoint.describe`
(`src/vibepy/app/entrypoint.py:72`) and the MCP adapter projects it to the agent, the current
choice means an agent reading the Hub's tool schema learns nothing about the state set it must
branch on. `AGENTS.md` asks for typed unions with `assert_never` at the branch; a bare `str` makes
that impossible for any consumer, including M11's Page.

Fix: `Literal[...]` (or a `StrEnum`) for both fields.

---

### Minor

**F10. `TODO_CONFIG` is test scaffolding shipped inside a sample distribution —
`samples/todo/src/todo_app/entry.py:131`**

```python
TODO_CONFIG: dict[str, object] = {"db_path": "/tmp/vibepy-todo.db"}
```

Its only consumers are `tests/test_nicegui_adapter.py` and `tests/test_dual_channel.py`. It is a
POSIX-only literal, and it is a `str` where `AGENTS.md` says "Filesystem paths are `pathlib.Path`,
never strings. The framework runs on macOS and Windows." Nothing opens the file, so the tests pass
on Windows by accident. It also teaches the wrong shape to an app author reading the sample: a real
App's configuration comes from the Hub over stdin, not from a module constant. Move it into the
tests (a `tmp_path`-derived fixture) and let the sample carry only its declaration.

**F11. `TodoStore` declares `db_path` and never honours it —
`samples/todo/src/todo_app/entry.py:49-56`**

The store takes the path, assigns it, and keeps a `list[Todo]` in memory. The module docstring is
honest about this, but `samples/todo` is the reference for how an app author wires configuration
through a lifespan, and it demonstrates the wiring without the payoff — a reader cannot tell
whether `db_path` is meant to be used or is decorative. Either use it (a JSON file is enough) or
declare `NoConfig` and let `samples/notes` carry the configuration story.

**F12. The App version is stated twice, and the two disagree for todo**

`samples/todo/pyproject.toml:4` says `version = "0.1.0"`; `entry.py:101` declares
`version="0.0.0"`, and `hub/tests/test_installation.py:32` asserts `"0.0.0"`. So the Hub reports a
version the distribution does not have. `samples/notes` and `hub` happen to agree
(`entry.py:49` / `hub/pyproject.toml:3`), but by coincidence rather than construction. `AppRef`
already carries `distribution_version` from metadata; the authoring docs do not say which of the
two an App's `version` is meant to be. Worth settling — at minimum, make todo's two agree.

**F13. `projects.py` re-declares the entry-point group — `hub/src/vibepy_hub/internals/projects.py:17`**

```python
APP_GROUP = "vibepy.apps"
```

`vibepy.APP_GROUP` is exported from the framework's top level precisely so this string exists once
(`src/vibepy/app/package.py:20`, re-exported at `src/vibepy/__init__.py:4`). "The same fact is not
stated in two places" is stated for documents, but the reasoning applies here and the framework has
already published the constant. Import it.

**F14. `install()` pins no interpreter — `hub/src/vibepy_hub/internals/installer.py:82`**

`uv venv <env>` takes whatever Python uv discovers, which need not satisfy the App's
`requires-python`. `uv pip install` will then fail with a `hub.install_failed` diagnostic, so this
is not a correctness hole — but the failure is late and its message is uv's, not the Hub's. Passing
`--python` (the Hub's own `sys.executable`, or the App's declared floor) would make the environment
predictable. `_run` also passes no `env=`, so `uv` inherits the Hub's `VIRTUAL_ENV`; unlike
`Processes.start`, which is careful about exactly this.

**F15. No timeout on installation subprocesses — `hub/src/vibepy_hub/internals/installer.py:70-73`**

`await process.communicate()` has no deadline. `Processes` has `STOP_TIMEOUT` and `READY_TIMEOUT`;
`_run` has none, so a hung `uv pip install` hangs the Tool call, and (per F2) the whole loop, with
no way to cancel. Also, `failure.output` is passed whole into `Diagnostic.details["output"]`
(`installation.py:108`) — an unbounded uv log delivered to an agent as a tool result. Cap both.

**F16. `remove_app` calls the `list_apps` handler directly — `hub/src/vibepy_hub/tools/installation.py:170`**

`return await list_apps(ctx, Empty())`. It works and the output is revalidated by `remove_app`'s own
`output_model`, but it makes a Tool handler double as an internal service, which is the shape
`AGENTS.md` warns off ("Internal helpers, services, policies, and repositories do not need to be
Tools" — read the other way, a Tool should not be the internal). Extract the listing into
`internals/` and have both Tools call it.

**F17. `installed_facts` conflates "not installed" with "facts unreadable" —
`hub/src/vibepy_hub/internals/installer.py:140`**

An env directory whose `.vibepy-facts.json` is missing or corrupt (`read_facts` logs and returns
`None`, `:126`) reports `hub.not_installed` from `configure_app` and `start_app`, while `list_apps`
still shows the row as installed. Two Tools disagree about the same App. A distinct code —
`hub.facts_unreadable` — would let a caller act (reinstall) instead of being told a falsehood.

**F18. `AppFacts.purelib` stores an absolute path across windows —
`hub/src/vibepy_hub/models.py:50`, used at `tools/installation.py:60`**

The facts file lives inside the environment it describes, but records an absolute path to that
environment's `site-packages`. Move the Hub root (or restore it from a backup) and `list_apps` reads
distributions from a path that no longer exists — `distributions(path=...)` returns empty rather
than raising, so every App silently gains a `hub.declaration_missing` diagnostic. Deriving it, or
validating it against `env`, would fail loudly instead.

**F19. Nothing imports from `vibepy` itself.** The Hub and both samples import from `vibepy.app`,
`vibepy.tool`, `vibepy.page`; `hub/tests/tests_support.py:8` reaches `vibepy.app.composition`. The
84-line flat re-export in `src/vibepy/__init__.py` is therefore unexercised by the only three
consumers in the repo. `AGENTS.md` says the public API is a product and must stay backward
compatible — but there are currently two supported import surfaces and no document saying which one
an app author should use. `docs/architecture/authoring.md` does not settle it. Worth deciding
before M12/M18, when a coding agent will have to pick one from the docs.

**F20. The framework distribution's dev group names the Hub — `pyproject.toml:26-28,38`**

`vibepy-hub` is a dev dependency of the root project, which is also the `vibepy-framework`
distribution. Dependency groups are not published in wheel metadata, so no installed App gains a
control plane and the ADR-024 boundary is intact at runtime. Still, the framework's own project
file names the Hub, which is the one direction ADR-024 says never happens. A workspace-level test
project (rather than the framework project) would keep the file honest. Flagging as a
documentation/structure point, not a defect.

---

## Cross-boundary assumptions

Every place I expected another module to hold up a guarantee, and what I did about it:

1. **"A window validates configuration before it acquires anything"** — the Hub's whole
   `start_app` story (`tools/runtime.py`, and `hub/tests/test_runtime.py:97`) depends on a
   rejected configuration producing a child that exits rather than a server that answers.
   **Verified** in `src/vibepy/app/composition.py:81` (`_validated` runs before
   `async with lifespan(...)`) and `src/vibepy/adapters/nicegui/application.py:44-49` (the window
   *is* the FastAPI lifespan, so a refusal is `lifespan.startup.failed`). Holds.

2. **"Reading what an environment offers imports nothing"** — the Hub calls
   `discover_apps(path=[purelib])` on an environment holding a third-party App.
   **Verified** in `src/vibepy/app/package.py:46-57`: only `distributions()` and
   `entry_points.select`; `EntryPoint.load` appears solely in `describe_app` (`:71`), which the
   Hub never calls — I grepped `hub/src` for `describe_app` and got no hits; the Hub instead shells
   out via `internals/installer.py:101`. `tests/test_app_isolation.py:11` asserts the `sys.modules`
   consequence. Holds.

3. **"No published framework operation imports an App into its caller's process"** — I did not take
   this on trust from `packaging.md`. **Verified** by reading every `.load()` / import site:
   `package.describe_app` and `serve._entrypoint` (`src/vibepy/serve.py:55`) are the only two, and
   both are module-`main` paths run under the App's own interpreter. Holds.

4. **"The framework never depends on the Hub"** — **Verified** by grepping `src/vibepy/` for
   `vibepy_hub` and `hub`: no hits. Only the dev dependency group names it (F20).

5. **Tool output revalidation and `Path` fields** — `SourceListing.sources: list[Path]` and
   `AppFacts.purelib: Path | None` must survive `ToolRuntime`'s dump-and-revalidate.
   **Verified** in `src/vibepy/tool/runtime.py:54-57`: `model_dump(by_alias=True)` in Python mode
   yields `Path` objects and `model_validate` accepts them. Holds in-process. I did **not** verify
   the MCP JSON projection of these `Path` fields — that is `src/vibepy/adapters/mcp/projection.py`,
   Axis 3's ground, and no Hub test covers a `Path`-bearing Hub Tool over the Agent channel. Worth
   one cross-axis check.

6. **`ToolRuntime` permits concurrent invocations** — this is what makes F2 (blocking I/O) matter
   rather than being theoretical. **Verified** at `src/vibepy/tool/runtime.py:72` ("Concurrent
   invocations are permitted. Nothing here serializes them").

7. **`AppDescription` carries no declared entry-point name** — F6 depends on this being genuinely
   absent rather than my having missed it. **Verified** by reading
   `src/vibepy/app/entrypoint.py:37-50` in full: `app_id`, `name`, `version`, `config_schema`,
   `tools`, `pages`, and nothing else. `describe.py:22` `asdict`s exactly that.

8. **`_run`'s `uv` lookup on Windows** — `shutil.which` is documented to consult `PATHEXT` on
   Windows, so `which("uv")` finds `uv.exe`. Taken from CPython's documented behaviour rather than
   executed here; I could not test on Windows.

---

## Rule concerns

None. Every finding above is measured against `AGENTS.md`, an ADR, or
`docs/architecture/packaging.md` / `app-model.md` / `errors.md` as written.

One observation that is a gap rather than a disagreement: `docs/architecture/errors.md` defines the
framework's error model (typed exceptions, stable codes, `ErrorInfo`) and says nothing about an
App's *own* expected failures. The Hub invented a parallel model — `Diagnostic` in an output model,
with `hub.*` codes — and it is a defensible reading of ADR-007 (an output model is revalidated, so
no exception instance can travel in one) and of ADR-019's "an exception raised by an App's own code
is described, not classified". But it is now a second failure vocabulary that no document owns, and
`AGENTS.md` says one role per document. When M11 renders these and M12 consumes them, whether an
App's expected failures are data or exceptions ought to be a decision on record.

---

## Assessment

The packaging layer is the strongest part of this axis. ADR-023 is implemented as written, the
import/no-import line is drawn in exactly the place the ADR draws it, and it is proven by test
rather than asserted in a docstring. The distribution boundary between `src/vibepy/` and `hub/`
holds in both directions, and the Hub is a real App rather than a control plane wearing an App's
clothes — its Tools are its surface, its internals are behind `ToolContext`, and its tests only
ever touch it through `ToolRuntime.invoke`.

The Hub's *internals* are where the work is unfinished, and the gap is consistent in character: the
happy path is thought through carefully — often more carefully than I expected, as with the
HTTP-answer readiness probe and the stripped child environment — while the failure and adversarial
paths are thin. F1 is the one that must not ship: an unconstrained Tool input reaching
`shutil.rmtree`, on a Tool that by ADR-024 is exposed to an agent by construction. F3, F4 and F5
are the same shape one level down: a failure mode that escapes the module's own diagnostic
vocabulary and leaves either a leaked process, a half-built environment, or a Tool that throws where
a `Diagnostic` already exists to carry the answer. F2 is a rule the Hub demonstrably knows and
applies once, then omits at twenty call sites, and it will become visible the moment M11 puts a Page
on the same loop.

F6 through F9 are contract-quality rather than correctness: positional joins between two
independently-sorted lists, three naming schemes for one App, an output model that is unsafe as an
input model, and a state field typed as `str` where the agent reading its schema needs the enum.
These are the ones worth fixing before M11 and M12 build on the surface, because each one becomes
harder to change once a Page and an authoring client consume it.

The samples do the job asked of them — `notes` in particular carries two invariants cleanly — but
`todo` has leaked test scaffolding into its shipped module and declares a config field it does not
use, which weakens it as the reference an app author (or, per M18, a coding agent) will copy.
