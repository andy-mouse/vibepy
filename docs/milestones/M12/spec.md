# M12 - Authoring Core

Date: 2026-09-11

## Acceptance criteria

From `docs/roadmap.md`, verbatim:

- authoring clients can inspect and validate Apps through a channel-neutral service
- runtime verification uses the canonical framework runtime path
- Authoring Core does not depend on MCP-specific types

## Sources

| Contract | Source |
| --- | --- |
| Authoring semantics exist as a channel-neutral service before any MCP surface | `docs/architecture/authoring.md` |
| Authoring takes the Hub's position: a platform-tier App built on the framework | `docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md` |
| The product is `vibepy-core` and `vibepy-builder` beside the Hub | `docs/decisions/ADR-025-the-framework-implements-channel-neutrality-and-delegates-the-rest.md` — superseded by this milestone's ADR-032 |
| The Host never imports an App; loading happens in the App's own interpreter through a command | `docs/architecture/packaging.md`, isolation invariant |
| `describe` and `serve` are the two commands that cross that boundary, one JSON object of failure on stderr | `docs/architecture/packaging.md`, `docs/decisions/ADR-030-a-window-reports-its-own-failure.md` |
| Both channels converge at `ToolRuntime`; `tool_runtime_for` is the channel-neutral invocation window | `docs/architecture.md`, `docs/architecture/runtime.md`, `src/vibepy_core/app/composition.py` |
| An expected failure travels as data | `docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md` |
| Framework errors carry stable codes and a category | `docs/decisions/ADR-019-framework-errors-carry-stable-codes.md`, `src/vibepy_core/errors.py` |
| Where a library covers a problem the framework delegates; a mechanism written here carries its argument | `docs/decisions/ADR-025-the-framework-implements-channel-neutrality-and-delegates-the-rest.md` |
| `uv run` verifies lockfile and environment before every invocation; `--project` discovers a project outside CWD and other relative paths resolve against CWD | uv docs, `docs/guides/projects.md` and the `--project` CLI definition |
| MCP Resources are application-controlled context, Tools are model-controlled | MCP specification 2026-07-28, server overview |
| Authoring MCP must not duplicate a coding agent's native file editing | `docs/architecture/authoring.md` |
| Installing, starting and stopping an App are package-layer capabilities, not authoring ones | `docs/architecture/authoring.md`, `docs/architecture/lifecycle.md` |

## Problem

The Hub covers half of an App's life: a wheel that exists is installed, configured, addressed and
started. Nothing covers the other half, in which an agent writes an App and needs deterministic
feedback from the framework — what the framework's contracts are, what a project declares, and
whether a Tool it wrote behaves — without that agent importing the framework's internals or
reading this repository.

`docs/architecture/authoring.md` asks for that feedback as a channel-neutral service first.
ADR-025 placed it in a third distribution, `vibepy-builder`. The owner has since decided
otherwise: one App carries the whole lifecycle, consumption on its Web channel for humans and
authoring on its Agent channel for coding agents. That App is the Hub, renamed.

## Decision: Studio

The Hub is promoted into `vibepy-studio`, the App that covers both halves of an App's life. It
remains a platform-tier App (ADR-024): built on the framework, never depended on by it.

| Was | Becomes |
| --- | --- |
| distribution `vibepy-hub` | `vibepy-studio` |
| import package `vibepy_hub` | `vibepy_studio` |
| `app_id` `"vibepy-hub"` (also the MCP server name, `adapters/mcp/server.py`) | `"vibepy-studio"` |
| entry point `hub = "vibepy_hub.entry:APP"` | `studio = "vibepy_studio.entry:APP"` |
| `HubConfig`, `HubDeps` | `StudioConfig`, `StudioDeps` |
| `HubState`, the `board` Page, its "Hub" heading | unchanged; the consumption role keeps the name |
| `make hub`, `scripts/run_hub.py`, launch entry `hub` | `make studio`, `scripts/run_studio.py`, `studio` |

ADR-032 records the decision and supersedes ADR-025's distribution table: the product is two
distributions, `vibepy-core` and `vibepy-studio`, and `vibepy-builder` is never created. ADR-025's
body is untouched beyond its status line; ADR-024 stays true and is not touched; ADR-031's module
path reference is corrected as a broken reference.

### Package layout

Roles are the first axis, because the two roles are the two channels' users.

```text
vibepy_studio/
├─ entry.py                  # one App: STUDIO_APP, CONSUMPTION_TOOLS + AUTHORING_TOOLS
├─ models.py                 # shared: Diagnostic, Empty
├─ internals/                # shared: files, processes (run, ChildFailure), describing, deps
├─ consumption/              # humans, Web channel — the Hub as it is, moved
│  ├─ models.py
│  ├─ tools/    packages, installation, configuration, runtime
│  ├─ internals/ installer, wheels, routing, state, configuration
│  └─ pages/    board, presentation
└─ authoring/                # agents, Agent channel — new
   ├─ models.py              # requests, results, the authoring.* vocabulary
   ├─ tools/    inspection, invocation
   └─ internals/ projects   (running the two commands under uv)
```

`consumption/` is a move with no behaviour change. Its tests move with it and keep passing
before any authoring code lands.

## Authoring capabilities

Three Tools, in `AUTHORING_TOOLS`, channel-neutral like every Tool. Until M14 introduces per-channel
exposure they appear on both of Studio's channels, as the consumption Tools do.

| Tool | Input | Output |
| --- | --- | --- |
| `inspect_framework` | `Empty` | `FrameworkDescription` |
| `inspect_app` | `InspectRequest` | `AppInspection` |
| `invoke_tool` | `InvokeRequest` | `Invocation` |

### `inspect_framework`

What `vibepy_core` asserts about itself, read by import — Studio depends on the framework, so no
repository access and no packaged documentation is involved. Documentation reaches an agent by
other means (`docs/roadmap.md` M18 says "docs + Authoring MCP"; M19 owns Skills), so this Tool
carries none, and the framework does not ship its documents twice.

```python
class FrameworkDescription(BaseModel):
    framework_version: str          # importlib.metadata.version("vibepy-core")
    entry_point_group: str          # "vibepy.apps"
    channel_extras: list[str]       # ["web", "agent"]
    error_catalog: list[ErrorCode]  # every framework code and its category

class ErrorCode(BaseModel):
    code: str
    category: ErrorCategory
```

### `inspect_app`

The App an agent is authoring is a source project: a directory with a `pyproject.toml`, no wheel
and no installation. Studio must not import it, so it is read the way the Hub reads an installed
App — through a command run in the App's own environment — with uv supplying that environment:

```text
uv run --project <absolute project dir> python -m vibepy_core.describe
```

Inspection and validation are one Tool. What core validates today is that a declaration loads
(entry point resolves, is an `AppEntrypoint`, its Tools and Pages register without conflict), and
that is exactly the failure path of describing. A separate `validate_app` arrives with M16's
conformance checks, when there is something to validate that describing does not.

```python
class InspectRequest(BaseModel):
    project: Path

class InspectedApp(BaseModel):
    app_name: str
    distribution: str
    distribution_version: str
    app_id: str
    name: str
    version: str
    config_schema: dict[str, object]
    tools: list[InspectedTool]      # name, description, input_schema, output_schema
    pages: list[InspectedPage]      # name, route, title

class AppInspection(BaseModel):
    apps: list[InspectedApp]
    diagnostic: Diagnostic | None = None
```

Running `describe` and reading what it writes is one shared operation,
`internals/describing.describe(python: Sequence[str])`: consumption passes an installed
environment's interpreter, authoring passes `uv run --project <dir> python`, and both receive the
full shape the command writes (`Described`, every Tool schema included). Consumption's `_Described`,
which read only what installation needs, is replaced by deriving `AppFacts` from `Described`.

### `invoke_tool`

Runtime verification: one Tool of one declared App, invoked once, through the framework's own
invocation window.

```text
uv run --project <absolute project dir> python -m vibepy_core.invoke <app> <tool>
```

```python
class InvokeRequest(BaseModel):
    project: Path
    app: str                        # a project may declare several Apps
    tool: str
    input: dict[str, object] = {}
    config: dict[str, object] = {}  # what the App's lifespan requires; NoConfig Apps leave it empty

class Invocation(BaseModel):
    output: dict[str, object] | None = None
    diagnostic: Diagnostic | None = None
```

The caller supplies `config` because an App under authoring has no installation for Studio to
hold values for, and the agent writing the App knows what it requires. Studio keeps no authoring
state. Configuration failure is the child's `config.invalid`, as it is for `serve`.

`invoke_tool` opens no channel. The Web channel of a project is opened by the agent itself with
`python -m vibepy_core.serve` under `uv run`, a command that exists; wrapping it would duplicate
`start_app`. The Agent channel's server command does not exist yet and arrives with M13.

### Diagnostics

Every expected failure is data on the result (ADR-029). A framework failure the child reports on
stderr travels with its own code and category — `package.entrypoint_unloadable`,
`package.app_not_declared`, `config.invalid`, `tool.not_found`, `tool.input_invalid`,
`tool.output_invalid`, `app.unhandled`. Authoring adds four codes of its own, defined in
`vibepy_studio/authoring/models.py`:

| Code | Category | When |
| --- | --- | --- |
| `authoring.project_not_found` | caller | `project` holds no `pyproject.toml` |
| `authoring.uv_unavailable` | execution | `uv` is not runnable from Studio's process |
| `authoring.environment_failed` | execution | uv exited non-zero without a framework report; stderr is the message |
| `authoring.no_apps_declared` | declaration | the environment stood up and declares nothing in `vibepy.apps` |

## Core additions

### `python -m vibepy_core.invoke <app-name> <tool-name>`

The third command across the process boundary, shaped like `serve`.

- stdin: one JSON object `{"config": {...}, "input": {...}}`. Anything else is
  `InvokeRequestInvalidError`, code `invoke.request_invalid`, category caller.
- resolves the App, opens `tool_runtime_for(definition, lifespan, config=config)`, calls
  `ToolRuntime.invoke(tool, input)` once, writes the output model as JSON to stdout, exits 0. The
  window closes after the call; cleanup is `async with`'s.
- every `VibepyError` is one JSON object of `code`, `category`, `message`, `details` on stderr and
  exit 1. An exception from the lifespan or a handler is reported as `app.unhandled` through
  `to_error_info`, as ADR-030 has a window report its own failure.

Why a mechanism written here: only the framework knows how to open a window and invoke a Tool
through `ToolRuntime`. Environment, process and JSON are uv's, `asyncio`'s and the standard
library's.

### `load_app(app_name, /) -> AppEntrypoint`

`serve`'s private entry point resolution gains a second user, so it becomes a public function in
`vibepy_core/app/package.py`, exported from `vibepy_core`; `serve` and `invoke` both call it.
Raises `AppNotDeclaredError`, `AppEntrypointUnloadableError`, `AppEntrypointInvalidError`.

### `ERROR_CATALOG`

`errors.py`'s private code-to-category table becomes public, `app.unhandled` included, exported
from `vibepy_core`. The existing catalogue test asserts through the public name.

## Data flow

```text
agent -> Studio Tool (inspect_app | invoke_tool)
      -> authoring/internals/projects: absolute path, pyproject.toml present?
      -> internals/processes.run(["uv", "run", "--project", dir, "python", "-m", "vibepy_core.<cmd>", ...], stdin=json)
         -> uv syncs the project's environment and runs the command in it
         -> the command imports the App there, reports on stdout (result) or stderr (one JSON object)
      -> stdout parsed into Described[] | output; stderr's JSON object read by the shared
         ChildFailure reader into Diagnostic; unparsable stderr into authoring.environment_failed
      -> result returned as data
```

One runner, one describer and one failure reader serve both roles. Consumption's `_run` in `installer.py` was shaped for installation
alone — no stdin, both streams merged — and authoring needs stdin written and stderr read apart.
Rather than a second runner beside it, `internals/processes.py` gains
`run(command, /, *, stdin: str | None = None) -> Completed` (return code, stdout, stderr; the
runnable check moves with it), and `installer._run` becomes a call to it that keeps its own
contract: merged streams in the `InstallFailed` message. The reader of a child's failure report —
today `processes._Failure`/`ChildFailure` bound to a log file, with `tools/runtime._category`
beside it — becomes one public reader of text (`ChildFailure | None`) and one `category(str)` in
shared `internals/processes.py`; the log-file path and stderr both call it. Consumption tests do
not change.

## Testing

One file per subject; success and failure paths of a subject share its file.

| File | Subject |
| --- | --- |
| `tests/test_invoke_command.py` | the `invoke` command as a real process: `create_todo` output on stdout; `tool.not_found`, `tool.input_invalid`, `config.invalid`, `invoke.request_invalid`, `package.app_not_declared` each as one stderr object and exit 1 |
| `tests/test_app_package.py` | `load_app`'s three failures, with `impostor_fixture` and `write_distribution` |
| `tests/test_errors.py` | the catalogue through `ERROR_CATALOG` |
| `packages/vibepy-studio/tests/test_inspect_framework.py` | version equals `importlib.metadata`'s; catalogue equals core's |
| `packages/vibepy-studio/tests/test_inspect_app.py` | `fixtures/todo-app` yields three Tools, one Page, its config schema; a directory without `pyproject.toml` yields `authoring.project_not_found`; `fixtures/broken-app` yields `package.entrypoint_unloadable` as data |
| `packages/vibepy-studio/tests/test_invoke_tool.py` | `create_todo` then `list_todos` against `fixtures/todo-app` returns what was created — each call its own window, state surviving in the App's store; `tool.input_invalid` and `config.invalid` as data |
| existing Hub tests | moved under `packages/vibepy-studio/tests/`, renamed imports, same assertions |

`fixtures/broken-app` is a new workspace member whose entry point names an attribute that does
not exist. Fixtures are workspace members so that `uv run --project` resolves against the root
environment and needs no network; a project generated under `tmp_path` would need uv to resolve
`vibepy-core` and is not used.

## Compatibility

`vibepy-hub` and `vibepy_hub` cease to exist. No installation outside this repository exists, so
no deprecation period is owed. Consumption Tool names and schemas are unchanged. `load_app` and
`ERROR_CATALOG` are additions to the public API; `vibepy_core.invoke` is a new command.

## Documentation

- `docs/architecture/authoring.md`: the core section becomes current truth — Studio's Agent
  channel, the three Tools, a project directory as the target, `authoring.*` defined in
  `vibepy_studio/authoring/models.py`; the nine conceptual capabilities become a table naming the
  milestone each belongs to
- `docs/architecture/packaging.md`: the `invoke` command, `load_app`, no third distribution
- `docs/architecture/lifecycle.md`, `docs/architecture/app-model.md`: module paths; "Hub" stays
  where the consumption role is meant
- `docs/decisions/ADR-032-authoring-is-studios-agent-channel.md`; ADR-025 status line;
  ADR-031 path reference
- this folder is deleted on integration

## Out of scope

`validate_package`, `package_app` (`uv build` is the agent's), `run_app`, per-channel exposure
(M14), logs and errors observation (M15), conformance (M16), Studio's MCP server command (M13),
child-process timeout policy (M20; the runner is not bounded today).
