# Axis 5 — Test suite as a contract

Repo: /Users/andy.warhol/my-projects/vibepy @ 05d602750328f723354823b8fb97c6bf5862ba03

Judged against AGENTS.md ("Tests verify public contracts, not internals"; "Exception types are
the contract, not message strings"), `docs/architecture.md` + `docs/architecture/*.md`,
ADR-001..ADR-024, and the M1..M10 acceptance criteria in `docs/roadmap.md`.

## Strengths

- **Almost no mocks.** The only substitute objects in the whole suite are
  `tests/test_page_core.py:17` `RecordingInvoker` (used only in tests that never invoke — it
  raises `AssertionError` if invoked, so it cannot silently satisfy a behavioural test) and
  `tests/impostor_fixture.py` (a negative fixture proving `describe_app` uses `isinstance`
  rather than duck-typing, `tests/test_app_package.py:128`). `tests/conftest.py` substitutes
  nothing; it only enables NiceGUI's `user` plugin. Nothing in `tests/` or `hub/tests/` asserts
  against a stub standing in for the code under test. Every Tool invocation in the suite goes
  through the real `ToolRuntime`.
- **The two channels are tested through their real seams.** `tests/test_dual_channel.py` drives
  a real `nicegui.testing.User` browser session and a real `mcp.client.Client` against one
  composed lifespan in one test, and `tests/test_execution_semantics.py:208,239` pins the
  concurrency of *both* SDKs rather than of the framework's own code. `tests/test_serve_command.py`
  and `hub/tests/test_runtime.py` run the Web channel as an actual OS process over a real socket.
  This is a rare and genuinely valuable level of integration.
- **Error-model tests are structural, not enumerated.** `tests/test_errors.py:107` walks
  `VibepyError.__subclasses__()` and fails if a new exception is added without a row; :120 and
  :125 enforce code uniqueness and the `app.unhandled` reservation; :142 enforces the AIP-193
  rule that every value the message interpolates is also in `details`. This is the correct way to
  hold `docs/architecture/errors.md`.
- **Invariants are proven, not assumed.** `tests/test_mcp_adapter.py:312` and
  `tests/test_nicegui_adapter.py:149` AST-scan `src/vibepy/{tool,page,app}` for `mcp`/`nicegui`
  imports, which is a real enforcement of the "must not leak into the core model" invariants.
  `tests/test_app_isolation.py:11` asserts `sys.modules` after `discover_apps`, which is the
  only honest way to test "reading what an environment offers imports nothing".
- **The public API is pinned as a product.** `tests/test_package.py:4` asserts the exact
  `vibepy.__all__` list, which is what "Keep it backward compatible; deprecate before removing"
  requires.
- **CI runs macOS and Windows** (`.github/workflows/ci.yml`), and the two platform-sensitive
  spots are handled: `hub/tests/test_installation.py:19` branches on `sys.platform`, and
  `hub/tests/test_configuration.py:90` skips the POSIX permission assertion on Windows.

## Findings

### Critical

None. No test in this suite is fabricated, and none passes because of a mock.

### Important

**1. `hub/tests/test_installation.py:72-88` — "leaves its data" asserts nothing about the App's
data.**
The test writes `tmp_path/todo.db`, installs and removes the Todo App, then asserts the file
still exists. But `samples/todo/src/todo_app/entry.py:46-59` `TodoStore` stores `db_path` and
never opens it — the store is a `list[Todo]` in memory. The file the test protects was never
touched by anything, and it lives outside the Hub root (`root/envs/...`) that `remove_app`
deletes (`hub/src/vibepy_hub/tools/installation.py:159`). The assertion would hold even if
`remove_app` deleted the App's real data directory. The claim in the test name — and in
`docs/architecture/lifecycle.md` ("Operations such as install, remove…") plus the Tool's own
description "Remove an installed App, leaving the data it wrote" — has no test behind it.
*Why it matters*: this is the one destructive operation in the Hub, and the test that guards it
is decorative.
*Fix*: give the Todo sample a store that actually writes `db_path` (it already declares the
config field for exactly this), or drop the data assertion and stop claiming it.

**2. `hub/tests/test_configuration.py:73-79` — the test named "so a restart needs no one" never
restarts, and reaches into internals to compensate.**
It imports `STATE_FILE` from `vibepy_hub.internals.state` (:10) and asserts the raw token string
appears in the file's text. That is an assertion about storage layout — an internal — in place of
the public contract, which is that a *second* Hub window over the same root still has the value.
`hub/tests/test_package_sources.py:56` shows the right shape for exactly this (`async with hub(root)`
twice), and that shape is used for `sources` but not for `config`.
*Violates*: AGENTS.md "Tests verify public contracts, not internals."
*Why it matters*: the file could be renamed, encrypted, or split and this test would fail while
the contract held; conversely, a `read_state` regression that dropped `config` on reload would
pass it.
*Fix*: open a second window over the same root and assert `list_apps` reports `configured: true`
and `configure_app` still masks the held secret. Keep the plaintext-storage assertion only if
the intent is to pin that trade-off, and then say so.

**3. No test covers `start_app`'s `secrets` parameter at all.**
Every one of the six `start_app` invocations in `hub/tests/` passes `secrets: {}`
(`test_installation.py:66`, `test_runtime.py:28,47,60,88,110`). The merge
`config={**held, **payload.secrets}` in `hub/src/vibepy_hub/tools/runtime.py:50` — the mechanism
by which a declared secret reaches a running App without touching disk or argv, and the reason
`StartRequest.secrets` exists — is never exercised. The only sample declaring a secret (`notes`)
declares no Pages, so it can never be started.
*Violates*: M10 acceptance "installed Apps can be started, stopped, and queried for status", read
together with `docs/architecture/lifecycle.md`'s configure→open-a-channel step.
*Why it matters*: a regression that dropped `payload.secrets` from the merge, or that let `held`
win over it, would be invisible to the suite.
*Fix*: a sample App that declares both a secret and a Page, started with a secret and asserted
through a Page or Tool that reports it received the value.

**4. `tests/test_serve_command.py:76` asserts an exception's message string for a failure the
framework never gave a type or a code.**
`assert "absent" in finished.stderr.decode()` pins the sentence produced by
`src/vibepy/serve.py:61`'s `AppNotDeclared`, which does **not** derive from `VibepyError`, carries
no `code`, and appears nowhere in the code table of `docs/architecture/errors.md`. `serve.main`
writes JSON with a code for every other failure (:92, :101) and a bare sentence for this one
(:97).
*Violates*: AGENTS.md "Framework exceptions derive from a single base class. Exception types are
the contract, not message strings." Also means `tests/test_errors.py:107`'s catalogue sweep
cannot see this error, so the "a milestone cannot skip the rule" guarantee has a hole in it.
*Why it matters*: the one failure a Hub operator hits most (wrong App name) is the one with no
machine-readable code, and its only test pins prose.
*Fix*: make it a `VibepyError` with a code, add it to `_CATEGORIES` and the errors.md table (it
will then be swept by `test_every_framework_error_is_covered_here`), and assert the code.

**5. The Web channel's error contract has no test.**
`docs/architecture/errors.md` states flatly: "The Web channel translates nothing. A framework
error or a handler exception raised during a render reaches NiceGUI, which renders it." There is
no test anywhere that raises inside a Page handler behind a *NiceGUI route* and observes what the
Web channel does. `tests/test_page_core.py:238` covers `PageRuntime.render` in isolation (the
exception reaches the caller), and `tests/test_mcp_adapter.py:267-286` covers the Agent channel
thoroughly — but the Web half of M7's third criterion ("channel adapters preserve the same
framework error semantics") is asserted only for the channel that translates, never for the one
that promises not to.
*Fix*: a page whose handler raises a `ToolNotFoundError` and a page whose handler raises a domain
exception, both opened through `user.open`, asserting the adapter neither swallows the failure nor
renders a success.

**6. `hub/tests/tests_support.py:8` and `tests/test_todo_distribution.py:3` import through
internal module paths.**
`from vibepy.app.composition import tool_runtime_for` and
`from vibepy.app.package import discover_apps` — both names are exported from `vibepy.app` and
from the package root (`src/vibepy/__init__.py:44`), and `tests/test_package.py` exists precisely
to pin that root surface. Importing the submodule path means the Hub's entire test suite, and one
framework test, exercise a path the public-API test does not defend.
*Violates*: AGENTS.md "Tests verify public contracts"; "The public API is a product."
*Why it matters*: `src/vibepy/app/composition.py` could be split or renamed without a single test
failing on the public surface — the failures would be in tests that shouldn't have known the path.
*Fix*: import from `vibepy` or `vibepy.app`.

**7. Hub diagnostics with no test: `hub.already_running` and `hub.declaration_missing`.**
`hub/src/vibepy_hub/tools/runtime.py:40-43` and
`hub/src/vibepy_hub/tools/installation.py:73-79` each publish a stable diagnostic code. Every
other Hub code (`hub.not_installed`, `hub.no_web_channel`, `hub.not_running`, `hub.start_failed`,
`hub.candidate_absent`, `hub.no_app_declared`, `hub.install_failed`, `hub.source_unreadable`) has
a test; these two do not. `hub.declaration_missing` also guards the only place the Hub reconciles
its `envs/` directory against what an environment actually declares — the row that tells an
operator an installation has gone stale.
*Violates*: M10 "installed Apps can be started, stopped, and queried for status"; the code-stability
rule in `docs/architecture/errors.md` applies to the Hub's published codes by the same logic.
*Fix*: start twice for the first; delete or corrupt an env's `dist-info` for the second.

### Minor

**8. `tests/test_app_isolation.py:27` — the test name overclaims what it asserts.**
`test_a_description_is_obtained_without_this_process_loading_the_app` runs `vibepy.describe` in a
subprocess and asserts only `returncode == 0` and `name == "Todo"`. It makes no assertion about
this process. It cannot: `tests/test_app_package.py:8` imports `todo_app.entry` at module scope,
so `todo_app` is already in `sys.modules` when the test runs. The invariant is genuinely proven
one test above it (:11, via `sys.modules`); this one proves only that the out-of-process describe
path works.
*Fix*: rename to what it tests (`test_the_describe_command_runs_in_the_apps_own_environment`), or
leave the assertion and drop the claim.

**9. `hub/tests/test_installation.py:129` asserts a message substring where a structured detail
exists.** `assert "uv" in answered.diagnostic.message`. `Diagnostic` carries
`details={"step": failure.step, "output": failure.output}`
(`hub/src/vibepy_hub/tools/installation.py:108`), so the test can assert `details["step"] == "uv"`.
*Violates*: the spirit of AGENTS.md's message-strings rule and of `docs/architecture/errors.md`
("an agent reads these rather than parsing the sentence") — a test should read the metadata for
the same reason an agent does.

**10. `tests/test_serve_command.py:96` — a disjunction weakens the assertion to nothing much.**
`assert "config.invalid" in written or "AppConfigInvalidError" in written`. One branch is the
stable published code; the other is a Python class name that is explicitly *not* the cross-boundary
contract (`docs/architecture/errors.md`: "A code is the projection of a type across a boundary a
Python type cannot cross"). The test passes if uvicorn logs the traceback and never emits the code.
*Fix*: assert the code, or if the code genuinely cannot reach stderr through ASGI's
`lifespan.startup.failed`, say so in the docstring and assert exactly what does.

**11. `tests/test_errors.py`'s catalogue guarantee is weaker than its docstring claims.**
`_descendants` walks `VibepyError.__subclasses__()`, which sees only classes whose defining module
has been imported. The file imports every name from `vibepy.errors` (:14-29), so it is exhaustive
for errors defined there — but the docstring's claim that "a milestone that adds an error must not
be able to skip the rule by not editing this file" holds only by the unenforced convention that all
errors live in one module. Finding 4 (`AppNotDeclared` in `serve.py`) is that convention already
broken once.
*Fix*: assert that every `VibepyError` subclass is defined in `vibepy.errors`, or import the
package's modules before sweeping.

**12. Untested framework error paths.**
- `src/vibepy/serve.py:92` — the `serve.config_invalid` branch (stdin that is not a JSON object)
  has no test, and its code appears in no document. Two of `main`'s three failure exits are
  tested; this one is not.
- `src/vibepy/serve.py:99-102` — the entrypoint-unloadable/invalid branch of `serve` has no test
  (the equivalent branch of `describe` does, `tests/test_describe_command.py:91`).
- `docs/architecture/lifecycle.md`'s cleanup table has three rows; `tests/test_app_composition.py`
  covers two ("entering the lifespan raises" :145, "a later resource fails" :157). The third,
  "the lifespan raises on exit", has no test.
- `src/vibepy/adapters/mcp/server.py:123-124` — the server's name and version are read from the
  declaration; nothing asserts an agent sees them.

**13. Untested Hub degradation paths.** `read_state` (`internals/state.py:38`), `read_facts`
(`internals/installer.py:125`), `secret_fields` (`internals/configuration.py:41`) and `_described`
(`internals/projects.py:54`) each swallow a `ValidationError`/parse failure and log-and-continue.
None of the four recovery paths has a test, so a Hub that silently forgets its state on a corrupt
file is indistinguishable from one that works. `Processes.stop`'s kill-after-`STOP_TIMEOUT` path
(`internals/processes.py:192-195`) is likewise untested.

**14. CI lints less than `make lint`.** `.github/workflows/ci.yml` runs `ruff check src tests`
while the Makefile runs `ruff check src tests hub samples`. `hub/tests/` — a quarter of the suite —
is formatted and linted only on a developer's machine. (`pyright` does cover it via
`pyproject.toml`'s `include`.) AGENTS.md says a change is done when `make lint typecheck test`
passes; CI does not run that.

**15. Duplicated AST helper.** `_imported_module_names` is defined identically in
`tests/test_mcp_adapter.py:302` and `tests/test_nicegui_adapter.py:139`, as is the module-collection
block. `tests/lifecycle.py` already exists as the place shared test helpers go. Not a contract
issue; noted because both copies must be kept in step if a fourth core package is added (neither
copy scans `src/vibepy/errors.py` or `src/vibepy/__init__.py`).

## Roadmap acceptance criteria coverage

**M1 — Tool Core.** *Verified*: raw input → validation → async handler → validated output
(`test_tool_core.py:192`); unknown (:215), input (:225) and output (:234) errors, each asserted by
exception type and by the attribute carrying the tool name. Registry enumeration and replacement
(:278, :290). Independent `invocation_id` per call (:265). No gap.

**M2 — Page Core.** *Verified*: a Page invokes a Tool through the narrow `ToolInvoker`
(`test_page_core.py:170`), receives the validated output model (:184), and `PageContext` exposes
nothing else (:47, asserted over `dataclasses.fields` — a legitimate reading of a public frozen
dataclass, not an internals reach). No gap.

**M3 — MCP Adapter.** *Verified*: discovery (`test_mcp_adapter.py:123`), schemas derived from the
declared Pydantic models including `$defs` (:64, :71, :133), calls going through `ToolRuntime`
(:144, :153 — proven by the `ToolContext` the handler actually received), no SDK leak into the
core model (:312). *No test*: the server's advertised name/version (finding 12).

**M4 — NiceGUI Adapter.** *Verified*: `PageDefinition` → route (`test_nicegui_adapter.py:42`),
handler receives `PageContext` (:63), interaction invokes a Tool (:130), dual-channel Todo proof
(`test_dual_channel.py:52`). Route rejection and all-or-nothing registration (:98, :109, :120).
No gap.

**M5A — AppRuntime and shared state.** *Verified*: Web-like and Agent-like calls over one composed
lifespan reach one backend (`test_dual_channel.py:52`); a second window is isolated
(`test_app_composition.py:98`, `test_app_config.py:125`). No gap.

**M5B — Execution semantics.** *Verified*, and unusually well: concurrency proved by an
`asyncio.Barrier` reached through `ctx.dependencies` rather than by elapsed time
(`test_execution_semantics.py:172`); independent contexts (:179); shared app-scoped deps (:186);
and the same proof repeated at both real channel seams (:208, :239) plus the Page render path
(:193). No gap.

**M6 — Runtime lifecycle.** The first two criteria (state machine `CREATED→…→STOPPED`, hooks at
transition boundaries) are **superseded by ADR-020** (Accepted; supersedes ADR-004/015/018) and by
`docs/architecture/lifecycle.md` — the framework owns no lifecycle object, so there are no
transitions to test. That is a documented decision, not a coverage gap; `docs/roadmap.md` is not
edited by rule. The third criterion, "startup/shutdown failures perform deterministic cleanup", is
*partly verified* (`test_app_composition.py:78,145,157`) — two of the three rows of the cleanup
table in `lifecycle.md`; the "lifespan raises on exit" row has no test (finding 12).

**M7 — Structured error model.** *Verified*: stable codes and the catalogue sweep
(`test_errors.py:107,120,125,129`), category assignment, `details` completeness (:142), and
`app.unhandled` for a non-framework exception (:152). Tool/Page/adapter failures distinguishable
(codes are namespaced, :113). *Gap*: "channel adapters preserve the same framework error
semantics" is verified for the Agent channel only; the Web channel's stated "translates nothing"
contract has no test (finding 5). Lifecycle failures no longer have codes (ADR-020, codes retired).

**M8 — Configuration and dependencies.** *Verified*: validated before the lifespan is entered
(`test_app_config.py:81`, asserting the lifespan was never entered); reaches the lifespan as the
declared model (:59); secrets not disclosed by the config object (:106); schema readable without
running anything (:145); sharing within one window and isolation between windows (:125,
`test_execution_semantics.py:186`). No gap. (Note the POSIX-literal `/tmp/...` paths at :72,:117,
:135 — comparisons hold on Windows since nothing opens them, and CI does run Windows.)

**M9 — App Package.** *Verified*: discovery from `dist-info` without importing
(`test_app_package.py:33`, `test_app_isolation.py:11`), ordering (:61), loading and describing a
declared entrypoint (:72), unloadable module (:84) and missing attribute (:100), a wrong object
(:113) and a duck-typed impostor (:128) — each asserted by exception type or published code.
*Thin*: "invalid package metadata produces structured diagnostics" is verified for *entrypoint*
failures only. Malformed `entry_points.txt`, an unparseable entry value, or a `dist-info` with no
`METADATA` produce no tested diagnostic.

**M10 — Hub Core.** *Verified*: register/remove source with candidate listing and persistence
across windows (`test_package_sources.py`, all five), install into an environment of its own with
a real interpreter (`test_installation.py:22`), listing installed vs available (:37), remove
(:72), start→answer over HTTP→stop (`test_runtime.py:18`), start under the declared name rather
than the folder name (`test_installation.py:51`), no-Web-channel refusal (:54), config refusal at
window-open (`test_runtime.py:97`), and no child left behind when the window closes (:78 — a real
socket assertion). This is strong. *Gaps*: `hub.already_running` and `hub.declaration_missing`
untested (finding 7); the `secrets` path untested (finding 3); "leaves its data" vacuous
(finding 1); config persistence across windows asserted through the state file rather than through
a second window (finding 2); `remove_app` forgetting an App's held configuration
(`installation.py:160-169`) has no assertion.

M11+ are unimplemented and out of scope.

## Cross-boundary assumptions

| I assumed | Verified? | Where I checked |
| --- | --- | --- |
| The MCP adapter reaches the App only through `ToolRuntime` and never builds a `ToolContext` | Yes | `src/vibepy/adapters/mcp/server.py:104` (`ctx.lifespan_context.invoke`); `tests/test_mcp_adapter.py:153` asserts the context the handler received came from the runtime |
| The NiceGUI adapter reaches the App only through `PageRuntime` | Yes | `src/vibepy/adapters/nicegui/web.py:48-57` closes over the runtime; `docs/decisions/ADR-020` explains why it is a closure and not request state |
| `ToolRuntime` revalidates output, so `Tool` output assertions are real | Yes | `src/vibepy/tool/runtime.py:54-59` dumps then re-validates; `tests/test_tool_core.py:177` uses `model_construct` to defeat construction-time validation, which is the right adversary |
| The Todo sample persists to `db_path`, making `hub/tests/test_installation.py:72` meaningful | **No — it does not** | `samples/todo/src/todo_app/entry.py:46-59`: in-memory `list[Todo]`. This is finding 1 |
| Test-suite platform coverage exists for the macOS/Windows rule | Yes | `.github/workflows/ci.yml` matrix; `hub/tests/test_installation.py:19`; `hub/tests/test_configuration.py:90`; `internals/installer.py:44` and `internals/state.py:63` both branch on `win32` |
| `pytest` config makes `tests.lifecycle` and `tests_support` importable without a `conftest` hack | Yes | `pyproject.toml` `testpaths`; `tests/__init__.py` exists (package import), `hub/tests/` has none (rootdir sys.path insertion). No `pythonpath` setting is needed and none is used |
| Every framework exception is defined in `vibepy/errors.py`, making the catalogue sweep exhaustive | **No** | `src/vibepy/serve.py:33` `AppNotDeclared`. Finding 4/11 |
| `AppEntrypoint` is checked by type, not by shape, when loading a package | Yes | `src/vibepy/app/package.py:74` `isinstance`; `tests/impostor_fixture.py` + `tests/test_app_package.py:128` are the negative proof |
| The Hub never imports an App into its own process | Yes | `hub/src/vibepy_hub/internals/installer.py:101` runs `vibepy.describe` with the child interpreter; `internals/processes.py:63` strips the variables that would misdescribe the child. Note: the individual entries of `DESCRIBES_THIS_PROCESS` are not asserted anywhere — the suite would only notice if stripping broke badly enough to stop a start |
| "Pages must not bypass Tools for business state changes" is enforced somewhere | **No, and it may not be testable** | No structural test exists; `PageContext` exposing only `tools` (`tests/test_page_core.py:47`) is the closest thing, and it is a good proxy. Noted rather than filed as a finding |

## Rule concerns

None. The AGENTS.md rules on this axis are sound and the suite mostly honours them. One
observation rather than an objection: AGENTS.md says "`docs/roadmap.md` acceptance criteria are the
tests", and M6's criteria have since been overruled by an Accepted ADR while the roadmap says it is
never edited. That combination is working here (the ADR and `docs/architecture/lifecycle.md` carry
the current truth), but it means a reader checking M6 against the suite will find nothing and needs
ADR-020 to know why. That is the documented design, not a defect.

## Assessment

The passing tests are worth a great deal. This suite is markedly better than typical: it is
mock-free where it matters, it exercises both channels through their real SDKs and real processes,
it proves concurrency with a barrier rather than a sleep, and it enforces two architectural
invariants (no MCP/NiceGUI leak into the core; discovery imports nothing) structurally rather than
by convention. The error-model tests are the best thing in the repository — they will catch the
next milestone's mistakes without being edited.

The weaknesses are narrow and concentrated. Three tests assert less than their names claim
(findings 1, 2, 8), and the first of those guards the only destructive operation in the codebase.
One published parameter — `start_app`'s `secrets` — has no test at all, because no sample App can
both hold a secret and be started. One documented channel contract (the Web channel translates
nothing) is unverified while its Agent-channel twin is thoroughly verified. And the "exception
types, not message strings" rule is broken once in the implementation (`AppNotDeclared`) and
followed into the test that pins its prose.

Nothing here is fabricated and nothing is hollow because of a mock. The one genuinely hollow
assertion is hollow because a *sample App* does less than its configuration claims — which is a
useful reminder that in an integration-heavy suite, the fixtures that can lie are the sample
applications, not the test doubles.
