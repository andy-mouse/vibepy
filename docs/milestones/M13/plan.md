# M13 Authoring MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open an App's Agent channel over stdio with `python -m vibepy_core.mcp <app-name>`, and give every framework process one configuration channel — `VIBEPY_<FIELD>` environment variables read by pydantic-settings — so that Codex and Claude Code can launch Studio.

**Architecture:** The framework owns `AppConfig(BaseSettings)` with `env_prefix="VIBEPY_"`; an App's configuration model subclasses it and a window instantiates it (`definition.config(**raw)`), so the library reads the environment and explicit values stand above it. `serve` and `invoke` keep stdin configuration as a deprecated fallback; every launcher in the repository moves to the environment through `environment_for`. The new command builds the existing `build_mcp_server` and runs it under the SDK's `stdio_server`.

**Tech Stack:** Python 3.12, pydantic 2, pydantic-settings ≥ 2.15, MCP Python SDK 2.x (`mcp.server.stdio.stdio_server`, `mcp.client.Client`, `mcp.client.stdio.StdioServerParameters`), pytest + pytest-asyncio, uv workspace.

## Global Constraints

- Spec: `docs/milestones/M13/spec.md`. Acceptance criteria are `docs/roadmap.md` M13's, verbatim there.
- `make lint typecheck test` passes at the end of every task. pyright is `strict`; no `Any`, no `cast` in the public API.
- Variable name is `VIBEPY_<FIELD>`, field name upper-cased, fixed by `AppConfig.model_config = SettingsConfigDict(env_prefix="VIBEPY_")`. No `--config` argument anywhere. No dotenv file, no secrets directory.
- `environment_for`: a `str` value verbatim, anything else `json.dumps`.
- stdin configuration for `serve` and `invoke` stays working and emits one `DeprecationWarning` when non-empty. Nothing is removed.
- Only `vibepy_core.adapters.**`, `vibepy_core.serve` and (after Task 6) `vibepy_core.mcp` may import `mcp`/`nicegui` (`[tool.ruff.lint.flake8-tidy-imports.banned-api]`).
- Commit messages are one sentence in the repository's voice (see `git log`), ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Commit after every task; never push.
- Blocking calls in async code go through `asyncio.to_thread`. Paths are `pathlib.Path`. Logging via `getLogger(__name__)`; no `print`.
- `docs/roadmap.md` is never edited.

---

## File map

| File | Responsibility after this milestone |
| --- | --- |
| `src/vibepy_core/app/config.py` (new) | `AppConfig`, `NoConfig`, `environment_for` — the configuration contract in one module |
| `src/vibepy_core/app/model.py` | `AppDefinition[DepsT, ConfigT: AppConfig]`; imports `NoConfig` from `config.py` for re-export |
| `src/vibepy_core/app/composition.py` | windows instantiate `definition.config(**raw)`; bound `ConfigT: AppConfig` |
| `src/vibepy_core/app/entrypoint.py`, `package.py`, `adapters/mcp/server.py`, `adapters/nicegui/application.py`, `adapters/nicegui/web.py` | bound `ConfigT: AppConfig` |
| `src/vibepy_core/serve.py`, `invoke.py` | environment is the channel; stdin config deprecated |
| `src/vibepy_core/mcp.py` (new) | the Agent channel command |
| `src/vibepy_core/__init__.py`, `app/__init__.py` | export `AppConfig`, `environment_for` |
| `pyproject.toml` | `pydantic-settings>=2.15` dependency; ruff ignore for `mcp.py` |
| `packages/vibepy-studio/pyproject.toml` | `vibepy-core[web,agent]` |
| `packages/vibepy-studio/src/vibepy_studio/internals/processes.py` | `Processes.start` and `run` hand configuration through the environment |
| `packages/vibepy-studio/src/vibepy_studio/authoring/tools/invocation.py` | `invoke_tool` renders `config` into the child's environment |
| `scripts/run_studio.py` | launches `serve` with `VIBEPY_ROOT`, `VIBEPY_PROXY_PORT` |
| `fixtures/*/src/*/entry.py`, `packages/vibepy-studio/src/vibepy_studio/entry.py`, `tests/test_app_config.py` | configuration models subclass `AppConfig` |
| `tests/test_app_config.py`, `tests/test_serve_command.py`, `tests/test_invoke_command.py`, `tests/test_mcp_command.py` (new), `packages/vibepy-studio/tests/test_authoring_over_mcp.py` (new), `packages/vibepy-studio/tests/test_processes.py` | the tests the spec names |
| `docs/architecture/{packaging,authoring,lifecycle,adapters,app-model}.md`, `docs/decisions/ADR-033-…md`, ADR-022 and ADR-026 amendments | documentation |

---

### Task 1: `AppConfig`, `environment_for`, and a window that instantiates its declaration

**Files:**
- Create: `src/vibepy_core/app/config.py`
- Modify: `src/vibepy_core/app/model.py` (remove `NoConfig` class, import it), `src/vibepy_core/app/composition.py:73-85`, `src/vibepy_core/app/__init__.py`, `src/vibepy_core/__init__.py`, `pyproject.toml` (`[project].dependencies`)
- Test: `tests/test_app_config.py`

**Interfaces:**
- Produces: `class AppConfig(BaseSettings)` with `model_config = SettingsConfigDict(env_prefix="VIBEPY_")`; `class NoConfig(AppConfig)`; `def environment_for(config: Mapping[str, object], /) -> dict[str, str]`. All three exported from `vibepy_core` and `vibepy_core.app`.
- Consumed by: every later task.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, `[project].dependencies`:

```toml
dependencies = [
    "pydantic>=2.9",
    "pydantic-settings>=2.15",
]
```

Run: `uv sync`
Expected: `pydantic-settings` and `python-dotenv` appear in `uv.lock`.

- [ ] **Step 2: Write the failing tests**

Replace the `StoreConfig` import/definition at the top of `tests/test_app_config.py` and append the new tests. The file's existing tests stay; only `StoreConfig`'s base class changes.

```python
from pydantic import BaseModel, SecretStr

from vibepy_core.app import AppConfig, AppDefinition, NoConfig, environment_for, tool_runtime_for


class Limits(BaseModel):
    per_page: int


class StoreConfig(AppConfig):
    db_path: Path
    api_token: SecretStr
    limits: Limits = Limits(per_page=10)
```

Append:

```python
async def test_a_window_reads_its_declaration_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBEPY_DB_PATH", "/tmp/env.db")
    monkeypatch.setenv("VIBEPY_API_TOKEN", "from-env")
    monkeypatch.setenv("VIBEPY_LIMITS", '{"per_page": 3}')
    monkeypatch.setenv("VIBEPY_OTHER", "not a field")
    seen: list[StoreConfig] = []

    @asynccontextmanager
    async def lifespan(config: StoreConfig) -> AsyncGenerator[Acquired]:
        seen.append(config)
        yield Acquired(config)

    async with tool_runtime_for(configured_definition(), lifespan, config={}):
        pass

    assert seen[0].db_path == Path("/tmp/env.db")
    assert seen[0].api_token.get_secret_value() == "from-env"
    assert seen[0].limits.per_page == 3


async def test_an_explicit_value_stands_above_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBEPY_DB_PATH", "/tmp/env.db")
    monkeypatch.setenv("VIBEPY_API_TOKEN", "from-env")
    seen: list[StoreConfig] = []

    @asynccontextmanager
    async def lifespan(config: StoreConfig) -> AsyncGenerator[Acquired]:
        seen.append(config)
        yield Acquired(config)

    async with tool_runtime_for(
        configured_definition(), lifespan, config={"db_path": "/tmp/explicit.db"}
    ):
        pass

    assert seen[0].db_path == Path("/tmp/explicit.db")
    assert seen[0].api_token.get_secret_value() == "from-env"


async def test_a_value_for_an_undeclared_field_is_refused() -> None:
    entered = entered_flags()

    with pytest.raises(AppConfigInvalidError) as raised:
        async with tool_runtime_for(
            configured_definition(),
            store_lifespan(entered),
            config={"db_path": "/tmp/x.db", "api_token": "s", "db_pth": "typo"},
        ):
            pass

    assert entered == []
    assert raised.value.fields == ("db_pth",)


def test_environment_for_renders_what_a_window_reads() -> None:
    rendered = environment_for(
        {"db_path": "/tmp/x.db", "api_token": "s", "limits": {"per_page": 7}, "port": 8080}
    )

    assert rendered == {
        "VIBEPY_DB_PATH": "/tmp/x.db",
        "VIBEPY_API_TOKEN": "s",
        "VIBEPY_LIMITS": '{"per_page": 7}',
        "VIBEPY_PORT": "8080",
    }
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_app_config.py -q`
Expected: ImportError — `AppConfig` and `environment_for` do not exist.

- [ ] **Step 4: Create `src/vibepy_core/app/config.py`**

```python
"""What an App requires of its host, and where the values come from.

The declaration is a Pydantic settings model: instantiating it reads one
environment variable per field, `VIBEPY_<FIELD>`, and explicit keyword values
stand above the environment field by field. Both are pydantic-settings'
documented behaviour; the framework fixes the prefix here so that every
declaration reads the same variables wherever it is instantiated. See
`docs/decisions/ADR-033-configuration-reaches-a-process-through-the-environment.md`.
"""

import json
from collections.abc import Mapping

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "VIBEPY_"
"""Every configuration variable begins with this."""


class AppConfig(BaseSettings):
    """The base of every App's configuration model.

    Subclass it and declare fields. A window instantiates the subclass; nothing
    else needs to. Extra keys are refused, as `BaseSettings` does by default,
    so a misspelt field fails when the window opens rather than being dropped.
    """

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX)


class NoConfig(AppConfig):
    """The configuration of an App that requires nothing of its host.

    Declared explicitly rather than defaulted, so that one validation path serves
    every App and the framework never guesses that an App needs nothing.
    """


def environment_for(config: Mapping[str, object], /) -> dict[str, str]:
    """Render held configuration values into the variables a window reads.

    The inverse of the library's decoding: a string verbatim, anything else as
    JSON, which is how pydantic-settings reads a complex field. Values are JSON
    values, as a host holds them.
    """
    return {
        f"{ENV_PREFIX}{name.upper()}": value if isinstance(value, str) else json.dumps(value)
        for name, value in config.items()
    }
```

- [ ] **Step 5: Move `NoConfig` out of `model.py`**

In `src/vibepy_core/app/model.py`, delete the `NoConfig` class and change the import block to:

```python
from vibepy_core.app.config import AppConfig, NoConfig
from vibepy_core.page.model import Page
from vibepy_core.tool.runtime import Tool

__all__ = ["AppConfig", "AppDefinition", "NoConfig"]
```

Change the class header to `class AppDefinition[DepsT, ConfigT: AppConfig]:` and remove the now-unused `from pydantic import BaseModel`. Update the `config` docstring sentence to: "``config`` is the opposite kind of type: an `AppConfig` subclass the framework instantiates and projects. It is what this App requires of its host, and it is readable without acquiring anything."

- [ ] **Step 6: Instantiate the declaration in the window**

In `src/vibepy_core/app/composition.py` replace `_validated`:

```python
def _validated[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT], raw: Mapping[str, object], /
) -> ConfigT:
    """Instantiate the App's configuration from explicit values and the environment.

    Explicit values stand above the environment field by field, in the
    library's documented order. Raised before a lifespan is entered, so a
    window that cannot run acquires nothing.
    """
    try:
        return definition.config(**raw)
    except ValidationError as error:
        fields = [".".join(str(part) for part in entry["loc"]) for entry in error.errors()]
        raise AppConfigInvalidError(definition.app_id, fields) from error
```

Change every `ConfigT: BaseModel` in this file to `ConfigT: AppConfig`, import `AppConfig` from `vibepy_core.app.config`, and drop `BaseModel` from the pydantic import (keep `ValidationError`).

- [ ] **Step 7: Export**

`src/vibepy_core/app/__init__.py`: import `AppConfig, NoConfig, environment_for` from `vibepy_core.app.config` (remove `NoConfig` from the `model` import), add `"AppConfig"` and `"environment_for"` to `__all__`.

`src/vibepy_core/__init__.py`: add `AppConfig` and `environment_for` to the `from vibepy_core.app import (...)` block and to `__all__`, alphabetically.

- [ ] **Step 8: Run the config tests**

Run: `uv run pytest tests/test_app_config.py -q`
Expected: all pass. If `test_a_value_for_an_undeclared_field_is_refused` reports `fields == ()`, inspect `error.errors()[0]["loc"]` — for an extra-forbidden key pydantic reports `("db_pth",)`; the join already yields `"db_pth"`.

- [ ] **Step 9: Typecheck to find every remaining `ConfigT: BaseModel` site**

Run: `uv run pyright`
Expected: errors at `entrypoint.py`, `package.py`, `adapters/mcp/server.py`, `adapters/nicegui/application.py`, `adapters/nicegui/web.py`, `serve.py`, `invoke.py`, the three fixtures and Studio's `entry.py` — Task 2 fixes them. Do not commit yet.

### Task 2: Narrow the bound everywhere and move every configuration model onto `AppConfig`

**Files:**
- Modify: `src/vibepy_core/app/entrypoint.py:48`, `src/vibepy_core/app/package.py:63,73,95`, `src/vibepy_core/adapters/mcp/server.py:66`, `src/vibepy_core/adapters/nicegui/application.py:32`, `src/vibepy_core/adapters/nicegui/web.py:26`, `src/vibepy_core/serve.py:69`, `src/vibepy_core/invoke.py:40`, `fixtures/todo-app/src/todo_app/entry.py:41`, `fixtures/notes-app/src/notes_app/entry.py:21`, `fixtures/timer-app/src/timer_app/entry.py:34`, `packages/vibepy-studio/src/vibepy_studio/entry.py:24`
- Test: the whole suite

**Interfaces:**
- Consumes: `AppConfig` from Task 1.
- Produces: every `AppDefinition`, `AppEntrypoint`, `build_mcp_server`, `build_web_app`, `register_pages`, `load_app` bound on `ConfigT: AppConfig`; `AppEntrypoint[object, AppConfig]` where `AppEntrypoint[object, BaseModel]` was.

- [ ] **Step 1: Core sites**

In each core file, replace `ConfigT: BaseModel` with `ConfigT: AppConfig` and `AppEntrypoint[object, BaseModel]` with `AppEntrypoint[object, AppConfig]`, importing `from vibepy_core.app.config import AppConfig`. Remove `BaseModel` from an import only where nothing else in the file uses it (`entrypoint.py` still uses `BaseModel` for `JsonValue`-adjacent code; `serve.py` and `invoke.py` still use it for `_Request`/return types — check each file).

- [ ] **Step 2: Fixtures and Studio**

`fixtures/todo-app/src/todo_app/entry.py`: `class TodoConfig(AppConfig):` with `from vibepy_core import AppConfig` added to the existing `vibepy_core` import. Same for `NotesConfig` and `TimerConfig`. In `packages/vibepy-studio/src/vibepy_studio/entry.py`: `class StudioConfig(AppConfig):`, import `AppConfig` from `vibepy_core`, keep `Field` from pydantic, drop `BaseModel` if unused.

- [ ] **Step 3: Gate**

Run: `make lint typecheck test`
Expected: passes. `tests/test_describe_command.py` and Studio's `test_describing.py` compare `config_schema`; `BaseSettings.model_json_schema()` yields the same `properties` as before. If a schema test now sees an added `additionalProperties: false`, that is the `extra="forbid"` default and is correct — update the expected schema in that test only.

- [ ] **Step 4: Commit**

```bash
git add -A src tests fixtures packages/vibepy-studio/src pyproject.toml uv.lock
git commit -m "An App's configuration is an AppConfig, and a window instantiates it: explicit values above VIBEPY_ variables

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 3: `serve` takes its configuration from the environment, stdin deprecated

**Files:**
- Modify: `src/vibepy_core/serve.py:90-118`
- Test: `tests/test_serve_command.py`

**Interfaces:**
- Consumes: the window's environment reading (Task 1).
- Produces: `python -m vibepy_core.serve <app-name> --port <n>` with `VIBEPY_*` set and no stdin; a non-empty stdin object still works and prints `DeprecationWarning` to stderr.

- [ ] **Step 1: Rewrite the tests that pass configuration**

In `tests/test_serve_command.py`, add a helper beneath `child_environment`:

```python
def todo_environment(tmp_path: Path) -> dict[str, str]:
    """The Todo App's configuration, as a served App reads it."""
    return {
        **child_environment(),
        **environment_for({"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}),
    }
```

with `from vibepy_core import environment_for` at the top. Then:

- `test_a_declared_page_is_served`: launch with `stdin=subprocess.DEVNULL, env=todo_environment(tmp_path)`; delete the three stdin lines and the `config` variable.
- `test_a_window_that_will_not_open_stops_the_server`: `stdin=subprocess.DEVNULL`, `env=child_environment()` (no `VIBEPY_*`), drop `input=b"{}"`. Assertions unchanged.
- `test_a_window_that_raises_for_its_own_reason_reports_that`: replace `input=json.dumps({...}).encode()` with `stdin=subprocess.DEVNULL, env={**child_environment(), **environment_for({"root": str(blocking / "root")})}`.
- `test_an_unknown_app_name_fails_with_the_framework_code`: `stdin=subprocess.DEVNULL`, drop `input`.
- `test_configuration_that_is_not_an_object_fails_with_a_framework_code`: unchanged (stdin `[]` is still the deprecated channel's shape error).

Add:

```python
@pytest.mark.integration
def test_configuration_on_standard_input_still_works_and_is_deprecated(tmp_path: Path) -> None:
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "vibepy_core.serve", "todo-app", "--port", str(port)],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=child_environment(),
    )
    assert process.stdin is not None and process.stderr is not None
    process.stdin.write(
        json.dumps({"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}).encode()
    )
    process.stdin.close()
    try:
        body = wait_for(f"http://127.0.0.1:{port}/todos", process)
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert "<html" in body.lower()
    assert "DeprecationWarning" in process.stderr.read().decode(errors="replace")
```

- [ ] **Step 2: Run to verify the new behaviour fails**

Run: `uv run pytest tests/test_serve_command.py -q`
Expected: the rewritten tests pass already — the window reads the environment since Task 1. The deprecation test fails: no warning is written.

- [ ] **Step 3: Implement**

In `src/vibepy_core/serve.py`, after `config` is validated from stdin in `main`:

```python
    if config:
        warnings.warn(
            "Configuration on standard input is deprecated; set VIBEPY_<FIELD> variables",
            DeprecationWarning,
            stacklevel=1,
        )
```

Add `import warnings`. Update `main`'s docstring: "Read configuration from the environment — `VIBEPY_<FIELD>` per declared field — and serve one App. A JSON object on standard input is still read as explicit values above the environment, and is deprecated." Update the module docstring's `_CONFIG` line: "Standard input may carry one JSON object of configuration, the deprecated channel; the window reads the environment."

`python -m` runs the module as `__main__`, where the default warning filter shows `DeprecationWarning`, so it reaches stderr without configuration.

- [ ] **Step 4: Run the serve tests**

Run: `uv run pytest tests/test_serve_command.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/vibepy_core/serve.py tests/test_serve_command.py
git commit -m "serve reads VIBEPY_ variables; configuration on standard input still works and is deprecated

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 4: `invoke` takes its configuration from the environment, stdin `config` deprecated

**Files:**
- Modify: `src/vibepy_core/invoke.py:32-80`
- Test: `tests/test_invoke_command.py`

**Interfaces:**
- Produces: `python -m vibepy_core.invoke <app> <tool>` with `VIBEPY_*` in the environment and `{"input": {...}}` on stdin; `{"config": {...}, "input": {...}}` still works with a `DeprecationWarning`.

- [ ] **Step 1: Rewrite the tests**

In `tests/test_invoke_command.py`, change `run_invoke` to take an environment:

```python
from vibepy_core import environment_for


def run_invoke(
    app: str, tool: str, request: object, *, config: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "vibepy_core.invoke", app, tool],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        env={**child_environment(), **environment_for(config or {})},
        check=False,
    )
```

Every call that passed `{"config": todo_config(tmp_path), "input": ...}` becomes `run_invoke(app, tool, {"input": ...}, config=todo_config(tmp_path))`. `test_invalid_configuration_is_reported` becomes `run_invoke("todo-app", "list_todos", {"input": {}})` with no `config`. Add:

```python
@pytest.mark.integration
def test_configuration_on_standard_input_still_works_and_is_deprecated(tmp_path: Path) -> None:
    result = run_invoke(
        "todo-app", "create_todo", {"config": todo_config(tmp_path), "input": {"title": "milk"}}
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["title"] == "milk"
    assert "DeprecationWarning" in result.stderr
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_invoke_command.py -q`
Expected: the deprecation test fails (no warning); the others pass already because the window reads the environment.

- [ ] **Step 3: Implement**

In `src/vibepy_core/invoke.py` `main`, after the request is parsed:

```python
    if request.config:
        warnings.warn(
            "`config` on standard input is deprecated; set VIBEPY_<FIELD> variables",
            DeprecationWarning,
            stacklevel=1,
        )
```

Add `import warnings`. `_Request` docstring: "What standard input carries: the Tool's input, and — deprecated — the App's configuration as explicit values above the environment."

- [ ] **Step 4: Run, then commit**

Run: `uv run pytest tests/test_invoke_command.py -q` — Expected: all pass.

```bash
git add src/vibepy_core/invoke.py tests/test_invoke_command.py
git commit -m "invoke reads VIBEPY_ variables; config on standard input still works and is deprecated

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 5: Studio's launchers hand configuration through the environment

**Files:**
- Modify: `packages/vibepy-studio/src/vibepy_studio/internals/processes.py` (`run` at 117, `Processes.start` at ~275-335), `packages/vibepy-studio/src/vibepy_studio/authoring/tools/invocation.py:28-37`, `scripts/run_studio.py:33-42`
- Test: `packages/vibepy-studio/tests/test_processes.py`, existing `test_runtime.py` and `test_invoke_tool.py` (assertions unchanged)

**Interfaces:**
- Consumes: `environment_for` from `vibepy_core`.
- Produces: `run(command, /, *, stdin: str | None = None, env: Mapping[str, str] | None = None) -> Completed`; `Processes.start` launches `serve` with `stdin=DEVNULL` and `env={**child_environment(), **environment_for(config)}`.

- [ ] **Step 1: Adjust the process test whose subject was the stdin pipe**

In `packages/vibepy-studio/tests/test_processes.py`, `test_a_child_that_dies_before_reading_its_stdin_is_a_start_failure`: rename to `test_a_child_that_cannot_run_the_command_is_a_start_failure`, docstring "An environment without the framework cannot run the command at all, so the child exits before it answers.", and `config={"db_path": "x", "db_key": "k"}`. Nothing is written to stdin any more, so the pipe-filling payload has no subject.

- [ ] **Step 2: `run` takes an environment**

```python
async def run(
    command: Sequence[str], /, *, stdin: str | None = None, env: Mapping[str, str] | None = None
) -> Completed:
    """Run one command to completion and return what it left.

    Every child receives `child_environment()` with `env` laid over it, so what
    describes Studio's own process describes no child and what the caller hands
    the child reaches it. Standard output and standard error are returned
    apart, unmerged, so a report a child wrote to standard error stays separate
    from what it wrote to standard output.
    """
    if not await asyncio.to_thread(is_runnable, command[0]):
        raise NotRunnable(command[0])
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL if stdin is None else asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**child_environment(), **(env or {})},
    )
```

(rest unchanged.)

- [ ] **Step 3: `Processes.start`**

Replace the `create_subprocess_exec` call and the stdin block:

```python
            process = await asyncio.create_subprocess_exec(
                str(interpreter),
                "-m",
                "vibepy_core.serve",
                app_name,
                "--port",
                str(port),
                stdin=asyncio.subprocess.DEVNULL,
                stderr=handle,
                env={**child_environment(), **environment_for(config)},
            )
        finally:
            await asyncio.to_thread(handle.close)
        child = _Child(process=process)
        self._running[known_as] = child
        try:
            await self._wait_until_answering(process, port)
        except StartFailed as failure:
```

Delete the `except OSError as broken:` clause (nothing is written to the child any more) and the `import json`. Add `from vibepy_core import environment_for`. Replace the docstring paragraph beginning "Standard input carries the configuration…" with: "The configuration reaches the child as `VIBEPY_<FIELD>` variables, rendered by `environment_for`, laid over the environment the child is entitled to (`docs/architecture/packaging.md`, Configuration)."

- [ ] **Step 4: `invoke_tool`**

In `invocation.py`:

```python
    request = json.dumps({"input": payload.input})
    try:
        completed = await run(
            [*python(project), "-m", "vibepy_core.invoke", payload.app, payload.tool],
            stdin=request,
            env=environment_for(payload.config),
        )
```

Add `from vibepy_core import environment_for`.

- [ ] **Step 5: `scripts/run_studio.py`**

```python
    studio = subprocess.Popen(
        [sys.executable, "-m", "vibepy_core.serve", "studio", "--port", str(args.port)],
        stdin=subprocess.DEVNULL,
        env={**os.environ, **environment_for({"root": str(root), "proxy_port": args.proxy_port})},
    )
```

Add `import os` and `from vibepy_core import environment_for`; delete the three `studio.stdin` lines and the `json` import if unused. Update the module docstring's second sentence to "reads its configuration from `VIBEPY_ROOT` and `VIBEPY_PROXY_PORT`".

- [ ] **Step 6: Gate**

Run: `make lint typecheck test`
Expected: passes. `test_runtime.py::test_a_secret_supplied_at_start_reaches_the_app` proves a secret still reaches the App through the new channel; `test_invoke_tool.py` proves `invoke_tool`'s `config` still arrives.

- [ ] **Step 7: Commit**

```bash
git add packages/vibepy-studio scripts/run_studio.py
git commit -m "Studio hands a child its configuration as VIBEPY_ variables, and writes nothing to its stdin

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 6: `python -m vibepy_core.mcp <app-name>`

**Files:**
- Create: `src/vibepy_core/mcp.py`, `tests/test_mcp_command.py`
- Modify: `pyproject.toml` (`[tool.ruff.lint.per-file-ignores]`), `packages/vibepy-studio/pyproject.toml` (`vibepy-core[web,agent]`)

**Interfaces:**
- Consumes: `load_app`, `build_mcp_server`, `report` (all existing); the window's environment reading (Task 1).
- Produces: the command; exit 1 with one report line for a command failure or a window that will not open.

- [ ] **Step 1: Write the failing tests**

`tests/test_mcp_command.py`:

```python
"""The command that opens an App's Agent channel over stdio, run as a real process."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import TextContent

from test_serve_command import child_environment
from vibepy_core import environment_for


def todo_server(tmp_path: Path) -> StdioServerParameters:
    """`vibepy-todo` served from this interpreter's environment, configured for `tmp_path`."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "vibepy_core.mcp", "todo-app"],
        env={
            **child_environment(),
            **environment_for({"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}),
        },
    )


@pytest.mark.integration
async def test_declared_tools_are_discoverable_over_stdio(tmp_path: Path) -> None:
    async with Client(todo_server(tmp_path)) as agent:
        listed = await agent.list_tools()

    assert {tool.name for tool in listed.tools} >= {"create_todo", "list_todos", "complete_todo"}


@pytest.mark.integration
async def test_a_call_returns_structured_content_over_stdio(tmp_path: Path) -> None:
    async with Client(todo_server(tmp_path)) as agent:
        created = await agent.call_tool("create_todo", {"title": "milk"})

    assert created.is_error is False
    assert created.structured_content is not None
    assert created.structured_content["title"] == "milk"
    block = created.content[0]
    assert isinstance(block, TextContent)
    assert json.loads(block.text)["title"] == "milk"


def _reported(stderr: bytes, /) -> dict[str, object]:
    for line in reversed(stderr.decode(errors="replace").splitlines()):
        try:
            parsed: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "code" in parsed:
            return parsed  # pyright: ignore[reportUnknownVariableType]
    raise AssertionError(f"nothing was reported: {stderr.decode(errors='replace')!r}")


@pytest.mark.integration
def test_an_unknown_app_name_fails_with_the_framework_code() -> None:
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.mcp", "absent"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode == 1
    assert finished.stdout == b""
    assert _reported(finished.stderr)["code"] == "package.app_not_declared"


@pytest.mark.integration
def test_a_window_that_will_not_open_ends_the_process() -> None:
    """No `VIBEPY_*` is set, so the window refuses and the process exits before
    any client message; nothing but MCP may reach stdout, and nothing did."""
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.mcp", "todo-app"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        env=child_environment(),
        timeout=60,
    )

    assert finished.returncode == 1
    assert finished.stdout == b""
    reported = _reported(finished.stderr)
    assert reported["code"] == "config.invalid"
    assert reported["category"] == "caller"
```

If `_reported`'s `parsed` return needs a typed shape for pyright, reuse the `Reported` TypedDict and `cast` from `tests/test_serve_command.py` by importing `_reported` from there instead (tests may use `cast`).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_mcp_command.py -q`
Expected: every test fails — `No module named vibepy_core.mcp`.

- [ ] **Step 3: Create `src/vibepy_core/mcp.py`**

```python
"""Open one App's Agent channel over stdio, in that App's own environment.

`vibepy_core.serve` runs an App's Web channel; this runs its Agent channel. The
adapter builds the server; the MCP client owns this process and speaks to it
over standard input and output, so this command runs the server and writes
nothing of its own to standard output. Its configuration is the environment's,
`VIBEPY_<FIELD>` per declared field, as for every framework command.
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence

from mcp.server.stdio import stdio_server

from vibepy_core.adapters.mcp import build_mcp_server
from vibepy_core.app.config import AppConfig
from vibepy_core.app.entrypoint import AppEntrypoint
from vibepy_core.app.package import load_app
from vibepy_core.errors import (
    AppEntrypointInvalidError,
    AppEntrypointUnloadableError,
    AppNotDeclaredError,
    report,
)

logger = logging.getLogger(__name__)


async def _serve(entrypoint: AppEntrypoint[object, AppConfig], /) -> None:
    """Run the server for as long as the client keeps this process alive.

    `Server.run` enters the App's window, so the window is the process.
    """
    server = build_mcp_server(entrypoint.definition, entrypoint.lifespan, config={})
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(argv: Sequence[str], /) -> int:
    """Serve one App's Tools over stdio.

    Exits 1 with one report line on standard error for a failure of the command
    itself — an App this environment does not declare or cannot load — and for a
    window that will not open, which `Server.run` propagates as it enters the
    lifespan. Standard output carries MCP messages and nothing else.
    """
    logging.basicConfig(stream=sys.stderr, level=logging.ERROR, format="%(message)s")
    parser = argparse.ArgumentParser(prog="vibepy_core.mcp")
    parser.add_argument("app_name")
    parsed = parser.parse_args(argv)
    try:
        entrypoint = load_app(str(parsed.app_name))
    except (AppNotDeclaredError, AppEntrypointUnloadableError, AppEntrypointInvalidError) as error:
        report(error)
        return 1
    try:
        asyncio.run(_serve(entrypoint))
    except Exception as error:
        # The window reports its own failure (ADR-030).
        report(error)
        logger.debug("the Agent channel did not open or did not stay open", exc_info=error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Let the command import the SDK, and give Studio the extra**

`pyproject.toml`, `[tool.ruff.lint.per-file-ignores]`:

```toml
"src/vibepy_core/serve.py" = ["TID251"]
"src/vibepy_core/mcp.py" = ["TID251"]
```

and extend the comment above it: "…the command that opens the Web channel and the command that opens the Agent channel are exempt below, because being a channel component is their job." Also update the banned-api message for `mcp`: `"The core declares no channel. Only vibepy_core.adapters.mcp and vibepy_core.mcp may import the MCP SDK."`

`packages/vibepy-studio/pyproject.toml`: `"vibepy-core[web,agent]",`. Run `uv lock`.

- [ ] **Step 5: Run the command tests**

Run: `uv run pytest tests/test_mcp_command.py -q`
Expected: all pass. If `test_a_window_that_will_not_open_ends_the_process` hangs, `Server.run` did not enter the lifespan before reading — read `mcp/server/lowlevel/server.py::run` in `.venv` and confirm where `self.lifespan(self)` is entered; the SDK documentation says `run` "enters the server lifespan, then drives the loop". Report what you find rather than adding a timeout to the command.

- [ ] **Step 6: Gate and commit**

Run: `make lint typecheck test`

```bash
git add src/vibepy_core/mcp.py tests/test_mcp_command.py pyproject.toml packages/vibepy-studio/pyproject.toml uv.lock
git commit -m "python -m vibepy_core.mcp opens an App's Agent channel over stdio, configured by its environment

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 7: Studio's authoring Tools over a real stdio process

**Files:**
- Create: `packages/vibepy-studio/tests/test_authoring_over_mcp.py`

**Interfaces:**
- Consumes: the command (Task 6), `FIXTURES` from `tests_support`, `AUTHORING_TOOLS` names.

- [ ] **Step 1: Write the tests**

```python
"""Studio's Agent channel as an agent platform reaches it: a stdio process."""

import json
import os
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import TextContent

from tests_support import FIXTURES
from vibepy_core import environment_for
from vibepy_studio.internals import child_environment

TODO = FIXTURES / "todo-app"


def studio_server(root: Path) -> StdioServerParameters:
    """Studio served from this interpreter's environment, over `root`.

    `uv` must be on the child's PATH: the authoring Tools run it.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "vibepy_core.mcp", "studio"],
        env={
            **child_environment(),
            "PATH": os.environ["PATH"],
            **environment_for({"root": str(root), "proxy_port": 8080}),
        },
    )


@pytest.mark.integration
async def test_authoring_tools_are_discoverable(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        listed = await agent.list_tools()

    assert {tool.name for tool in listed.tools} >= {"inspect_framework", "inspect_app", "invoke_tool"}


@pytest.mark.integration
async def test_an_inspection_arrives_as_structured_content(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        inspected = await agent.call_tool("inspect_app", {"project": str(TODO)})

    assert inspected.is_error is False
    assert inspected.structured_content is not None
    apps = inspected.structured_content["apps"]
    assert [tool["name"] for tool in apps[0]["tools"]] == ["create_todo", "list_todos", "complete_todo"]
    assert inspected.structured_content["diagnostic"] is None


@pytest.mark.integration
async def test_an_expected_failure_arrives_as_structured_data(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        inspected = await agent.call_tool("inspect_app", {"project": str(tmp_path / "nowhere")})

    assert inspected.is_error is False
    assert inspected.structured_content is not None
    assert inspected.structured_content["diagnostic"]["code"] == "authoring.project_not_found"


@pytest.mark.integration
async def test_invalid_input_arrives_as_the_framework_payload(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        refused = await agent.call_tool("inspect_app", {})

    assert refused.is_error is True
    block = refused.content[0]
    assert isinstance(block, TextContent)
    assert json.loads(block.text)["code"] == "tool.input_invalid"
```

The Tool-name order in the second test is whatever `fixtures/todo-app/src/todo_app/entry.py` declares; read it and match. If the SDK's `Client` result types make `structured_content[...]` indexing fail pyright, validate through Studio's own models instead: `AppInspection.model_validate(inspected.structured_content)` and assert on `.apps[0].tools`, which is the contract anyway.

- [ ] **Step 2: Run**

Run: `uv run pytest packages/vibepy-studio/tests/test_authoring_over_mcp.py -q`
Expected: all pass. A failure in the second test with `authoring.uv_unavailable` means `PATH` did not reach the child — check `child_environment()` keeps `PATH` (it does; `DESCRIBES_THIS_PROCESS` does not name it).

- [ ] **Step 3: Gate and commit**

Run: `make lint typecheck test`

```bash
git add packages/vibepy-studio/tests/test_authoring_over_mcp.py
git commit -m "Studio's authoring Tools are reached as an agent platform reaches them: a stdio process, structured results intact

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 8: Documentation, ADR-033, amendments, docstrings

**Files:**
- Create: `docs/decisions/ADR-033-configuration-reaches-a-process-through-the-environment.md`
- Modify: `docs/architecture/packaging.md`, `docs/architecture/authoring.md`, `docs/architecture/lifecycle.md`, `docs/architecture/adapters.md`, `docs/architecture/app-model.md`, `docs/decisions/ADR-022-configuration-is-a-declaration.md` (status line + amendment), `docs/decisions/ADR-026-the-web-window-is-the-served-applications-lifespan.md` (status line + amendment), `docs/milestones/M13/spec.md` (one word)

- [ ] **Step 1: ADR-033**

Nygard format, `Status: Accepted`. Context: ADR-022 left the source open; stdin was chosen in ADR-026 as a consequence with no alternative weighed and kept in Studio for secret hygiene; stdio makes stdin the transport. Cite: MCP transports spec, Codex and Claude Code `env`, MCP registry `environmentVariables`, 12-factor config, OWASP §5.1 as the counter-argument, pydantic-settings documentation. Decision: `AppConfig(BaseSettings)` with `env_prefix="VIBEPY_"`; `ConfigT: AppConfig`; a window instantiates the declaration, explicit values above the environment; `vibepy-core` depends on `pydantic-settings`; stdin configuration deprecated. Consequences: one channel for three commands; a declaration reads its host when instantiated (ADR-022's "reads no environment" no longer holds); secrets pass through the environment, and `child_environment` is where a launcher bounds what a child inherits; an undeclared key is refused; removal of stdin is a later milestone's. Say why, not how.

- [ ] **Step 2: Amend ADR-022 and ADR-026**

ADR-022 status line: `Status: Accepted; the source of the mapping decided by ADR-033`. Append beneath the status: "Amendment, appended: `ConfigT` is bound by `AppConfig`, a `BaseSettings`, since ADR-033; the framework reads the environment through it." ADR-026 status line: `Status: Accepted; the stdin configuration sentence superseded by ADR-033`, with a one-line amendment. Touch nothing else in either body.

- [ ] **Step 3: `packaging.md`**

- New section `## Configuration` before "Running a channel": `AppConfig`, `VIBEPY_<FIELD>`, explicit values above the environment, `environment_for` as the parent's rendering, `config_schema` as the list of variables, stdin deprecated for `serve` and `invoke`.
- "Running a channel": drop "one JSON object of configuration is read from standard input. A configuration therefore reaches a running App without a file, an environment variable or an argument vector." Replace with one sentence pointing at Configuration.
- New section `## Opening the Agent channel` with the `mcp` command, what it does, that stdout is the SDK's, and the Codex and Claude Code configuration from the spec (cite both documents).
- "All three commands" → four, in both places; "Invoking one Tool": stdin carries `input`, `config` deprecated.

- [ ] **Step 4: `authoring.md`, `lifecycle.md`, `adapters.md`, `app-model.md`**

- `authoring.md`: replace "the Agent channel's server command is `docs/roadmap.md` M13's" with the command; the "Authoring MCP" section states that it exists and how a platform reaches it, pointing at packaging for the configuration.
- `lifecycle.md`: "over stdio the client launches one server process" → name `python -m vibepy_core.mcp`; the Hub hands configuration through the environment (the sentence about `python -m vibepy_core.serve`).
- `adapters.md`, MCP Adapter: after "the adapter builds an SDK server object; it does not run one", add that `vibepy_core.mcp` runs it over stdio.
- `app-model.md`: `ConfigT: AppConfig` in the signature block; one sentence on where the values come from, pointing at packaging.

- [ ] **Step 5: Spec correction and Studio docstring**

`docs/milestones/M13/spec.md`: "logs one deprecation record" → "emits one `DeprecationWarning`" (two places). Confirm `Processes.start`'s docstring no longer mentions stdin (Task 5).

- [ ] **Step 6: Docstring convention pass**

Read every module touched in Tasks 1–7 and check module and public docstrings say what the file covers and why, in the repository's voice (PEP 257 via ruff `D`). Fix drift: `serve.py` module docstring, `invoke.py` `_Request`, `processes.py` module docstring's last paragraph.

- [ ] **Step 7: Gate and commit**

Run: `make lint typecheck test`

```bash
git add docs packages/vibepy-studio/src
git commit -m "Configuration reaches a process through the environment (ADR-033), and the Agent channel has its command

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 9: Review rounds and structural audit

- [ ] **Step 1: Review the branch** with superpowers:requesting-code-review against `docs/milestones/M13/spec.md`; fix findings, commit.
- [ ] **Step 2: Cross-check against the acceptance criteria** in `docs/roadmap.md` M13 — each criterion names the test that holds it: discovery (`test_authoring_tools_are_discoverable`), delegation (`vibepy_core.mcp` holds no authoring code; `tests/test_channel_neutrality.py`), structured results (`test_an_inspection_arrives_as_structured_content`, `test_an_expected_failure_arrives_as_structured_data`).
- [ ] **Step 3: Structural audit**: grep for a second reading or rendering of configuration (`json.dumps(dict(config))`, `VIBEPY_` literals outside `config.py` and docs), for `BaseModel` still bounding a config, for stdin writes to a framework command. Fix causes in one wave; commit.
- [ ] **Step 4: Hand off** to superpowers:finishing-a-development-branch: `--no-ff` merge into `main`, retire `docs/milestones/M13/` per AGENTS "promote what is still true, then delete the folder", push, read the CI run on macOS and Windows.
