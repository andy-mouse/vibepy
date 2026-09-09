# Code review findings

Full-repository review at `05d6027`, baseline `make lint typecheck test` passing with 152 tests.
Seven reviewer agents; every finding below was then re-verified against the code by the
coordinator. The reports the findings were distilled from are in `reviews/`.

`../code-review-roadmap.md` says which stage fixes what. This file says what was found, where,
and how it was checked.

## Index

| ID | Finding | Where | Stage |
| --- | --- | --- | --- |
| C1 | Hub path traversal reaches `rmtree` | `hub/.../tools/installation.py:159` | CR1 |
| I1 | `AppNotDeclared` outside the exception hierarchy | `serve.py:33` | CR1 |
| I2 | Blocking I/O on the event loop in Hub handlers | ~20 sites in `hub/` | CR2 |
| I3 | Routes outlive the window; three documents say otherwise | `adapters/nicegui/web.py:45` | CR3 |
| I4 | No Agent-channel command exists (adjudicated, A1) | all four `pyproject.toml` | CR3 |
| I5 | `PageRegistry.definitions()` is dead, and three places say it is used | `page/registry.py:26` | CR1 |
| I6 | Duplicate Page name serves one handler on two routes | `adapters/nicegui/web.py:34` | CR1 |
| I7 | Child process orphaned on cancellation or stdin failure | `internals/processes.py:166` | CR2 |
| I8 | `config.invalid` degrades to an exit code at the Hub boundary | `internals/processes.py:156` | CR2 |
| I9 | Hub publishes a second, category-less error vocabulary | `hub/.../models.py:13` | CR2 |
| I10 | Hub state is read-modify-write, unlocked, truncating | `internals/state.py:61` | CR2 |
| I11 | Two install identities for one App | `tools/installation.py:42` | CR2 |
| I12 | AGENTS.md restates facts the architecture documents own | `AGENTS.md` | Q1 — done |
| I13 | No document owns the Hub as current truth | `docs/architecture/` | CR3 |
| I14 | Two headline invariants have no executable guard | `tests/test_mcp_adapter.py:312` | CR1 |
| I15 | `to_error_info` breaks on the framework's own public extension point | `errors.py:213` | CR1 |
| I16 | Half-installed environment left behind, diagnostic lost | `tools/installation.py:111` | CR2 |
| I17 | `list_apps` raises when a registered source folder has disappeared | `internals/projects.py:67` | CR2 |
| I18 | `declared_name` paired positionally with `describe` output | `tools/installation.py:113` | CR2 |
| I19 | `HeldConfig` cannot be fed back into `configure_app` | `internals/configuration.py:48` | CR2 |
| I20 | The Web channel's error contract is untested | `tests/` | CR1 |
| I21 | Three Hub tests assert less than their names claim | `hub/tests/` | CR2 |
| I22 | `start_app`'s `secrets` has no test at all | `hub/tests/` | CR2 |
| I23 | CI does not run what the Makefile runs | `.github/workflows/` | L1 |
| I24 | The Todo example teaches the wrong shape | `samples/todo/.../entry.py` | CR2 |
| I25 | ADR hygiene | `docs/decisions/` | A0 — done |
| I26 | Three implemented decisions have no ADR | `docs/decisions/` | A0 — done |
| I27 | `architecture.md:18` contradicts `packaging.md:132` | `docs/architecture.md:18` | CR3 |
| I28 | `authoring.md` documents nothing that exists | `docs/architecture/authoring.md` | CR3 |
| D1 | Published schema versus serialized payload | `adapters/mcp/projection.py:19` | CR1 — latent |

## Critical

### C1 — An App name reaches `rmtree` unconstrained

**Where** `hub/src/vibepy_hub/tools/installation.py:159`, `internals/installer.py:39`,
`models.py:56` · **Agreed by** axis 4

`AppName.app_name` is an unconstrained `str`, `environment()` is a bare `root / "envs" / name`
join, and `remove_app` calls `shutil.rmtree` on the result with no gate. ADR-024 exposes every
Hub Tool on the Agent channel, so this is a model-controlled string reaching a recursive delete.

**Verified** by resolving paths only; no delete was executed.

```text
'todo-app'      -> /hubroot/envs/todo-app   under the root
'../../victim'  -> /victim                  escapes
'/etc/passwd'   -> /private/etc/passwd      an absolute name discards the root entirely
```

The reviewer reported the `../..` case. The absolute-path case is worse and was found in
verification.

## Important — reached independently by two or more reviewers

### I1 — `AppNotDeclared` sits outside the exception hierarchy

**Where** `src/vibepy/serve.py:33` · **Agreed by** axes 3, 5, 7

Derives from `Exception`, so it carries no code, no category and no row in `errors.md`.
`tests/test_errors.py` walks `VibepyError.__subclasses__()` and therefore cannot see it — the
catalogue test gives false assurance. The same function writes `{"code", "message"}` JSON for
every other failure at `serve.py:99-102` and prose for this one.

### I2 — Blocking I/O on the event loop across the Hub's handlers

**Where** roughly twenty sites in `hub/src/vibepy_hub/` · **Agreed by** axes 3, 4

`asyncio.to_thread` appears twice in the whole repository, one of them at `installer.py:68` in
the same package — the rule is known and applied once. `rmtree`, `iterdir`, `mkdir` and TOML
parsing run directly in `async def` handlers that `ToolRuntime` explicitly permits to overlap.

### I3 — Routes outlive the window, and three documents say otherwise

**Where** `adapters/nicegui/web.py:45` · **Agreed by** axes 2, 3, 6, 7

Registration mutates the Web technology's process-global table and nothing unregisters.
`application.py:38-41`, `adapters.md:77-80` and `app-model.md` all state the opposite as a
property of the window. `tests/test_nicegui_adapter.py:1-6` says outright that the test fixture
performs the cleanup those documents attribute to the framework.

### I4 — No Agent-channel command exists

**Where** all four `pyproject.toml` files · **Agreed by** axes 6, 7

**Verified**: no `[project.scripts]` anywhere. `app-model.md:88-90` and `packaging.md` say the
MCP client launches a command. `samples/notes`, the Agent-only sample, is therefore reachable by
nobody.

**Adjudicated (A1)**: axis 2 called this a decision recorded ahead of its milestone rather than a
defect. That is right about ADR-010 — a record of *why* may record a future decision — and wrong
as a verdict, because axes 6 and 7 judged the architecture documents, which AGENTS.md makes
current truth. The finding stands against those documents, not against the ADR.

### I5 — `PageRegistry.definitions()` is dead, and three places say it is used

**Where** `src/vibepy/page/registry.py:26` · **Agreed by** axes 2, 6

`register_pages` iterates `definition.pages`; `definitions()` has no caller outside its own test.
`page-model.md:135-136` and the method's own docstring at `registry.py:29` both assert that a Web channel adapter
projects those declarations into routes.

### I6 — A duplicate Page name serves one handler on two routes

**Where** `adapters/nicegui/web.py:34-45`, `page/registry.py:18` · **Agreed by** axis 2

Registration validates route uniqueness and not name uniqueness, while the registry overwrites
by name. Two Pages with one name and two routes register both routes and render the second
handler from each, with no diagnostic. ADR-012's stated rationale is that such a collision fails
loudly rather than disappearing silently.

### I7 — A child process is orphaned on cancellation or a stdin failure

**Where** `hub/src/vibepy_hub/internals/processes.py:166-177` · **Agreed by** axes 3, 4, 7

The stdin write sits outside the `try`, and `_running` is populated only after the child answers.
A `CancelledError` or `BrokenPipeError` therefore leaves a child neither killed nor owned, so
`aclose()` cannot reach it — against `entry.py:35-36`, which promises a window leaves no child
behind.

### I8 — `config.invalid` degrades to an exit code at the Hub boundary

**Where** `internals/processes.py:156-176`, `tools/runtime.py:52` · **Agreed by** axes 3, 7

The framework raises `config.invalid` inside the lifespan; the Hub inherits the child's stderr
and reports `"the App exited with N"`, returning `hub.start_failed`. The `caller` category, which
is what says a retry could succeed, is lost. `serve.py:99-102` already writes structured JSON for
entrypoint failures, so the command is inconsistent with itself.

### I9 — The Hub publishes a second, category-less error vocabulary

**Where** `hub/src/vibepy_hub/models.py:13-18` · **Agreed by** axes 4, 7

`Diagnostic` carries code, message and details and rides inside a *successful* result;
`ErrorInfo` carries those plus a category and rides inside a failure. Eight `hub.*` codes appear
in no table, and none answers the retryability question the category exists for. `errors.md` is
silent on App-defined codes.

### I10 — Hub state is read-modify-write, unlocked, and truncating

**Where** `internals/state.py:61` · **Agreed by** axis 7

**Verified**: `write_text` in place — no temporary file and `os.replace`, no `asyncio.Lock` —
while `ToolRuntime` explicitly permits concurrent invocations. A concurrent write loses an
update; a crash mid-write loses the held secrets.

### I11 — One App acquires two install identities

**Where** `tools/installation.py:42-48`, `:97`, `:141-151` · **Agreed by** axes 4, 7

`_candidate_folder` matches a distribution name *or* a folder name, the environment is created
under whichever the caller passed, and `list_apps` keys available rows by folder name alone.
Installing by project name lists the same App twice and keys every later Tool on the caller's
accidental choice.

### I12 — AGENTS.md restates about eleven facts the architecture documents own

**Where** `AGENTS.md` · **Agreed by** axis 6 · **Stage** Q1, merged

The one-role rule was breached most heavily by the document stating it, and one copy had already
drifted: AGENTS.md said a *channel* validates configuration where `app-model.md` says a *window*
does.

### I13 — No document owns the Hub as current truth

**Where** `docs/architecture/` · **Agreed by** axis 6

Roughly 700 lines, eight Tools, a state vocabulary and a diagnostic vocabulary. M10's integration
promoted four lines out of 2,045 deleted. M11 is specified against "Hub Core state" that no
document defines.

### I14 — The two headline invariants have no executable guard

**Where** `tests/test_mcp_adapter.py:312`, `tests/test_nicegui_adapter.py:149` · **Agreed by**
axes 1, 2

No MCP type in the core Tool model and no Web type in the core Page model are true by reading and
untested. The AST leak guards that exist scan `tool/`, `page/` and `app/` only, skipping
`vibepy/__init__.py`, `errors.py` and `describe.py` — and the package root is exactly where an
SDK import would reach every consumer.

## Important — one reviewer, verified

### I15 — `to_error_info` breaks on the framework's own public extension point

**Where** `src/vibepy/errors.py:213` · **Agreed by** axis 1

`VibepyError` is exported public API (`__init__.py:78`) and `code` is an unassigned `ClassVar`,
so an App that subclasses it reaches a normalizer that cannot describe it. The MCP adapter calls
this inside `except Exception`, so an app defect becomes the protocol error that clause exists to
prevent.

**Reproduced**:

```text
to_error_info(VibepyError('x'))                 -> AttributeError
to_error_info(<subclass declaring its own code>) -> KeyError
```

### I16 — A half-installed environment is left behind and its diagnostic lost

**Where** `tools/installation.py:111` · **Agreed by** axis 4

`purelib(env)` sits outside the `except InstallFailed` block and can itself raise it, so the
environment survives with no facts file. The next `list_apps` then takes the branch that calls
`purelib` again and raises out of `list_apps` too. Every other failure here returns a
`Diagnostic`.

### I17 — `list_apps` raises when a registered source folder has disappeared

**Where** `internals/projects.py:67` · **Agreed by** axis 4

`source.iterdir()` is unguarded, and a source path is checked once at registration and then
persists in `state.json` across windows. A removed folder makes `list_apps`, `install_app` and
even `remove_package_source` — the fix — raise `FileNotFoundError`. The
`hub.source_unreadable` code already exists for this.

### I18 — `declared_name` is paired positionally with `describe` output

**Where** `tools/installation.py:113`, `:124` · **Agreed by** axis 4

The two lists come from different search paths and are joined by index, lining up only because
both happen to sort the same way. `AppDescription` carries no declared name to join on.
`declared_name` is what `start_app` hands `vibepy.serve`, so a mispairing starts a different App.

### I19 — `HeldConfig` cannot be fed back into `configure_app`

**Where** `internals/configuration.py:48` · **Agreed by** axis 4

Secrets are returned as the literal string `"set"` and there is no read-only configuration Tool,
so the natural round trip — read the form, edit one field, resend — writes `"set"` over the real
secret. The output type is unsafe as the input type.

### I20 — The Web channel's error contract is untested

**Where** `tests/` · **Agreed by** axis 5

`errors.md` states that the Web channel translates nothing. No test raises inside a Page handler
behind a route. M7's third criterion is verified for the Agent channel only, so the channel that
promises not to translate is the one never checked.

### I21 — Three Hub tests assert less than their names claim

**Where** `hub/tests/test_installation.py:72`, `test_configuration.py:73`,
`tests/test_app_isolation.py:27` · **Agreed by** axis 5

"leaves its data" is vacuous because `TodoStore` never writes `db_path` and the file it checks
lies outside the tree `remove_app` deletes. "so a restart needs no one" never restarts and reads
`STATE_FILE` internals instead of the public contract.

### I22 — `start_app`'s `secrets` has no test at all

**Where** `hub/tests/` · **Agreed by** axis 5

All six invocations pass `{}`. The merge that is the parameter's whole reason is never exercised,
because the only secret-declaring sample has no Pages and cannot be started.

### I23 — CI does not run what the Makefile runs

**Where** `.github/workflows/` · **Agreed by** axis 5 · **Stage** L1

**Verified**: CI lints `src tests`; the Makefile lints `src tests hub samples`. The Hub and the
examples are never linted or format-checked in CI, so `make lint typecheck test` is not what CI
enforces.

### I24 — The Todo example teaches the wrong shape

**Where** `samples/todo/src/todo_app/entry.py:49`, `:90`, `:131` · **Agreed by** axes 4, 7

`TODO_CONFIG` ships a POSIX `"/tmp/..."` string in a distributed module, against the rule that
paths are `Path` on macOS and Windows. `TodoStore` declares `db_path` and keeps a list in memory.
The Page narrows Tool results with `assert isinstance`, which `python -O` strips. This is the
file an app author, or M18's coding agent, copies.

### I25 — ADR hygiene

**Where** `docs/decisions/` · **Agreed by** axis 6 · **Stage** A0, merged

ADR-006 Accepted and half false, still cited as live by `lifecycle.md:64`; ADR-012 Accepted with
a Decision that names a signature `register_pages` has never had; ADR-003, 004, 005 and 006 with
no Context section.

### I26 — Three implemented decisions have no ADR

**Where** `docs/decisions/` · **Agreed by** axis 6 · **Stage** A0, merged

The direct `fastapi`/`uvicorn` dependency with an ASGI-lifespan Web window, which reversed what
the M10 spec specified; `python -m vibepy.serve` as a second framework command; and the Hub's
`Diagnostic`/`hub.*` vocabulary.

### I27 — `architecture.md` contradicts `packaging.md`

**Where** `docs/architecture.md:18` versus `docs/architecture/packaging.md:132` · **Agreed by**
axis 6

**Verified**. The core-model diagram still lists `Manifest / metadata`; `packaging.md` and
ADR-023 state that the framework defines no manifest format.

### I28 — `authoring.md` documents nothing that exists

**Where** `docs/architecture/authoring.md` · **Agreed by** axis 6

Three of its capability names now collide with shipped Hub Tools, and `app_status` no longer
exists.

## Downgraded in verification

### D1 — Published schema versus serialized payload

**Where** `adapters/mcp/projection.py:19`, `adapters/mcp/server.py:116` · **Reported by** axes 1,
7, both as Important

The schema is `model_json_schema()` in validation mode; the payload is
`model_dump(mode="json")`. A `computed_field` or a `serialization_alias` would make the payload
non-conforming to the schema the same adapter published.

**Verified**: no `computed_field` and no `serialization_alias` exists in any output model in the
repository — the single `alias=` is on `internals/projects.py:41`, an internal parsing model.
The contract gap is real; it has no instance today. Downgraded to latent. The fix is one
argument, `mode="serialization"`, and a test.

## Open questions — not defects

| ID | Question | Status |
| --- | --- | --- |
| Q1 | Do AGENTS.md's invariants belong to it or to the architecture documents? | Settled in Q1, merged |
| Q2 | Is a Tool name validated at all? Nothing checks it, and the projection passes it through. `tool-model.md` does not require it | CR3 |
| Q3 | Are two import surfaces supported? Nothing imports from `vibepy` itself; the flat re-export is unexercised | CR3 |
| Q4 | Where does a design artifact such as `hub-ui-mockup.html` belong? The role table has no row for one | CR3 |

## Checked and found sound

- No Critical in the framework core. Channel neutrality, the single invocation path, `ToolContext`
  as the only carrier of invocation state, declarations held in the registry, and one name per
  invocation all hold in the code — verified independently by axes 1, 2, 3 and 7.
- No test was found to be fabricated or satisfied by a mock. The only substitutes are a recording
  invoker that raises if invoked and a negative fixture proving `describe_app` uses `isinstance`.
- The framework-to-Hub distribution boundary is intact in both directions. The only reference
  from the framework's own project file is in its dev group (`pyproject.toml:26-28`).
