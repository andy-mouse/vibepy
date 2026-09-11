# M12 Authoring Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the Hub into `vibepy-studio` and give its Agent channel three authoring Tools — `inspect_framework`, `inspect_app`, `invoke_tool` — backed by a new core command `python -m vibepy_core.invoke`.

**Architecture:** One App, two roles as folders: `consumption/` (the Hub moved, unchanged in behaviour) and `authoring/` (new), over shared `internals/` (files, processes, describing, deps) and shared `models.py`. Authoring never imports the App it inspects: it runs `python -m vibepy_core.describe|invoke` under `uv run --project <dir>` and reads the child's stdout as data and its stderr as a framework diagnostic. Core grows `load_app`, `ERROR_CATALOG`, `report_line` and the `invoke` command.

**Tech Stack:** Python 3.12, pydantic 2, uv (project environments), pytest (asyncio_mode=auto), ruff, pyright strict.

## Global Constraints

- `make lint typecheck test` passes at the end of every task. `make lint` runs `ruff check .` and `ruff format --check .`; `make typecheck` runs pyright strict.
- `Any` and `cast` are not acceptable in the public API. Blocking calls inside async code are wrapped in `asyncio.to_thread`. Optional and configuration parameters are keyword-only. Paths are `pathlib.Path`. Standard `logging` only, `getLogger(__name__)` per module.
- One test file is one subject. Tests verify public contracts. A test that cannot fail is deleted.
- Docstrings: PEP 257 via ruff `D` rules in `src/` and `packages/*/src/`; not required in tests and fixtures.
- The word "Hub" in code and docstrings: where it means this App itself it becomes Studio; where it means the consumption role — its board, `hub.*` codes, `HubState`, the heading "VibePy Hub", Page title "Hub" — it stays. Each occurrence is read and decided.
- `docs/roadmap.md` is never edited. Accepted ADRs take only a status line or a broken-reference fix.
- Commit messages: one sentence in the style of `git log` (what became true), body optional, ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Work happens on branch `m12-authoring-core`, cut from `main` before Task 1.

---

## File structure after the milestone

```text
src/vibepy_core/
  errors.py            + InvokeRequestInvalidError, ERROR_CATALOG (public), report_line()
  app/package.py       + load_app(app_name)
  describe.py          failure written with report_line()
  serve.py             uses load_app() and report_line()
  invoke.py            NEW: python -m vibepy_core.invoke <app> <tool>
  __init__.py          exports ERROR_CATALOG, InvokeRequestInvalidError, load_app, report_line

packages/vibepy-studio/                       (was packages/vibepy-hub)
  pyproject.toml                              name vibepy-studio, entry point studio
  src/vibepy_studio/
    __init__.py
    entry.py                                  StudioConfig, StudioDeps lifespan, STUDIO_APP, APP
    models.py                                 shared: Diagnostic, Empty, category()
    internals/__init__.py
    internals/deps.py                         StudioDeps
    internals/files.py                        (moved)
    internals/processes.py                    (moved) + Completed, NotRunnable, is_runnable, run(), reported()
    internals/describing.py                   NEW: Described*, DescribeFailed, describe(python)
    consumption/__init__.py
    consumption/models.py                     (was models.py, less Diagnostic/Empty)
    consumption/tools/{__init__,packages,installation,configuration,runtime}.py
    consumption/internals/{__init__,installer,wheels,routing,state,configuration}.py
    consumption/pages/{__init__,board,presentation}.py, board.css
    authoring/__init__.py
    authoring/models.py                       NEW
    authoring/tools/{__init__,inspection,invocation}.py   NEW
    authoring/internals/{__init__,projects}.py            NEW
  tests/                                      (moved) + test_inspect_framework.py, test_inspect_app.py, test_invoke_tool.py

tests/
  test_invoke_command.py                      NEW
  test_app_package.py                         + load_app cases
  test_errors.py                              + InvokeRequestInvalidError row; ERROR_CATALOG

scripts/run_studio.py                         (was run_hub.py)
Makefile, .claude/launch.json, .gitignore, pyproject.toml, uv.lock
docs/architecture/{authoring,packaging,lifecycle,app-model}.md
docs/decisions/ADR-032-authoring-is-studios-agent-channel.md   NEW
docs/decisions/ADR-025-...md (status line), ADR-031-...md (path)
```

---

### Task 0: Cut the branch

**Files:** none

- [ ] **Step 1: Branch**

```bash
git checkout -b m12-authoring-core main
```

---

### Task 1: Rename the distribution and move consumption under its role

The mechanical move. No behaviour changes; every existing test passes with renamed imports.

**Files:**
- Move: `packages/vibepy-hub/` → `packages/vibepy-studio/`
- Move: `packages/vibepy-studio/src/vibepy_hub/` → `packages/vibepy-studio/src/vibepy_studio/`
- Create: `packages/vibepy-studio/src/vibepy_studio/consumption/__init__.py`, `.../models.py` (shared), `.../authoring/__init__.py` (empty for now)
- Modify: `pyproject.toml` (root), `packages/vibepy-studio/pyproject.toml`, `Makefile`, `.claude/launch.json`, `.gitignore`, `scripts/run_hub.py` → `scripts/run_studio.py`, `uv.lock` (regenerated)
- Modify: every `packages/vibepy-studio/tests/*.py` import

**Interfaces:**
- Produces: import roots `vibepy_studio.models` (Diagnostic, Empty), `vibepy_studio.internals` (StudioDeps, Processes, files, `child_environment`), `vibepy_studio.consumption.models`, `vibepy_studio.consumption.tools` (`HUB_TOOLS`), `vibepy_studio.consumption.internals`, `vibepy_studio.consumption.pages`, `vibepy_studio.entry` (`STUDIO_APP`, `APP`, `StudioConfig`, `studio_lifespan`).

- [ ] **Step 1: Move the tree with git**

```bash
cd /Users/andy.warhol/my-projects/vibepy
git mv packages/vibepy-hub packages/vibepy-studio
git mv packages/vibepy-studio/src/vibepy_hub packages/vibepy-studio/src/vibepy_studio
cd packages/vibepy-studio/src/vibepy_studio
mkdir consumption authoring
git mv models.py consumption/models.py
git mv tools consumption/tools
git mv pages consumption/pages
mkdir consumption/internals
for m in installer wheels routing state configuration; do git mv internals/$m.py consumption/internals/$m.py; done
git mv internals/__init__.py consumption/internals/__init__.py
touch internals/__init__.py consumption/__init__.py authoring/__init__.py
git add -A .
```

`internals/` now holds `deps.py`, `files.py`, `processes.py` and an empty `__init__.py`; `consumption/internals/__init__.py` is the old re-export list.

- [ ] **Step 2: Write the shared `models.py`**

Create `packages/vibepy-studio/src/vibepy_studio/models.py`:

```python
"""What both of Studio's roles say the same way: a diagnostic, and an empty input."""

from pydantic import BaseModel

from vibepy_core import ErrorCategory


class Diagnostic(BaseModel):
    """An expected, actionable failure, in the form a channel can render."""

    code: str
    category: ErrorCategory
    message: str
    details: dict[str, str] = {}


class Empty(BaseModel):
    """The input of a Tool that takes nothing."""
```

Remove the `Diagnostic` and `Empty` classes from `consumption/models.py` and add at its top `from vibepy_studio.models import Diagnostic` (it uses `Diagnostic` in `CandidateRow`, `SourceListing`, `AppRow`, `Installation`, `RunningApp`, `ConfigDescription`; `Empty` is not used there — check with grep and import only what is used).

- [ ] **Step 3: Rewrite imports and names across the package and tests**

```bash
cd /Users/andy.warhol/my-projects/vibepy/packages/vibepy-studio
FILES=$(grep -rl "vibepy_hub\|HubDeps\|HubConfig\|HUB_APP\|hub_lifespan" src tests)
sed -i '' \
  -e 's/vibepy_hub\.internals\.\(installer\|wheels\|routing\|state\|configuration\)/vibepy_studio.consumption.internals.\1/g' \
  -e 's/vibepy_hub\.internals\.\(deps\|files\|processes\)/vibepy_studio.internals.\1/g' \
  -e 's/vibepy_hub\.internals/vibepy_studio.consumption.internals/g' \
  -e 's/vibepy_hub\.tools/vibepy_studio.consumption.tools/g' \
  -e 's/vibepy_hub\.pages/vibepy_studio.consumption.pages/g' \
  -e 's/vibepy_hub\.models/vibepy_studio.consumption.models/g' \
  -e 's/vibepy_hub\.entry/vibepy_studio.entry/g' \
  -e 's/vibepy_hub/vibepy_studio/g' \
  -e 's/HubDeps/StudioDeps/g' -e 's/HubConfig/StudioConfig/g' \
  -e 's/HUB_APP/STUDIO_APP/g' -e 's/hub_lifespan/studio_lifespan/g' \
  $FILES
```

Then fix by hand what the sed cannot:

1. Every module that imports `Diagnostic` or `Empty` from `vibepy_studio.consumption.models` imports them from `vibepy_studio.models` instead (`consumption/tools/*.py`, `consumption/pages/*.py`, tests such as `test_presentation.py`). pyright names each remaining one.
2. `consumption/internals/__init__.py` re-exports `StudioDeps` from `vibepy_studio.internals.deps` and `Processes`, `AlreadyStarted`, `StartFailed` from `vibepy_studio.internals.processes`. Its `__all__` is unchanged apart from the `HubDeps` → `StudioDeps` rename the sed made.
3. `internals/deps.py` imports `Processes` from `vibepy_studio.internals.processes` (the sed produced that). Its docstring: "What one Studio window owns".
4. `entry.py`: `app_id="vibepy-studio"`, `name="Studio"`. `HUB_TOOLS` import path is `vibepy_studio.consumption.tools`; `BOARD` from `vibepy_studio.consumption.pages.board`. Module docstring: "The Studio App: one declaration, one lifespan, one composition root. Studio is a platform-tier App…".
5. `tests/tests_support.py`: rename the helper `hub(` → `studio(` and update its callers:

```bash
cd tests
grep -l '\bhub(' *.py | xargs sed -i '' -E 's/\bhub\(/studio(/g'
sed -i '' -E '/^from tests_support import/ s/\bhub\b/studio/' *.py
```

`tmp_path / "hub"` strings are directory names and stay.

- [ ] **Step 4: Tooling and configuration**

`packages/vibepy-studio/pyproject.toml`:

```toml
[project]
name = "vibepy-studio"
version = "0.1.0"
description = "The App that covers an App's whole life: consumption through its board, authoring through its Tools"
...
[project.entry-points."vibepy.apps"]
studio = "vibepy_studio.entry:APP"

[tool.hatch.build.targets.wheel]
packages = ["src/vibepy_studio"]
```

Root `pyproject.toml`: in `[dependency-groups].dev` replace `"vibepy-hub"` with `"vibepy-studio"`; in `[tool.uv.sources]` replace `vibepy-hub = { workspace = true }` with `vibepy-studio = { workspace = true }`; in `[tool.pytest.ini_options].pythonpath` replace `packages/vibepy-hub/tests` with `packages/vibepy-studio/tests`; in the comment above `-p` ("two test trees (root and vibepy-hub)") write `vibepy-studio`.

`Makefile`: rename target `hub` → `studio`, its recipe `uv run python scripts/run_studio.py`, `.PHONY` list, and the comment ("The Hub's board" → "Studio's board").

`git mv scripts/run_hub.py scripts/run_studio.py`; inside: `prog="run_studio"`, default root `REPO / ".studio-dev"`, the served app name `"studio"` in the `serve` argv, variable `hub` → `studio`, message `Studio board:`. Module docstring: `python -m vibepy_core.serve studio`, "Studio writes the proxy's install configuration".

`.gitignore`: `.hub-dev/` → `.studio-dev/`. `.claude/launch.json`: `"name": "studio"`, args `scripts/run_studio.py`.

- [ ] **Step 5: Regenerate the lock and run the gate**

```bash
cd /Users/andy.warhol/my-projects/vibepy
uv lock && uv sync
make lint typecheck test
```

Expected: all pass. Tests that assert `app_id == "vibepy-hub"` or the App name, if any, fail here and are updated to `vibepy-studio` / `Studio`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "The Hub becomes Studio, its consumption role moved under a folder of its own

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Read every "Hub" and decide it

**Files:**
- Modify: every `.py` under `packages/vibepy-studio/src/vibepy_studio/` and `packages/vibepy-studio/tests/` containing `Hub`

- [ ] **Step 1: List occurrences**

```bash
grep -rn "Hub" packages/vibepy-studio/src packages/vibepy-studio/tests
```

- [ ] **Step 2: Apply the rule to each**

Becomes Studio (this App itself): "the Hub must not import an App", "the Hub's own process", "this Hub's environments", "One Hub window", "What one Hub window owns", "the Hub exists to provide", "the Hub composes a child's environment", "the Hub reaches an environment only through its interpreter", "the Hub's tests", "a Hub root", "two Hubs never share one".

Stays (the consumption role): `hub.*` codes and their table in `consumption/models.py`, `HubState`, `HUB_TOOLS`, "VibePy Hub" heading and Page title "Hub" in `board.py`, "what the Hub holds" where it means the held configuration/ports/routes, "Hub Core" as the roadmap's name of the consumption Tools.

Where "the Hub" is the actor doing installation, starting or stopping (the consumption role's own work), either reading is true; leave it.

- [ ] **Step 3: Gate and commit**

```bash
make lint typecheck test
git commit -am "Hub names the consumption role; Studio names the App

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: `ERROR_CATALOG`, `report_line`, `InvokeRequestInvalidError`

**Files:**
- Modify: `src/vibepy_core/errors.py`
- Modify: `src/vibepy_core/__init__.py`
- Modify: `src/vibepy_core/serve.py` (use `report_line`)
- Modify: `src/vibepy_core/describe.py` (use `report_line`)
- Test: `tests/test_errors.py`, `tests/test_describe_command.py`

**Interfaces:**
- Produces: `ERROR_CATALOG: Mapping[str, ErrorCategory]`, `report_line(info: ErrorInfo, /) -> str`, `InvokeRequestInvalidError` (code `invoke.request_invalid`, category caller), all exported from `vibepy_core`.

- [ ] **Step 1: Failing tests**

In `tests/test_errors.py`, add to `CASES` (after the `ServeConfigInvalidError` row):

```python
    (
        InvokeRequestInvalidError(),
        "invoke.request_invalid",
        ErrorCategory.CALLER,
        {},
    ),
```

and import it. Add:

```python
def test_the_catalogue_is_public_and_includes_the_unhandled_code() -> None:
    assert ERROR_CATALOG["app.unhandled"] == ErrorCategory.EXECUTION
    for error, code, category, _ in CASES:
        assert ERROR_CATALOG[code] == category


def test_a_report_line_is_one_json_object_of_the_four_fields() -> None:
    line = report_line(to_error_info(ToolNotFoundError("create_todo")))
    assert line.endswith("\n")
    assert json.loads(line) == {
        "code": "tool.not_found",
        "category": "caller",
        "message": str(ToolNotFoundError("create_todo")),
        "details": {"tool_name": "create_todo"},
    }
```

Where the file currently reaches the private table (grep `_CATEGORIES`), switch to `ERROR_CATALOG`.

In `tests/test_describe_command.py`, find the test that asserts the failure written to stderr and extend its assertion to the four fields:

```python
    reported = json.loads(result.stderr)
    assert reported["code"] == "package.entrypoint_unloadable"
    assert reported["category"] == "declaration"
    assert set(reported) == {"code", "category", "message", "details"}
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/test_errors.py tests/test_describe_command.py -q
```

Expected: ImportError on `ERROR_CATALOG` / `report_line` / `InvokeRequestInvalidError`.

- [ ] **Step 3: Implement**

`src/vibepy_core/errors.py` — after `ServeConfigInvalidError`:

```python
class InvokeRequestInvalidError(VibepyError):
    """Standard input did not carry one JSON object of `config` and `input`."""

    code = "invoke.request_invalid"

    def __init__(self) -> None:
        """State that standard input was not one JSON object of config and input."""
        super().__init__("The request on standard input is not a JSON object of config and input")
```

Rename `_CATEGORIES` to `ERROR_CATALOG`, add `InvokeRequestInvalidError.code: ErrorCategory.CALLER` and `UNHANDLED_CODE: ErrorCategory.EXECUTION` to it, with a docstring:

```python
ERROR_CATALOG: Mapping[str, ErrorCategory] = {...}
"""Every framework code and its category, `app.unhandled` included.

Public so that a reader outside the framework — an authoring Tool describing
the framework to an agent — states the same catalogue this module classifies by.
"""
```

`to_error_info` keeps its behaviour: it reads `ERROR_CATALOG.get(code)`; because `app.unhandled` is now in the table, nothing changes for `VibepyError` subclasses without a code (their `code` is not a `str`).

Add, at the bottom, with `import json` at the top:

```python
def report_line(info: ErrorInfo, /) -> str:
    """One failure as the line a command writes to standard error.

    `describe`, `serve` and `invoke` write it, and a host reads all three with
    one reader, which is why the shape lives here and not in each command.
    """
    return (
        json.dumps(
            {
                "code": info.code,
                "category": info.category,
                "message": info.message,
                "details": dict(info.details),
            }
        )
        + "\n"
    )
```

`src/vibepy_core/serve.py`: `_reported` becomes `sys.stderr.write(report_line(to_error_info(error)))`. `src/vibepy_core/describe.py`: replace the `sys.stderr.write(json.dumps({...}))` with `sys.stderr.write(report_line(info))`; drop the now-unused `json` import if nothing else uses it.

`src/vibepy_core/__init__.py`: import and list `ERROR_CATALOG`, `InvokeRequestInvalidError`, `report_line` in `__all__` (alphabetical).

- [ ] **Step 4: Run, expect pass; gate; commit**

```bash
make lint typecheck test
git add -A
git commit -m "The error catalogue is public, and three commands report one line shape

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: `load_app`

**Files:**
- Modify: `src/vibepy_core/app/package.py`, `src/vibepy_core/app/__init__.py`, `src/vibepy_core/__init__.py`
- Modify: `src/vibepy_core/serve.py` (remove `_entrypoint`, `_is_entrypoint`; use `load_app`)
- Test: `tests/test_app_package.py`

**Interfaces:**
- Produces: `load_app(app_name: str, /) -> AppEntrypoint[object, BaseModel]`, raising `AppNotDeclaredError`, `AppEntrypointUnloadableError`, `AppEntrypointInvalidError`.

- [ ] **Step 1: Failing tests**

Append to `tests/test_app_package.py` (it already has `write_distribution`, `write_module`, and a way to put a directory on the path — reuse whatever helper the existing `describe_app` failure tests use, typically `monkeypatch.syspath_prepend(tmp_path)` plus `discover_apps(path=...)`; here `load_app` searches the running interpreter, so the distribution is placed on `sys.path`):

```python
def test_load_app_returns_the_declared_entrypoint() -> None:
    loaded = load_app("todo-app")
    assert loaded.definition.app_id == "todo-app"


def test_load_app_refuses_an_app_this_environment_does_not_declare() -> None:
    with pytest.raises(AppNotDeclaredError) as raised:
        load_app("no-such-app")
    assert raised.value.details() == {"app_name": "no-such-app"}


def test_load_app_reports_an_entrypoint_that_will_not_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_distribution(
        tmp_path, distribution="ghost-app", version="0.1", entries=[("ghost", "ghost_app.entry:APP")]
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(AppEntrypointUnloadableError):
        load_app("ghost")


def test_load_app_reports_an_entrypoint_that_is_not_an_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_distribution(
        tmp_path,
        distribution="impostor-app",
        version="0.1",
        entries=[("impostor", "impostor_fixture:IMPOSTOR")],
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(AppEntrypointInvalidError):
        load_app("impostor")
```

`impostor_fixture` is importable from `tests/` (pytest `pythonpath`). `importlib.metadata.distributions()` reads `sys.path` at call time, so `syspath_prepend` is enough; if `discover_apps` caches nothing, these pass once implemented.

- [ ] **Step 2: Run, expect ImportError**

```bash
uv run pytest tests/test_app_package.py -q
```

- [ ] **Step 3: Implement**

In `src/vibepy_core/app/package.py`, factor the load out of `describe_app` and add `load_app`:

```python
def _load(ref: AppRef, /) -> AppEntrypoint[object, BaseModel]:
    """Import one declared entrypoint and check it is one."""
    reference = f"{ref.module}:{ref.attr}"
    entry = EntryPoint(name=ref.app_name, value=reference, group=APP_GROUP)
    try:
        loaded: object = entry.load()
    except (ImportError, AttributeError) as error:
        raise AppEntrypointUnloadableError(ref.app_name, reference) from error
    if not _is_entrypoint(loaded):
        raise AppEntrypointInvalidError(ref.app_name, reference, type(loaded).__name__)
    return loaded


def _is_entrypoint(value: object, /) -> TypeGuard[AppEntrypoint[object, BaseModel]]:
    """Whether what a reference resolved to is a composition root.

    A runtime check cannot see type arguments, and this module never constructs
    a definition or calls a lifespan itself, so the widest pair is a sound
    reading of what was found.
    """
    return isinstance(value, AppEntrypoint)


def describe_app(ref: AppRef, /) -> AppDescription:
    """Load one declared entrypoint and project it. ...(keep the docstring)"""
    return _load(ref).describe()


def load_app(app_name: str, /) -> AppEntrypoint[object, BaseModel]:
    """Load the App this interpreter's environment declares under `app_name`.

    This imports, so it belongs in the App's own environment: `serve` and
    `invoke` call it there, and a host reaches it only through them.

    Raises:
        AppNotDeclaredError: nothing in this environment declares `app_name`.
        AppEntrypointUnloadableError: the reference does not import.
        AppEntrypointInvalidError: the reference is not an `AppEntrypoint`.
    """
    for ref in discover_apps():
        if ref.app_name == app_name:
            return _load(ref)
    raise AppNotDeclaredError(app_name)
```

Imports needed: `from typing import TypeGuard`, `from pydantic import BaseModel`, `AppNotDeclaredError` from `vibepy_core.errors`.

`src/vibepy_core/serve.py`: delete `_is_entrypoint`, `_entrypoint`, the `EntryPoint`/`TypeGuard`/`APP_GROUP`/`discover_apps` imports they needed; `main` calls `load_app(str(parsed.app_name))` inside the same `except (AppNotDeclaredError, AppEntrypointUnloadableError, AppEntrypointInvalidError)`.

Export `load_app` from `vibepy_core/app/__init__.py` and `vibepy_core/__init__.py`.

- [ ] **Step 4: Gate and commit**

```bash
make lint typecheck test
git add -A
git commit -m "An App is loaded by name in one place, which serve now calls

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `python -m vibepy_core.invoke`

**Files:**
- Create: `src/vibepy_core/invoke.py`
- Test: `tests/test_invoke_command.py`
- Modify: `docs/architecture/packaging.md` (the command's section — written in Task 12; not here)

**Interfaces:**
- Consumes: `load_app`, `report_line`, `to_error_info`, `InvokeRequestInvalidError`, `tool_runtime_for`.
- Produces: the command. stdin `{"config": {...}, "input": {...}}`; stdout one JSON object (the Tool's output) and exit 0; stderr one report line and exit 1.

- [ ] **Step 1: Failing tests**

`tests/test_invoke_command.py`:

```python
"""The command that invokes one Tool of an App, run as a real process."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_serve_command import child_environment


def run_invoke(app: str, tool: str, request: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "vibepy_core.invoke", app, tool],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        env=child_environment(),
        check=False,
    )


def todo_config(tmp_path: Path) -> dict[str, str]:
    return {"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}


def reported(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 1, result.stderr
    lines = [line for line in result.stderr.splitlines() if line.startswith("{")]
    assert lines, result.stderr
    return json.loads(lines[-1])


@pytest.mark.integration
def test_a_tool_is_invoked_and_its_output_written(tmp_path: Path) -> None:
    result = run_invoke(
        "todo-app", "create_todo", {"config": todo_config(tmp_path), "input": {"title": "milk"}}
    )
    assert result.returncode == 0, result.stderr
    written = json.loads(result.stdout)
    assert written["title"] == "milk"
    assert written["done"] is False


@pytest.mark.integration
def test_a_second_invocation_sees_what_the_first_wrote(tmp_path: Path) -> None:
    config = todo_config(tmp_path)
    run_invoke("todo-app", "create_todo", {"config": config, "input": {"title": "milk"}})
    result = run_invoke("todo-app", "list_todos", {"config": config, "input": {}})
    assert result.returncode == 0, result.stderr
    assert [todo["title"] for todo in json.loads(result.stdout)["todos"]] == ["milk"]


@pytest.mark.integration
def test_an_unknown_tool_is_reported(tmp_path: Path) -> None:
    result = run_invoke("todo-app", "no_such_tool", {"config": todo_config(tmp_path), "input": {}})
    report = reported(result)
    assert report["code"] == "tool.not_found"
    assert report["category"] == "caller"
    assert result.stdout == ""


@pytest.mark.integration
def test_invalid_input_is_reported(tmp_path: Path) -> None:
    result = run_invoke("todo-app", "create_todo", {"config": todo_config(tmp_path), "input": {}})
    assert reported(result)["code"] == "tool.input_invalid"


@pytest.mark.integration
def test_invalid_configuration_is_reported() -> None:
    result = run_invoke("todo-app", "list_todos", {"config": {}, "input": {}})
    assert reported(result)["code"] == "config.invalid"


@pytest.mark.integration
def test_a_request_that_is_not_an_object_is_reported() -> None:
    result = run_invoke("todo-app", "list_todos", [1, 2])
    assert reported(result)["code"] == "invoke.request_invalid"


@pytest.mark.integration
def test_an_app_this_environment_does_not_declare_is_reported() -> None:
    result = run_invoke("no-such-app", "list_todos", {"config": {}, "input": {}})
    assert reported(result)["code"] == "package.app_not_declared"
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/test_invoke_command.py -q
```

Expected: every test fails with `No module named vibepy_core.invoke` in stderr (returncode 1 but no `{` line).

- [ ] **Step 3: Implement `src/vibepy_core/invoke.py`**

```python
"""Invoke one Tool of one App, in that App's own environment.

`vibepy_core.describe` reads a declaration and `vibepy_core.serve` runs its Web
channel; this opens the channel-neutral invocation window once, calls one Tool
through ToolRuntime, and closes the window. It is how a host that must not import
an App verifies that a Tool behaves.
"""

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from vibepy_core.app.composition import tool_runtime_for
from vibepy_core.app.entrypoint import AppEntrypoint
from vibepy_core.app.package import load_app
from vibepy_core.errors import (
    AppEntrypointInvalidError,
    AppEntrypointUnloadableError,
    AppNotDeclaredError,
    InvokeRequestInvalidError,
    report_line,
    to_error_info,
)

logger = logging.getLogger(__name__)


class _Request(BaseModel):
    """What standard input carries: the App's configuration and the Tool's input."""

    config: dict[str, object] = {}
    input: dict[str, object] = {}


def _reported(error: Exception, /) -> None:
    """Write one failure where whatever started this process can read it."""
    sys.stderr.write(report_line(to_error_info(error)))


async def _invoke(
    entrypoint: AppEntrypoint[object, BaseModel], tool_name: str, request: _Request, /
) -> BaseModel:
    """Open the window, invoke once, close the window."""
    async with tool_runtime_for(
        entrypoint.definition, entrypoint.lifespan, config=request.config
    ) as runtime:
        return await runtime.invoke(tool_name, request.input)


def main(argv: Sequence[str], /) -> int:
    """Read a request from standard input and invoke one Tool.

    Exits 0 with the Tool's output as one JSON object on standard output. Exits 1
    with one report line on standard error for any failure: a request that is
    not an object, an App this environment does not declare or cannot load,
    configuration the window refuses, a Tool the App does not declare, input or
    output its models reject, and anything the lifespan or handler raised,
    which is reported as `app.unhandled`.
    """
    parser = argparse.ArgumentParser(prog="vibepy_core.invoke")
    parser.add_argument("app_name")
    parser.add_argument("tool_name")
    parsed = parser.parse_args(argv)
    try:
        request = _Request.model_validate_json(sys.stdin.read() or "{}")
    except ValidationError as invalid:
        _reported(InvokeRequestInvalidError())
        logger.debug("the request on standard input was unreadable", exc_info=invalid)
        return 1
    try:
        entrypoint = load_app(str(parsed.app_name))
    except (AppNotDeclaredError, AppEntrypointUnloadableError, AppEntrypointInvalidError) as error:
        _reported(error)
        return 1
    try:
        result = asyncio.run(_invoke(entrypoint, str(parsed.tool_name), request))
    except Exception as error:  # noqa: BLE001 — the window reports its own failure (ADR-030)
        _reported(error)
        logger.debug("the invocation failed", exc_info=error)
        return 1
    sys.stdout.write(json.dumps(result.model_dump(mode="json")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

If ruff does not select `BLE`, drop the `noqa` comment but keep the sentence as a plain comment.

- [ ] **Step 4: Gate and commit**

```bash
make lint typecheck test
git add -A
git commit -m "A Tool is invoked once through the framework's own window, from outside the App's process

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: One runner and one failure reader in shared `internals/processes.py`

**Files:**
- Modify: `packages/vibepy-studio/src/vibepy_studio/internals/processes.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/models.py` (add `category`)
- Modify: `packages/vibepy-studio/src/vibepy_studio/consumption/internals/installer.py` (`_run` calls the shared runner; `_is_runnable` removed)
- Modify: `packages/vibepy-studio/src/vibepy_studio/consumption/tools/runtime.py` (`_category` removed; uses `category` from `vibepy_studio.models`)
- Modify: `packages/vibepy-studio/src/vibepy_studio/internals/__init__.py` (exports)
- Test: `packages/vibepy-studio/tests/test_processes.py` (add the runner's and reader's contract)

**Interfaces:**
- Produces:
  - `Completed(returncode: int, stdout: str, stderr: str)` frozen dataclass
  - `NotRunnable(program: str)` exception
  - `is_runnable(program: str, /) -> bool`
  - `async run(command: Sequence[str], /, *, stdin: str | None = None) -> Completed` — raises `NotRunnable`; every child gets `child_environment()`
  - `reported(text: str, /) -> ChildFailure | None` — the last JSON line carrying `code`
  - `vibepy_studio.models.category(reported: str, /) -> ErrorCategory` — the child's category, or `EXECUTION` for one the framework does not know

- [ ] **Step 1: Failing tests** — append to `test_processes.py`:

```python
async def test_run_returns_both_streams_and_the_exit_code() -> None:
    completed = await run(
        [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"]
    )
    assert completed.returncode == 3
    assert completed.stdout.strip() == "out"
    assert completed.stderr.strip() == "err"


async def test_run_hands_the_child_standard_input() -> None:
    completed = await run(
        [sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"], stdin="hello"
    )
    assert completed.stdout.strip() == "HELLO"


async def test_run_refuses_a_program_that_is_not_there() -> None:
    with pytest.raises(NotRunnable):
        await run(["no-such-program-anywhere"])


def test_reported_reads_the_last_report_among_other_lines() -> None:
    text = 'noise\n{"code": "tool.not_found", "category": "caller", "message": "m", "details": {}}\nTraceback\n'
    found = reported(text)
    assert found is not None
    assert found.code == "tool.not_found"
    assert found.category == "caller"
    assert reported("nothing here") is None


def test_category_of_a_report_the_framework_does_not_know_is_execution() -> None:
    assert category("caller") == ErrorCategory.CALLER
    assert category("weird") == ErrorCategory.EXECUTION
```

Imports: `sys`, `pytest`, `from vibepy_studio.internals.processes import NotRunnable, reported, run`, `from vibepy_studio.models import category`, `from vibepy_core import ErrorCategory`.

- [ ] **Step 2: Run, expect ImportError**

```bash
uv run pytest packages/vibepy-studio/tests/test_processes.py -q
```

- [ ] **Step 3: Implement**

`internals/processes.py` — add after `child_environment`:

```python
@dataclass(frozen=True)
class Completed:
    """What one finished child left: its exit code and both streams, decoded."""

    returncode: int
    stdout: str
    stderr: str


class NotRunnable(Exception):
    """The program a command names is neither on PATH nor a file."""

    def __init__(self, program: str) -> None:
        """Record `program` for the message."""
        super().__init__(f"{program} is not available")
        self.program = program


def is_runnable(program: str, /) -> bool:
    """Whether a program is on PATH or is itself a file, as an environment's Python is."""
    return shutil.which(program) is not None or Path(program).is_file()


async def run(command: Sequence[str], /, *, stdin: str | None = None) -> Completed:
    """Run one command to completion and return what it left.

    Every child receives `child_environment()`, so what describes Studio's own
    process describes no child. Both streams are read apart: a reader that wants
    them merged joins them, and one that wants a report finds it on standard error.
    """
    if not await asyncio.to_thread(is_runnable, command[0]):
        raise NotRunnable(command[0])
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL if stdin is None else asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=child_environment(),
    )
    out, err = await process.communicate(None if stdin is None else stdin.encode())
    return Completed(
        returncode=process.returncode if process.returncode is not None else 0,
        stdout=out.decode(errors="replace"),
        stderr=err.decode(errors="replace"),
    )


def reported(text: str, /) -> ChildFailure | None:
    """Return the failure a child described in `text`, found by parsing, not position.

    The report is one line among whatever else the child wrote, and a traceback
    the framework writes after it is as much a part of that output as the report.
    Scanning in reverse finds the report regardless of what follows it.
    """
    for line in reversed(text.splitlines()):
        try:
            parsed = _FAILURE.validate_json(line)
        except ValidationError:
            continue
        return ChildFailure(
            code=parsed.code, category=parsed.category, message=parsed.message, details=parsed.details
        )
    return None
```

`_reported(path)` becomes: read the file (existing `try/except OSError`), then `return reported(written)`. Add `import shutil` and `from collections.abc import Mapping, Sequence`.

`models.py` — add:

```python
import logging

logger = logging.getLogger(__name__)


def category(reported: str, /) -> ErrorCategory:
    """Return the category a child named, or execution when it named one we do not know."""
    try:
        return ErrorCategory(reported)
    except ValueError:
        logger.debug("a child reported an unknown category: %s", reported)
        return ErrorCategory.EXECUTION
```

`consumption/internals/installer.py` — replace `_is_runnable` and `_run`:

```python
async def _run(command: Sequence[str], /) -> str:
    """One command, its output, and a failure that says which step it was."""
    try:
        completed = await run(command)
    except NotRunnable as absent:
        raise InstallFailed(command[0], str(absent)) from absent
    written = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise InstallFailed(" ".join(command[:2]), written.strip())
    return completed.stdout
```

Note the return: callers parse stdout (`purelib` reads a path, `describe` reads JSON), so a success returns stdout alone. Import `from vibepy_studio.internals.processes import NotRunnable, run`; drop `shutil` if now unused.

`consumption/tools/runtime.py` — delete `_category`, import `category` from `vibepy_studio.models`, call `category(reported.category)`.

`internals/__init__.py` — export `Completed`, `NotRunnable`, `Processes`, `AlreadyStarted`, `StartFailed`, `ChildFailure`, `StudioDeps`, `child_environment`, `is_runnable`, `reported`, `run`.

- [ ] **Step 4: Gate and commit**

```bash
make lint typecheck test
git add -A
git commit -m "One runner and one failure reader, shared by both of Studio's roles

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: One describer in shared `internals/describing.py`

**Files:**
- Create: `packages/vibepy-studio/src/vibepy_studio/internals/describing.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/consumption/internals/installer.py` (`describe(env)` derives `AppFacts` from the shared result; `_Described` removed)
- Modify: `packages/vibepy-studio/src/vibepy_studio/internals/__init__.py`
- Test: `packages/vibepy-studio/tests/test_describing.py` (new subject: reading a declaration out of an environment)

**Interfaces:**
- Produces:
  - `DescribedTool(name, description, input_schema: dict[str, object], output_schema: dict[str, object])`
  - `DescribedPage(name, route, title)`
  - `Described(app_name, distribution, distribution_version, app_id, name, version, config_schema: dict[str, object] = {}, tools: list[DescribedTool] = [], pages: list[DescribedPage] = [])` — pydantic models
  - `DescribeFailed(output: str, *, reported: ChildFailure | None)` exception
  - `async describe(python: Sequence[str], /) -> tuple[Described, ...]` — runs `[*python, "-m", "vibepy_core.describe"]`; raises `NotRunnable`, `DescribeFailed`

- [ ] **Step 1: Failing tests** — `packages/vibepy-studio/tests/test_describing.py`:

```python
"""Reading what an environment declares, through the framework's own command."""

import sys

import pytest

from vibepy_studio.internals.describing import DescribeFailed, describe
from vibepy_studio.internals.processes import NotRunnable


@pytest.mark.integration
async def test_the_running_environment_describes_its_apps_with_their_tools() -> None:
    described = await describe([sys.executable])
    todo = next(entry for entry in described if entry.app_name == "todo-app")
    assert todo.distribution == "vibepy-todo"
    assert sorted(tool.name for tool in todo.tools) == ["create_todo", "list_todos"]
    assert "properties" in next(t for t in todo.tools if t.name == "create_todo").input_schema
    assert [page.route for page in todo.pages] == ["/todos"]


async def test_a_python_that_is_not_there_is_not_runnable() -> None:
    with pytest.raises(NotRunnable):
        await describe(["no-such-python"])


@pytest.mark.integration
async def test_a_python_without_the_framework_fails_to_describe() -> None:
    with pytest.raises(DescribeFailed) as failed:
        await describe([sys.executable, "-S", "-c", "import sys; sys.exit(2)", "--"])
    assert failed.value.reported is None
```

The third test's command is `python -S -c "..." -- -m vibepy_core.describe`: the `-c` program exits 2 before anything else, so the runner sees exit 2 and no report. If the argument order makes `-c` swallow `-m`, that is fine — the exit code is what is asserted.

- [ ] **Step 2: Run, expect ImportError**

- [ ] **Step 3: Implement `internals/describing.py`**

```python
"""Reading what an environment declares, without importing any of it.

`python -m vibepy_core.describe` is run with the environment's own Python and its
output read here. The consumption role passes an installed environment's
interpreter; the authoring role passes `uv run --project <dir> python`. Both get
the whole shape the command writes.
"""

import logging
from collections.abc import Sequence

from pydantic import BaseModel, TypeAdapter, ValidationError

from vibepy_studio.internals.processes import ChildFailure, reported, run

logger = logging.getLogger(__name__)


class DescribedTool(BaseModel):
    """One Tool, as `describe` writes it."""

    name: str
    description: str
    input_schema: dict[str, object]
    output_schema: dict[str, object]


class DescribedPage(BaseModel):
    """One Page, as `describe` writes it."""

    name: str
    route: str
    title: str


class Described(BaseModel):
    """One entry of what `describe` writes: the declaration's identity and its description."""

    app_name: str
    distribution: str
    distribution_version: str
    app_id: str
    name: str
    version: str
    config_schema: dict[str, object] = {}
    tools: list[DescribedTool] = []
    pages: list[DescribedPage] = []


_DESCRIBED = TypeAdapter(list[Described])


class DescribeFailed(Exception):
    """The command did not describe. Carries what it wrote and any report among it."""

    def __init__(self, output: str, *, reported: ChildFailure | None) -> None:
        """Record `output` for the message and the child's `reported` failure, if any."""
        super().__init__(output)
        self.output = output
        self.reported = reported


async def describe(python: Sequence[str], /) -> tuple[Described, ...]:
    """Return what the environment `python` runs in declares.

    Raises:
        NotRunnable: `python[0]` is not a program.
        DescribeFailed: the command exited non-zero, or wrote something that is
            not a list of descriptions.
    """
    completed = await run([*python, "-m", "vibepy_core.describe"])
    if completed.returncode != 0:
        raise DescribeFailed(
            (completed.stdout + completed.stderr).strip(), reported=reported(completed.stderr)
        )
    try:
        return tuple(_DESCRIBED.validate_json(completed.stdout))
    except ValidationError as invalid:
        raise DescribeFailed(str(invalid), reported=None) from invalid
```

`consumption/internals/installer.py` — remove `_Described`, `_DESCRIBED`; `describe(env)` becomes:

```python
async def describe(env: Path, /) -> tuple[AppFacts, ...]:
    """Return what the Apps in one environment declare, read in that environment."""
    try:
        described = await describe_with([str(interpreter(env))])
    except (NotRunnable, DescribeFailed) as failure:
        raise InstallFailed("vibepy_core.describe", str(failure)) from failure
    return tuple(
        AppFacts(
            app_id=entry.app_id,
            name=entry.name,
            version=entry.version,
            distribution_version=entry.distribution_version,
            config_schema=entry.config_schema,
            has_pages=bool(entry.pages),
            declared_name=entry.app_name,
            distribution=entry.distribution,
        )
        for entry in described
    )
```

with `from vibepy_studio.internals.describing import DescribeFailed, describe as describe_with`. Drop `TypeAdapter`/`ValidationError`/`BaseModel` imports if unused. Export `Described`, `DescribedPage`, `DescribedTool`, `DescribeFailed`, `describe` from `internals/__init__.py`.

- [ ] **Step 4: Gate and commit**

```bash
make lint typecheck test
git add -A
git commit -m "One describer reads the whole declaration, and installation derives its facts from it

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Authoring models and `inspect_framework`

**Files:**
- Create: `packages/vibepy-studio/src/vibepy_studio/authoring/models.py`
- Create: `packages/vibepy-studio/src/vibepy_studio/authoring/tools/__init__.py`, `.../tools/inspection.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/entry.py` (tools = `[*HUB_TOOLS, *AUTHORING_TOOLS]`)
- Test: `packages/vibepy-studio/tests/test_inspect_framework.py`

**Interfaces:**
- Produces: `AUTHORING_TOOLS: Sequence[Tool[StudioDeps]]`; models `FrameworkDescription`, `ErrorCode`, `InspectRequest`, `InspectedTool`, `InspectedPage`, `InspectedApp`, `AppInspection`, `InvokeRequest`, `Invocation`; Tool `inspect_framework`.

- [ ] **Step 1: Failing test** — `test_inspect_framework.py`:

```python
"""What the framework says about itself, read by import and handed to an agent."""

from importlib.metadata import version
from pathlib import Path

from tests_support import studio
from vibepy_core import ERROR_CATALOG
from vibepy_studio.authoring.models import FrameworkDescription


async def test_the_framework_describes_its_version_group_extras_and_catalogue(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        described = await tools.invoke("inspect_framework", {})
    assert isinstance(described, FrameworkDescription)
    assert described.framework_version == version("vibepy-core")
    assert described.entry_point_group == "vibepy.apps"
    assert described.channel_extras == ["web", "agent"]
    assert {row.code: row.category for row in described.error_catalog} == dict(ERROR_CATALOG)
```

- [ ] **Step 2: Run, expect ImportError**

- [ ] **Step 3: Implement**

`authoring/models.py`:

```python
"""What the authoring Tools take and return, and the `authoring.*` vocabulary.

| Code | Category | Reports |
| --- | --- | --- |
| `authoring.project_not_found` | caller | `project` holds no `pyproject.toml`, or one with no `[project].name` |
| `authoring.uv_unavailable` | execution | `uv` is not runnable from Studio's process |
| `authoring.environment_failed` | execution | uv exited non-zero with no framework report; what it wrote is the message |
| `authoring.no_apps_declared` | declaration | the project's environment declares nothing under the project's distribution |

A framework failure the child reports travels with its own code and category and
is not restated here.
"""

from pathlib import Path

from pydantic import BaseModel

from vibepy_core import ErrorCategory
from vibepy_studio.models import Diagnostic


class ErrorCode(BaseModel):
    """One framework code and its category."""

    code: str
    category: ErrorCategory


class FrameworkDescription(BaseModel):
    """What `vibepy_core` asserts about itself."""

    framework_version: str
    entry_point_group: str
    channel_extras: list[str]
    error_catalog: list[ErrorCode]


class InspectRequest(BaseModel):
    """A project to inspect: the directory holding its `pyproject.toml`."""

    project: Path


class InspectedTool(BaseModel):
    """One Tool a project declares."""

    name: str
    description: str
    input_schema: dict[str, object]
    output_schema: dict[str, object]


class InspectedPage(BaseModel):
    """One Page a project declares."""

    name: str
    route: str
    title: str


class InspectedApp(BaseModel):
    """One App a project declares, as its own environment describes it."""

    app_name: str
    distribution: str
    distribution_version: str
    app_id: str
    name: str
    version: str
    config_schema: dict[str, object]
    tools: list[InspectedTool]
    pages: list[InspectedPage]


class AppInspection(BaseModel):
    """What a project declares, or why that could not be read."""

    apps: list[InspectedApp]
    diagnostic: Diagnostic | None = None


class InvokeRequest(BaseModel):
    """One Tool of one App a project declares, with the App's configuration and the Tool's input."""

    project: Path
    app: str
    tool: str
    input: dict[str, object] = {}
    config: dict[str, object] = {}


class Invocation(BaseModel):
    """What the Tool returned, or why it did not."""

    output: dict[str, object] | None = None
    diagnostic: Diagnostic | None = None
```

`authoring/tools/inspection.py` (inspect_app is added in Task 9; this task writes `inspect_framework` only):

```python
"""Describing the framework, and describing what a project declares."""

import logging
from collections.abc import Sequence
from importlib.metadata import version

from vibepy_core import APP_GROUP, ERROR_CATALOG
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.authoring.models import ErrorCode, FrameworkDescription
from vibepy_studio.internals import StudioDeps
from vibepy_studio.models import Empty

logger = logging.getLogger(__name__)

CHANNEL_EXTRAS = ["web", "agent"]
"""The extras of `vibepy-core` that carry a channel; `docs/architecture/packaging.md` owns the fact."""


async def inspect_framework(_ctx: ToolContext[StudioDeps], _payload: Empty) -> FrameworkDescription:
    """Say what the framework this Studio is built on asserts about itself."""
    return FrameworkDescription(
        framework_version=version("vibepy-core"),
        entry_point_group=APP_GROUP,
        channel_extras=list(CHANNEL_EXTRAS),
        error_catalog=[ErrorCode(code=code, category=cat) for code, cat in ERROR_CATALOG.items()],
    )


INSPECTION_TOOLS: Sequence[Tool[StudioDeps]] = [
    Tool(
        definition=ToolDefinition(
            name="inspect_framework",
            description="What the framework asserts about itself: version, entry point group, channel extras, error catalogue",
            input_model=Empty,
            output_model=FrameworkDescription,
        ),
        handler=inspect_framework,
    ),
]
```

`authoring/tools/__init__.py`:

```python
"""Studio's authoring operations: what a coding agent asks of the framework while writing an App."""

from collections.abc import Sequence

from vibepy_core.tool import Tool
from vibepy_studio.authoring.tools.inspection import INSPECTION_TOOLS, inspect_framework
from vibepy_studio.internals import StudioDeps

AUTHORING_TOOLS: Sequence[Tool[StudioDeps]] = [*INSPECTION_TOOLS]

__all__ = ["AUTHORING_TOOLS", "inspect_framework"]
```

`entry.py`: `tools=[*HUB_TOOLS, *AUTHORING_TOOLS]` with the import from `vibepy_studio.authoring.tools`.

`version("vibepy-core")` is `importlib.metadata.version`; the workspace installs `vibepy-core` editable so it resolves in tests.

- [ ] **Step 4: Gate and commit**

```bash
make lint typecheck test
git add -A
git commit -m "Studio's Agent channel describes the framework it is built on

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: `inspect_app`

**Files:**
- Create: `packages/vibepy-studio/src/vibepy_studio/authoring/internals/__init__.py`, `.../internals/projects.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/authoring/tools/inspection.py`
- Test: `packages/vibepy-studio/tests/test_inspect_app.py`

**Interfaces:**
- Consumes: `describe(python)`, `DescribeFailed`, `NotRunnable`, `reported` (via `DescribeFailed.reported`), `category`.
- Produces: `projects.locate(project: Path, /) -> Path | None` (resolved dir if it holds `pyproject.toml`), `projects.declared_name(project: Path, /) -> str | None` (canonical `[project].name`), `projects.python(project: Path, /) -> list[str]` = `["uv", "run", "--project", str(project), "python"]`; Tool `inspect_app`; `authoring/models.py: diagnostic_of(reported: ChildFailure, /, **details: str) -> Diagnostic`; `authoring/tools/inspection.py: uv_unavailable(project: Path, /) -> Diagnostic`. Task 10 reuses the last two.

- [ ] **Step 1: Failing tests** — `test_inspect_app.py`:

```python
"""What a source project declares, read in the project's own environment."""

from pathlib import Path

import pytest

from tests_support import FIXTURES, studio
from vibepy_core import ErrorCategory
from vibepy_studio.authoring.models import AppInspection


@pytest.mark.integration
async def test_a_project_is_inspected_with_its_tools_pages_and_config(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        inspected = await tools.invoke("inspect_app", {"project": str(FIXTURES / "todo-app")})
    assert isinstance(inspected, AppInspection)
    assert inspected.diagnostic is None, inspected.diagnostic
    assert [app.app_name for app in inspected.apps] == ["todo-app"]
    todo = inspected.apps[0]
    assert sorted(tool.name for tool in todo.tools) == ["create_todo", "list_todos"]
    assert [page.route for page in todo.pages] == ["/todos"]
    assert set(todo.config_schema["properties"]) == {"db_path", "db_key"}  # type: ignore[index]


async def test_a_directory_without_a_pyproject_is_not_a_project(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        inspected = await tools.invoke("inspect_app", {"project": str(tmp_path / "nowhere")})
    assert isinstance(inspected, AppInspection)
    assert inspected.apps == []
    assert inspected.diagnostic is not None
    assert inspected.diagnostic.code == "authoring.project_not_found"
    assert inspected.diagnostic.category == ErrorCategory.CALLER


@pytest.mark.integration
async def test_a_project_whose_environment_lacks_the_framework_fails_as_an_environment(
    tmp_path: Path,
) -> None:
    project = tmp_path / "plain"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "plain"\nversion = "0.0.0"\nrequires-python = ">=3.12"\n', encoding="utf-8"
    )
    async with studio(tmp_path / "studio") as tools:
        inspected = await tools.invoke("inspect_app", {"project": str(project)})
    assert isinstance(inspected, AppInspection)
    assert inspected.diagnostic is not None
    assert inspected.diagnostic.code == "authoring.environment_failed"
    assert inspected.diagnostic.category == ErrorCategory.EXECUTION
    assert "vibepy_core" in inspected.diagnostic.message
```

The `# type: ignore[index]` is for pyright on `dict[str, object]` indexing; if pyright complains differently, assert via `isinstance(props := todo.config_schema["properties"], dict)` first and drop the ignore.

- [ ] **Step 2: Run, expect `tool.not_found` for `inspect_app`**

- [ ] **Step 3: Implement**

`authoring/internals/projects.py`:

```python
"""Locating a source project and naming the environment it runs in.

uv owns the environment: `uv run --project <dir>` discovers the project, keeps
its lockfile and environment current, and runs the command inside it. The path
handed to it is absolute, because uv resolves other arguments against the
current directory rather than the project.
"""

import tomllib
from pathlib import Path

from packaging.utils import canonicalize_name

PYPROJECT = "pyproject.toml"


def locate(project: Path, /) -> Path | None:
    """Return the resolved project directory, or nothing when it holds no `pyproject.toml`."""
    resolved = project.resolve()
    return resolved if (resolved / PYPROJECT).is_file() else None


def declared_name(project: Path, /) -> str | None:
    """Return the canonical `[project].name`, or nothing when the file declares none."""
    try:
        document = tomllib.loads((project / PYPROJECT).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    table = document.get("project")
    if not isinstance(table, dict):
        return None
    name = table.get("name")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return canonicalize_name(name) if isinstance(name, str) else None


def python(project: Path, /) -> list[str]:
    """The command prefix that runs Python inside this project's environment."""
    return ["uv", "run", "--project", str(project), "python"]
```

`authoring/internals/__init__.py` exports `declared_name`, `locate`, `python`.

`authoring/models.py` — add:

```python
def diagnostic_of(reported: ChildFailure, /, **details: str) -> Diagnostic:
    """Carry a failure a child reported, with its own code and category, plus `details`."""
    return Diagnostic(
        code=reported.code,
        category=category(reported.category),
        message=reported.message,
        details={**details, **reported.details},
    )
```

importing `ChildFailure` from `vibepy_studio.internals.processes` and `category` from `vibepy_studio.models`.

`authoring/tools/inspection.py` — add:

```python
def _not_a_project(project: Path, reason: str, /) -> AppInspection:
    return AppInspection(
        apps=[],
        diagnostic=Diagnostic(
            code="authoring.project_not_found",
            category=ErrorCategory.CALLER,
            message=f"{project} {reason}",
            details={"project": str(project)},
        ),
    )


def _failed(project: Path, failed: DescribeFailed, /) -> Diagnostic:
    """A child's own report when it made one, else the environment as the failure."""
    if failed.reported is not None:
        return diagnostic_of(failed.reported, project=str(project))
    return Diagnostic(
        code="authoring.environment_failed",
        category=ErrorCategory.EXECUTION,
        message=failed.output,
        details={"project": str(project)},
    )


def uv_unavailable(project: Path, /) -> Diagnostic:
    """Say uv is not runnable from this process."""
    return Diagnostic(
        code="authoring.uv_unavailable",
        category=ErrorCategory.EXECUTION,
        message="uv is not available to Studio; install uv and put it on PATH",
        details={"project": str(project)},
    )


async def inspect_app(_ctx: ToolContext[StudioDeps], payload: InspectRequest) -> AppInspection:
    """Describe the Apps a source project declares, read in that project's environment."""
    project = await asyncio.to_thread(locate, payload.project)
    if project is None:
        return _not_a_project(payload.project, "holds no pyproject.toml")
    name = await asyncio.to_thread(declared_name, project)
    if name is None:
        return _not_a_project(project, "declares no [project] name")
    try:
        described = await describe(python(project))
    except NotRunnable:
        return AppInspection(apps=[], diagnostic=uv_unavailable(project))
    except DescribeFailed as failed:
        return AppInspection(apps=[], diagnostic=_failed(project, failed))
    own = [
        InspectedApp.model_validate(entry.model_dump())
        for entry in described
        if canonicalize_name(entry.distribution) == name
    ]
    if not own:
        return AppInspection(
            apps=[],
            diagnostic=Diagnostic(
                code="authoring.no_apps_declared",
                category=ErrorCategory.DECLARATION,
                message=f"{name!r} declares no App in the {APP_GROUP!r} entry point group",
                details={"project": str(project), "distribution": name},
            ),
        )
    return AppInspection(apps=own)
```

Append to `INSPECTION_TOOLS`:

```python
    Tool(
        definition=ToolDefinition(
            name="inspect_app",
            description="Describe the Apps a source project declares, read in the project's own environment",
            input_model=InspectRequest,
            output_model=AppInspection,
        ),
        handler=inspect_app,
    ),
```

Imports: `asyncio`, `from pathlib import Path`, `from packaging.utils import canonicalize_name`, `ErrorCategory`, `Diagnostic`, `AppInspection`, `InspectRequest`, `InspectedApp`, `diagnostic_of`, `from vibepy_studio.authoring.internals import declared_name, locate, python`, `from vibepy_studio.internals import DescribeFailed, NotRunnable, describe`. Export `inspect_app` from `authoring/tools/__init__.py`.

- [ ] **Step 4: Gate and commit**

```bash
make lint typecheck test
git add -A
git commit -m "A source project is inspected in its own environment, and answers for its own Apps

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: `invoke_tool`

**Files:**
- Create: `packages/vibepy-studio/src/vibepy_studio/authoring/tools/invocation.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/authoring/tools/__init__.py`
- Test: `packages/vibepy-studio/tests/test_invoke_tool.py`

**Interfaces:**
- Consumes: `run`, `reported`, `NotRunnable`, `locate`, `python`, `diagnostic_of`, `uv_unavailable` (import from `inspection.py`).
- Produces: Tool `invoke_tool`.

- [ ] **Step 1: Failing tests** — `test_invoke_tool.py`:

```python
"""One Tool of a project's App, invoked through the framework's own window."""

from pathlib import Path

import pytest

from tests_support import FIXTURES, studio
from vibepy_core import ErrorCategory
from vibepy_studio.authoring.models import Invocation

TODO = str(FIXTURES / "todo-app")


def config(tmp_path: Path) -> dict[str, str]:
    return {"db_path": str(tmp_path / "todo.json"), "db_key": "k"}


@pytest.mark.integration
async def test_a_tool_is_invoked_and_a_later_call_sees_what_it_wrote(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        created = await tools.invoke(
            "invoke_tool",
            {
                "project": TODO,
                "app": "todo-app",
                "tool": "create_todo",
                "input": {"title": "milk"},
                "config": config(tmp_path),
            },
        )
        listed = await tools.invoke(
            "invoke_tool",
            {"project": TODO, "app": "todo-app", "tool": "list_todos", "config": config(tmp_path)},
        )
    assert isinstance(created, Invocation) and isinstance(listed, Invocation)
    assert created.diagnostic is None, created.diagnostic
    assert created.output is not None and created.output["title"] == "milk"
    assert listed.output is not None
    assert [todo["title"] for todo in listed.output["todos"]] == ["milk"]  # type: ignore[index]


@pytest.mark.integration
async def test_a_tool_the_app_does_not_declare_arrives_as_the_childs_report(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        answered = await tools.invoke(
            "invoke_tool",
            {"project": TODO, "app": "todo-app", "tool": "no_such_tool", "config": config(tmp_path)},
        )
    assert isinstance(answered, Invocation)
    assert answered.output is None
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "tool.not_found"
    assert answered.diagnostic.category == ErrorCategory.CALLER


@pytest.mark.integration
async def test_invalid_input_and_invalid_configuration_arrive_as_data(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        bad_input = await tools.invoke(
            "invoke_tool",
            {"project": TODO, "app": "todo-app", "tool": "create_todo", "config": config(tmp_path)},
        )
        bad_config = await tools.invoke(
            "invoke_tool", {"project": TODO, "app": "todo-app", "tool": "list_todos"}
        )
    assert isinstance(bad_input, Invocation) and bad_input.diagnostic is not None
    assert bad_input.diagnostic.code == "tool.input_invalid"
    assert isinstance(bad_config, Invocation) and bad_config.diagnostic is not None
    assert bad_config.diagnostic.code == "config.invalid"


async def test_a_directory_without_a_pyproject_is_not_a_project(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        answered = await tools.invoke(
            "invoke_tool", {"project": str(tmp_path / "nowhere"), "app": "x", "tool": "y"}
        )
    assert isinstance(answered, Invocation) and answered.diagnostic is not None
    assert answered.diagnostic.code == "authoring.project_not_found"
```

- [ ] **Step 2: Run, expect `tool.not_found` for `invoke_tool`**

- [ ] **Step 3: Implement `authoring/tools/invocation.py`**

```python
"""Invoking one Tool of a project's App, in the project's own environment."""

import asyncio
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from vibepy_core import ErrorCategory
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.authoring.internals import locate, python
from vibepy_studio.authoring.models import Invocation, InvokeRequest, diagnostic_of
from vibepy_studio.authoring.tools.inspection import uv_unavailable
from vibepy_studio.internals import NotRunnable, StudioDeps, reported, run
from vibepy_studio.models import Diagnostic

logger = logging.getLogger(__name__)

_OUTPUT = TypeAdapter(dict[str, object])
"""The command writes one JSON object: the Tool's output model, dumped."""


def _environment_failed(project: Path, output: str, /) -> Diagnostic:
    return Diagnostic(
        code="authoring.environment_failed",
        category=ErrorCategory.EXECUTION,
        message=output,
        details={"project": str(project)},
    )


async def invoke_tool(_ctx: ToolContext[StudioDeps], payload: InvokeRequest) -> Invocation:
    """Invoke one Tool once through the framework's own window, and return what it said."""
    project = await asyncio.to_thread(locate, payload.project)
    if project is None:
        return Invocation(
            diagnostic=Diagnostic(
                code="authoring.project_not_found",
                category=ErrorCategory.CALLER,
                message=f"{payload.project} holds no pyproject.toml",
                details={"project": str(payload.project)},
            )
        )
    request = json.dumps({"config": payload.config, "input": payload.input})
    try:
        completed = await run(
            [*python(project), "-m", "vibepy_core.invoke", payload.app, payload.tool], stdin=request
        )
    except NotRunnable:
        return Invocation(diagnostic=uv_unavailable(project))
    if completed.returncode != 0:
        report = reported(completed.stderr)
        if report is not None:
            return Invocation(
                diagnostic=diagnostic_of(
                    report, project=str(project), app=payload.app, tool=payload.tool
                )
            )
        return Invocation(
            diagnostic=_environment_failed(
                project, (completed.stdout + completed.stderr).strip()
            )
        )
    try:
        return Invocation(output=_OUTPUT.validate_json(completed.stdout))
    except ValidationError as invalid:
        logger.debug("the child wrote something other than one object", exc_info=invalid)
        return Invocation(diagnostic=_environment_failed(project, completed.stdout.strip()))


INVOCATION_TOOLS: Sequence[Tool[StudioDeps]] = [
    Tool(
        definition=ToolDefinition(
            name="invoke_tool",
            description="Invoke one Tool of an App a source project declares, once, in the project's own environment",
            input_model=InvokeRequest,
            output_model=Invocation,
        ),
        handler=invoke_tool,
    ),
]
```

`authoring/tools/__init__.py`: `AUTHORING_TOOLS = [*INSPECTION_TOOLS, *INVOCATION_TOOLS]`, export `invoke_tool`.

- [ ] **Step 4: Gate and commit**

```bash
make lint typecheck test
git add -A
git commit -m "A project's Tool is invoked once from Studio, through the framework's own window

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: ADR-032 and the ADR status/reference fixes

**Files:**
- Create: `docs/decisions/ADR-032-authoring-is-studios-agent-channel.md`
- Modify: `docs/decisions/ADR-025-the-framework-implements-channel-neutrality-and-delegates-the-rest.md` (status line only)
- Modify: `docs/decisions/ADR-031-the-proxy-is-traefik.md` (path reference only)

- [ ] **Step 1: Write ADR-032**

```markdown
# ADR-032: Authoring is Studio's Agent channel

Status: Accepted

Supersedes the distribution table of ADR-025.

## Context

ADR-025 fixed the product as three distributions: `vibepy-core`, `vibepy-hub`, and a
`vibepy-builder` to carry authoring when M12 arrived. ADR-024 had already placed authoring in the
Hub's position — a platform-tier App built on the framework.

Two platform-tier Apps would each be one App with one channel in use: the Hub consumed through
Pages by humans, the builder consumed through Tools by agents. The framework's own claim — one
App, one set of Tools, two first-class channels — would be true of neither.

An App's life has two halves, authoring and consumption (`docs/architecture/authoring.md`,
`docs/architecture/lifecycle.md`). They share what a host needs to read an App without importing
it: running the framework's commands in the App's environment and reading one shape of report.

## Decision

One platform-tier App, `vibepy-studio`, carries both halves. Consumption is its Web channel —
the board, for humans. Authoring is its Agent channel — Tools over MCP, for coding agents. Its
`app_id` is `vibepy-studio`, which is also the name its MCP server answers to.

The product is two distributions: `vibepy-core` and `vibepy-studio`. `vibepy-builder` is not
created. `vibepy-hub` is renamed, not kept beside it.

## Consequences

- the Hub's Tools, state and vocabulary are Studio's consumption role and keep the name Hub where
  a human sees it; the Studio's package is organised by role, `consumption` and `authoring`
- until per-channel exposure exists (`docs/roadmap.md` M14), every Studio Tool appears on both
  channels; M14 decides exposure with the authoring loop of M18 as its measure
- an installed App's environment holds the framework and that App, and never Studio — as ADR-024
  already required of the Hub
- the mechanisms both roles share — a child-process runner, a describer, a failure reader — are
  written once in Studio's shared internals, which is what having one App buys
```

- [ ] **Step 2: ADR-025 and ADR-031**

ADR-025: change `Status: Accepted` to `Status: Accepted; distribution table superseded by ADR-032`. Nothing else.

ADR-031: replace `vibepy_hub/internals/routing.py` with `vibepy_studio/consumption/internals/routing.py` (both occurrences).

- [ ] **Step 3: Commit**

```bash
git add docs/decisions
git commit -m "ADR-032: authoring is Studio's Agent channel, and there is no builder distribution

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: Architecture documents

**Files:**
- Modify: `docs/architecture/authoring.md`, `docs/architecture/packaging.md`, `docs/architecture/lifecycle.md`, `docs/architecture/app-model.md`

- [ ] **Step 1: `authoring.md`**

Replace the section "Authoring core before Authoring MCP" with current truth:

```markdown
## Authoring Core

Authoring is the Agent channel of Studio, the platform-tier App that also carries consumption; see
`docs/decisions/ADR-032-authoring-is-studios-agent-channel.md`. Its capabilities are Tools, so
they are channel-neutral like every Tool and reach an agent through MCP as any App's Tools do.

The App being authored is a source project: a directory holding a `pyproject.toml`, with no wheel
and no installation. Studio never imports it. It runs the framework's own commands in the
project's environment — `uv run --project <dir> python -m vibepy_core.describe|invoke` — and
reads what they write; `docs/architecture/packaging.md` owns those commands. The Apps a project
answers for are those its `[project].name` declares.

| Tool | Answers |
| --- | --- |
| `inspect_framework` | what `vibepy_core` asserts about itself: version, entry point group, channel extras, error catalogue. Read by import; carries no documentation |
| `inspect_app` | the project's Apps with every Tool schema, Page and configuration schema — or the framework's own diagnostic when the declaration will not load |
| `invoke_tool` | one Tool of one App, invoked once through the framework's invocation window, with configuration supplied by the caller |

Inspection and validation are one Tool: what the framework validates today is that a declaration
loads, and that is the failure path of describing. A failure the project's environment reports
travels with its own code and category; authoring's own diagnostics are the `authoring.*`
vocabulary that `vibepy_studio/authoring/models.py` defines.

Studio keeps no authoring state. The Web channel of a project is opened by the agent with
`python -m vibepy_core.serve` under `uv run`; the Agent channel's server command is
`docs/roadmap.md` M13's.

| Conceptual capability | Where it lives |
| --- | --- |
| inspect_framework, inspect_app, validate_app, invoke_tool | Studio, M12 (`validate_app` is `inspect_app`'s failure path until M16) |
| validate_package, package_app | `uv build`, the agent's own; M9's `describe` reads the result |
| run_conformance_tests | M16 |
| get_app_errors, get_runtime_logs | M15 |
```

Keep the Goal, Framework responsibility, Authoring MCP and North-star sections; in "Authoring MCP", replace "an adapter over the Authoring core" with "Studio's Agent channel served over MCP (`docs/roadmap.md` M13)".

- [ ] **Step 2: `packaging.md`**

After "## Running a channel", add:

```markdown
## Invoking one Tool

```text
python -m vibepy_core.invoke <app-name> <tool-name>
```

Run with an App environment's own interpreter, it opens the channel-neutral invocation window
once, invokes one Tool through `ToolRuntime`, and closes the window. Standard input carries one
JSON object of `config` and `input`; standard output receives the Tool's output as one JSON
object. This is how a host verifies that a Tool behaves without importing the App, and why the
verification runs the same path both channels run.

All three commands report a failure the same way: one line of `code`, `category`, `message` and
`details` on standard error and exit 1, produced by `report_line` in `vibepy_core.errors`. A
lifespan or handler that raises is reported as `app.unhandled`, as ADR-030 has a window report its
own failure.
```

In "Inspection and loading", add `load_app(app_name: str, /) -> AppEntrypoint` to the signature block with one sentence: "`load_app` imports by name in the running interpreter; it is what `serve` and `invoke` call, and a host reaches it only through them." Replace the sentence in "Both commands exist for one reason" with "All three commands exist for one reason".

In "What an environment holds", the Hub sentence becomes: "Studio declares `[web]` because its consumption role is a Page (`docs/roadmap.md` M11); its authoring role is Tools and needs no channel of its own."

Remove any mention of a third distribution if present.

- [ ] **Step 3: `lifecycle.md` and `app-model.md`**

`lifecycle.md`: `vibepy_hub/internals/files.py` → `vibepy_studio/internals/files.py`; `vibepy_hub/internals/routing.py` → `vibepy_studio/consumption/internals/routing.py`; `vibepy_hub/models.py` → `vibepy_studio/consumption/models.py`; the package-lifecycle owner line "a host App built on the framework" gains "(Studio's consumption role, called the Hub)". Where "the Hub" runs `python -m vibepy_core.serve` and opens windows, it is the consumption role and stays.

`app-model.md`: grep for `vibepy_hub` and update the path.

- [ ] **Step 4: Gate (ruff formats markdown code blocks only outside docs) and commit**

```bash
make lint
git add docs/architecture
git commit -m "The architecture says where authoring lives and what the third command does

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 13: Docstring convention pass and final gate

**Files:** every file the milestone created or changed under `src/` and `packages/vibepy-studio/src/`

- [ ] **Step 1: Read each new module's docstrings against PEP 257 and the repository's voice** — one sentence saying what the thing is or does, why where it is not obvious, no restating of a signature. `ruff check` enforces presence; this pass is for content.

- [ ] **Step 2: Full gate**

```bash
make lint typecheck test
```

- [ ] **Step 3: Commit if anything changed**

```bash
git add -A
git commit -m "Docstrings say what each new thing is for

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review notes

- Spec coverage: rename (T1–T2), ADR-032 (T11), three Tools (T8–T10), `invoke` command (T5), `load_app` (T4), `ERROR_CATALOG`/`report_line`/`describe` shape (T3), shared runner/reader (T6), shared describer (T7), documentation (T11–T12), tests one-per-subject (each task), compatibility (no deprecation; T1).
- The `uv run --project` calls in T9/T10 tests run against workspace members and the shared root environment; the first call may take a few seconds while uv checks the lock. `@pytest.mark.integration` marks them.
- `describe_with` alias in T7 avoids shadowing `installer.describe`, which the consumption `__init__` re-exports under that name.
