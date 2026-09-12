# M16 — App conformance validation

Date: 2026-09-12

## Acceptance criteria

From `docs/roadmap.md`, verbatim:

- conforming Apps pass validation deterministically
- invalid declarations and references produce actionable structured diagnostics
- conformance validation remains independent of channel-specific implementations

The milestone's own statement, also verbatim: *Validate manifest, declarations, handlers,
routes, Tool references, config, exposure, and lifecycle consistency with structured
diagnostics.*

## Sources

| Contract | Source |
| --- | --- |
| Declarations are frozen dataclasses; boundary values are one pydantic model | `AGENTS.md`, Python conventions |
| `AppDefinition` is a value holding every Tool and Page of one App | `docs/architecture/app-model.md`, AppDefinition |
| Route format and uniqueness are validated where routes are registered | `docs/architecture/page-model.md`, PageDefinition; `docs/architecture/adapters.md`; ADR-012 — **superseded by this milestone** |
| A Page reaches Tools only through `ctx.tools.invoke(name, raw_input)` | `docs/architecture/page-model.md`, ToolInvoker; ADR-002; ADR-016 |
| A name's format is not validated; uniqueness within one App is | `docs/architecture/tool-model.md`, ToolRegistry |
| `channels` is the set a Tool is exposed through; `required_roles` empty means anyone | `docs/architecture/tool-model.md`, ToolDefinition |
| A code is stable; two failures never share one; a milestone declares its codes | `docs/architecture/errors.md`, Codes |
| `declaration` is the category of what the App declared and the framework rejects | `docs/architecture/errors.md`, Categories |
| A command reports a failure as one `ErrorInfo` line on stderr; a reader takes what validates | `docs/architecture/packaging.md`, What a command writes to standard error |
| `describe` reads a declaration without running it; `validate_app` is `inspect_app`'s failure path until M16 | `docs/architecture/packaging.md`; `docs/architecture/authoring.md` |
| Type validation is a feedback surface the framework provides | `docs/architecture/authoring.md`, Framework responsibility |
| The framework delegates what already has an owner | ADR-025 |
| Studio runs framework commands in the project's environment with `uv run --project` | `docs/architecture/authoring.md`, Authoring Core |
| Type checking is the type checker's, not the runtime's | PEP 484, Non-goals: type hints are for offline analysis, runtime checking is left to third-party opt-in tools |
| Invariants belong in the initializer; cross-attribute invariants in the post-init hook | Python `dataclasses` docs, Post-init processing; attrs docs, Validators ("checking the resulting instance for invariants" belongs in `__init__`) |
| Collect every violation and raise once | pydantic, `ValidationError` "will contain information about all the errors" |
| A static checker reports declarations, not code bodies; references are checked only where they are declarations | Django system checks (`fields.E300` checks a declared relation; `reverse()` in view code is not checked); Terraform `validate`; Kubernetes admission (cross-object references fail at runtime) |
| A component declares what its template uses, and the compiler refuses what is not declared | Angular, `imports` array; Relay, fragments and data masking |
| A framework's build command runs the project's own type checker with the project's configuration and fails on errors | Next.js, `next build` ("fails your production build when TypeScript errors are present"; installs the checker when absent) |
| pyright is pointed at another environment's interpreter for import resolution | pyright `docs/command-line.md`, `--pythonpath` ("Path to the Python interpreter"; the same as the language server setting `python.pythonPath`) |
| pyright's structured output and exit codes | pyright `docs/command-line.md`: `--outputjson` (`generalDiagnostics[]` with `file`, `severity`, `message`, `range`, `rule`), exit 0 clean, 1 errors, 2–4 failures; default `typeCheckingMode` is `standard` |
| A diagnostic carries a severity; a failure does not | LSP `Diagnostic` (`severity`: Error, Warning, Information, Hint); Django `CheckMessage.level` and `check --fail-level`; Terraform `-json` (`severity`: error or warning, "errors invalidate the configuration, warnings are advisory") |
| PyPI `pyright[nodejs]` bundles Node through `nodejs-wheel-binaries` | pypi.org/project/pyright |

## Problem

The rules an App must satisfy exist, but each lives where its failure happens to surface, and
each stops at the first violation:

| Rule | Where it is enforced today |
| --- | --- |
| Tool names unique, Page names unique | `tool_registry_for`, `page_registry_for` as a window opens |
| route starts with `/`, routes unique | the NiceGUI adapter, as it registers routes — the Web channel only |
| configuration values valid | the window, before the lifespan |
| the entrypoint loads and is an `AppEntrypoint` | `load_app` |
| a Page refers to a Tool that exists and is exposed to it | nowhere; `tool.not_found` or `tool.forbidden` at first render |
| a Tool is exposed on at least one channel | nowhere; `channels=frozenset()` is accepted |
| handler, config and lifespan satisfy the framework's typed contracts | pyright, if the App's author runs it |

An agent authoring an App therefore learns one problem per run, learns some only on the Web
channel, and learns the type-level ones only if it happens to type-check. `authoring.md` names
`validate_app` as the place this is answered and defers it to this milestone.

## Design

### Principle

**An invalid App declaration cannot exist.** Every rule that a declaration can break is checked
where the declaration is constructed, in the dataclass's `__post_init__`, and every violation
found there is collected and raised as one exception. Nothing downstream — a window, `describe`,
an adapter — checks again; it trusts what was constructed. Validation is then what happens when
the App's own environment imports its entrypoint, and a validator is a reader of that import's
outcome.

Two kinds of rule are distinguished by what can express them:

| Rule kind | Where | Why |
| --- | --- | --- |
| a value the type cannot constrain (an empty set) | the declaring dataclass's `__post_init__` | it is known from that object alone |
| a relationship between declarations (uniqueness, a reference) | `AppDefinition.__post_init__`, the one object holding every Tool and Page | it is known only from the whole |
| a type-level contract (a handler's signature, `config` is a class, the lifespan's shape) | the type checker, run by `validate_app` | PEP 484 places it there, and the codebase re-checks no type at runtime |

### Declarations

`PageDefinition` gains a required field:

```python
@dataclass(frozen=True, kw_only=True)
class PageDefinition:
    name: str
    route: str
    title: str
    tools: frozenset[str]
```

`tools` is the set of Tool names the Page's handler may invoke. It is required with no default:
a Page that invokes nothing declares `frozenset()`, and the framework does not guess. This is
the Angular `imports` / Relay fragment pattern: what the body uses is stated in the declaration,
so a reader — the validator, `describe`, an agent — knows the Page↔Tool relationship without
reading the body.

`ToolDefinition.__post_init__` refuses an empty `channels` with `ToolChannelsEmptyError`. A Tool
is an operation an external actor invokes; one exposed nowhere is a contradiction, unlike an
empty `required_roles`, which means anyone.

`AppDefinition.__post_init__` runs the cross-declaration rules and raises
`AppDefinitionInvalidError` carrying every violation found, in declaration order:

| Rule | Violation |
| --- | --- |
| two Tools declare one name | `ToolNameConflictError` (existing) |
| two Pages declare one name | `PageNameConflictError` (existing) |
| a route does not start with `/` | `PageRouteInvalidError` (existing, moved from the adapter) |
| two Pages declare one route | `PageRouteConflictError` (existing, moved from the adapter) |
| a Page's `tools` names a Tool the App does not declare, or one not exposed on `Channel.WEB` | `PageToolUnresolvedError` (new) |

The exception is raised whether one violation was found or five, so a caller handles one shape.
The member exceptions keep their types and codes; they are the contract for *which* rule broke,
and the aggregate is the contract for *that* the declaration is invalid.

Nothing is added for handlers, `config` or the lifespan at runtime. `ToolHandler` and
`PageHandler` are Protocols admitting a callable object with an `async __call__`, so
`inspect.iscoroutinefunction` would refuse a legal handler; `type[ConfigT]` and `Lifespan` are
types. All three are the type checker's, and the type checker is run — see Studio below.

### Enforcement

The declaration is an allow-list, not a description. `PageRuntime.render` already binds the
render's principal into the invoker a Page receives; it now binds the Page's declared `tools`
as well. Invoking a name outside them raises `PageToolUndeclaredError` before `ToolRuntime` is
reached. This is Relay's data masking: a Page cannot use what it did not declare, so an App the
validator passed cannot fail at render with `tool.not_found` for a Tool its Page never named.

### What is removed

- `tool_registry_for` and `page_registry_for` no longer check names; they register.
- `adapters/nicegui/web.py` no longer checks routes; it registers. Route validation is thereby
  channel-neutral, which the third acceptance criterion requires.
- Their tests move to `AppDefinition` construction and assert every violation is reported.

### The process boundary

`report(error)` given an `AppDefinitionInvalidError` writes the aggregate as one line, then one
line per member, in order. The line format is unchanged and a reader already "takes what
validates and skips the rest", so `read_report_line` is unchanged. A single failure stays one
line. No fifth command is added: `describe` already imports the entrypoint, and its failure path
is where these lines come from — `authoring.md`'s "validate is inspect's failure path" becomes
permanently true rather than provisional.

`PageDescription` gains `tools: list[str]`, sorted, so what crosses the boundary carries the
relationship the declaration now states.

### Studio

`vibepy_studio.internals.processes.reported(text)` is widened to return every report line in
order, `tuple[ErrorInfo, ...]`; the two callers that show one failure (`invoke_tool`, the Hub's
child reader) take the first, which for a declaration failure is the aggregate and otherwise
the only line.

A new authoring Tool, Agent channel, beside `inspect_app`:

```python
class ValidateRequest(BaseModel):
    project: PurePath

class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"

class Diagnostic(BaseModel):
    severity: Severity
    error: ErrorInfo

class AppValidation(BaseModel):
    conforms: bool
    diagnostics: list[Diagnostic]
```

A `Diagnostic` is not an `ErrorInfo`. An `ErrorInfo` is a failure that happened and has no
degree; a diagnostic is a finding about a declaration and may be advisory, which is why LSP,
Django and Terraform all give one a severity and give a failure none. The framework's model
stays a failure; the authoring vocabulary wraps it once with the one field a finding adds.
`conforms` is `not any(d.severity is ERROR for d in diagnostics)`, Django's `--fail-level`
default, stated as a field so an agent does not recompute it.

`validate_app` runs two authorities in the project's environment and concatenates what they
report:

1. `uv run --project <dir> python -m vibepy_core.describe` — the declaration rules. On exit 1,
   every report line except the aggregate is a `Diagnostic` of severity `error`. On exit 0,
   none.
2. `sys.executable -m pyright --outputjson --pythonpath <project's interpreter> -p <dir> <dir>` —
   the typed contracts. Each `generalDiagnostics` entry is one `Diagnostic` whose severity is
   pyright's own, one to one, wrapping `ErrorInfo(code="authoring.type_error",
   category=DECLARATION, message=<pyright's message>, details={"file", "line", "rule"})`.
   Nothing pyright reports is dropped. Exit 0 and 1 are answers; 2, 3 and 4 are one `error`
   diagnostic, `authoring.environment_failed`, carrying pyright's output.

The project's own pyright configuration applies — `[tool.pyright]` in its `pyproject.toml` if
present, pyright's default `standard` otherwise, under which `reportArgumentType` is an error
and every contract above is caught. pyright is Studio's declared dependency, pinned by its own
lockfile, and the project's own files — `pyproject.toml`, lock and environment — are untouched;
`--pythonpath` points pyright's import resolution at the project's interpreter instead.

`validate_app` answers "what does not conform"; `inspect_app` keeps answering "what is
declared", and its `diagnostic: ErrorInfo | None` becomes `diagnostics: list[ErrorInfo]` — a
declaration that will not load has no single reason to pick. The `authoring.*` refusals
(`project_not_found`, `uv_unavailable`) are one diagnostic in either Tool, as today.

`docs/architecture/authoring.md`'s capability table changes accordingly: `validate_app` is
Studio's, M16; "type validation" is pyright, run by `validate_app`; `run_conformance_tests`
stays unassigned.

Studio's own `board` Page and the two fixture Pages (`todo-app`, `timer-app`) declare their
`tools`.

## Package layout

| Path | Change |
| --- | --- |
| `src/vibepy_core/page/model.py` | `PageDefinition.tools` |
| `src/vibepy_core/tool/model.py` | `ToolDefinition.__post_init__` |
| `src/vibepy_core/app/model.py` | `AppDefinition.__post_init__` and the rules it runs |
| `src/vibepy_core/app/composition.py` | name checks removed |
| `src/vibepy_core/adapters/nicegui/web.py` | route checks removed |
| `src/vibepy_core/page/runtime.py` | `_BoundInvoker` holds the declared names |
| `src/vibepy_core/app/entrypoint.py` | `PageDescription.tools` |
| `src/vibepy_core/errors.py` | four exceptions, four codes, `report` writes members |
| `packages/vibepy-studio/src/vibepy_studio/internals/processes.py` | `reported` returns all lines |
| `packages/vibepy-studio/src/vibepy_studio/authoring/models.py` | `ValidateRequest`, `Severity`, `Diagnostic`, `AppValidation`, `AppInspection.diagnostics`, `type_error` |
| `packages/vibepy-studio/src/vibepy_studio/authoring/internals/` | running pyright and reading its JSON |
| `packages/vibepy-studio/src/vibepy_studio/authoring/tools/validation.py` | `validate_app` |
| `packages/vibepy-studio/src/vibepy_studio/operating/pages/board.py`, `fixtures/*/entry.py` | `tools=` on each Page |

The rules import nothing from `vibepy_core.adapters`; `tests/test_app_isolation.py`'s pattern
proves it.

## Public API

Added: `PageDefinition.tools`, `PageDescription.tools`, `AppDefinitionInvalidError.errors`,
`ToolChannelsEmptyError`, `PageToolUnresolvedError`, `PageToolUndeclaredError`, the Studio Tool
`validate_app`.

Changed: `PageDefinition` requires `tools`; an invalid `AppDefinition` raises at construction
rather than when a window opens; `AppInspection.diagnostics` is a list. Pre-production, no
deprecation path (`AGENTS.md` keeps the API backward compatible once it is a product; it is not
yet).

## Data flow

```text
entry.py  ->  ToolDefinition(...)          refuses an empty channels
          ->  AppDefinition(...)           collects every cross-declaration violation, raises once
          ->  AppEntrypoint(...)

validate_app(project)
  -> uv run --project P python -m vibepy_core.describe
       exit 0: no declaration diagnostics
       exit 1: stderr = aggregate line + one line per violation  -> members become diagnostics
  -> sys.executable -m pyright --outputjson --pythonpath <interpreter> -p P P
       exit 0/1: every generalDiagnostics entry  -> authoring.type_error at pyright's severity
       exit 2-4: authoring.environment_failed, severity error
  -> AppValidation(conforms=<no error-severity diagnostic>, diagnostics=[...])

render(page)  ->  _BoundInvoker(principal, page.definition.tools)
              ->  invoke(name) with name not declared  ->  page.tool_undeclared
```

## Errors

| Code | Category | Exception | Raised |
| --- | --- | --- | --- |
| `app.declaration_invalid` | declaration | `AppDefinitionInvalidError` | `AppDefinition.__post_init__`; `details["count"]` and the member codes |
| `tool.channels_empty` | declaration | `ToolChannelsEmptyError` | `ToolDefinition.__post_init__` |
| `page.tool_unresolved` | declaration | `PageToolUnresolvedError` | inside the aggregate; `details`: page, tool, reason `missing` or `not_exposed` |
| `page.tool_undeclared` | caller | `PageToolUndeclaredError` | `PageRuntime`, at invoke; `details`: page, tool |
| `authoring.type_error` | declaration | — (Studio data) | `validate_app`, one per pyright diagnostic, at pyright's severity |

`page.route_invalid`, `page.route_conflict`, `tool.name_conflict`, `page.name_conflict` keep
their codes and are now raised inside the aggregate. No code is retired.

## Testing

Acceptance, in `tests/test_app_conformance.py` (one subject: what a declaration may be):

- an `AppDefinition` with one violation of each kind raises `AppDefinitionInvalidError` whose
  `errors` hold all of them, in declaration order, each with its own code and details
- an empty `channels` is refused by `ToolDefinition` alone
- a conforming definition constructs, and constructing it twice yields equal descriptions
- the rules module imports nothing under `vibepy_core.adapters`

Moved, not added: the two name-conflict tests in `tests/test_app_composition.py` and the two
route tests in `tests/test_nicegui_adapter.py` become construction tests.

`tests/test_page_core.py`: a Page invoking a Tool outside its `tools` raises
`page.tool_undeclared`; one inside reaches the Tool.

`tests/test_describe_command.py`: `describe` of a fixture whose declaration is invalid writes the
aggregate line and one line per violation, and exits 1. A conforming fixture describes with
`tools` on each Page.

Studio, `packages/vibepy-studio/tests/test_validate_app.py`: the four fixtures validate with
`conforms` true and no `error` diagnostic; a fixture with a broken declaration and a handler
missing `async` yields `conforms` false with one `page.tool_unresolved` and one
`authoring.type_error` naming the file and line, both `error`; a pyright warning arrives as a
`warning` diagnostic and leaves `conforms` true; a project without `pyproject.toml` yields
`authoring.project_not_found`. `test_authoring_over_mcp.py` lists
`validate_app`.

## Compatibility

Every App declaring a Page must add `tools=`; the framework is pre-production and the change is
made in the same commit for every App the repository holds. An App whose declaration violated a
rule now fails at import, where before it failed when a window opened; the codes it fails with
are the same, wrapped in `app.declaration_invalid`.

`Diagnostic` lives in Studio's authoring vocabulary because pyright is today the only producer
of a finding that is not an error. Should the framework itself one day report an advisory
finding, the type moves to `vibepy_core` unchanged; it is not placed there now, where it would
have no producer.

pyright and Node arrive with Studio's own installation. Offline, nothing more is downloaded; the
declaration diagnostics still arrive on their own, because the two authorities are run
independently.

## Documentation

- new ADR: *An App declaration validates itself at construction* — supersedes ADR-012's
  statement that the adapter validates routes; records why construction rather than a checker,
  why the type checker rather than runtime guards, and why the type checker is run by the
  authoring Tool
- `docs/architecture/errors.md`: five codes
- `docs/architecture/page-model.md`: `tools`, the allow-list, route validation no longer the adapter's
- `docs/architecture/tool-model.md`: `channels` is non-empty
- `docs/architecture/app-model.md`: construction validates; the window trusts
- `docs/architecture/adapters.md`: route validation sentence removed
- `docs/architecture/packaging.md`: a declaration failure is several lines; `PageDescription.tools`
- `docs/architecture/authoring.md`: `validate_app`, type validation's owner, the M16 markers resolved

## Out of scope

- invoking Tools as a conformance test (`run_conformance_tests`)
- a severity on `ErrorInfo` itself: a failure has none, a `Diagnostic` carries it
- invoking a Tool by object rather than by name (a change to ADR-016)
- widening `ErrorInfo.details` beyond strings
- a checking mode the framework imposes on a project
