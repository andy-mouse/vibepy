# M17 — Enterprise isolation: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Web channel process the Hub starts lives inside the Hub's window and sees only its own environment: isolated mode, an App folder of its own as working directory, and a stdin pipe whose closing ends it — proven by tests that kill one App, plant modules on the Hub, and kill the Hub.

**Architecture:** All changes are in how Studio (the Hub) runs the framework's commands and where it puts an App; one framework command, `vibepy_core.serve`, gains an opt-in flag. The App / Tool / Page contract is untouched. Spec: `docs/milestones/M17/spec.md`.

**Tech Stack:** Python 3.12, asyncio subprocesses, uv (`uv venv`, `uv pip install`), uvicorn `Server`, pytest with `asyncio_mode = "auto"` and the `integration` marker.

## Global Constraints

- `make lint typecheck test` passes at the end of every task. Run from the repository root.
- No `Any`, no `cast` in public API. Keyword-only optional parameters. Blocking calls in async code go through `asyncio.to_thread`.
- Paths are `pathlib`; a handler reaches `PurePath` only; a concrete `Path` exists where the I/O happens.
- Tests are subject-shaped: one file, one subject. `@pytest.mark.integration` on any test that starts a child process or installs a distribution.
- Standard `logging` only. No `print` outside the fixture App's own output.
- Commit after each task. Commit messages state why, in the repository's style (a sentence, no `feat:` prefix). End each with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- The App folder is `<root>/vibepy-apps/<app>/`, the environment `<root>/vibepy-apps/<app>/env/`, logs stay at `<root>/logs/`.
- `docs/roadmap.md` is never edited.
- `run_studio.py` and the fixtures' `pyproject.toml` files are not changed except where a task names them.

---

## File structure

| File | Responsibility after this plan |
| --- | --- |
| `packages/vibepy-studio/src/vibepy_studio/internals/processes.py` | `python_command` (the one place `-I` is written); `run(..., cwd=)`; `DESCRIBES_THIS_PROCESS` without `PYTHON*` |
| `packages/vibepy-studio/src/vibepy_studio/internals/describing.py` | builds its command with `python_command`, accepts `cwd` |
| `packages/vibepy-studio/src/vibepy_studio/authoring/tools/invocation.py` | builds its command with `python_command` |
| `src/vibepy_core/serve.py` | `--until-stdin-closes`; runs a `uvicorn.Server` it holds |
| `fixtures/timer-app/src/timer_app/entry.py` | `probe` Tool; `home` Page renders it |
| `packages/vibepy-studio/src/vibepy_studio/operating/internals/installer.py` | `app_folder`, `environment` → `…/env`, `remove_app_folder`, `environments` over the new layout |
| `packages/vibepy-studio/src/vibepy_studio/operating/internals/root.py` | `app_folder`, `remove_app_folder`, `describe` in the App folder |
| `packages/vibepy-studio/src/vibepy_studio/operating/internals/processes.py` | `start(..., cwd=)`, `stdin=PIPE` held per child, `--until-stdin-closes` |
| `packages/vibepy-studio/src/vibepy_studio/operating/tools/installation.py` | `remove_app` deletes the App folder |
| `packages/vibepy-studio/src/vibepy_studio/operating/tools/runtime.py` | `start_app` passes the App folder as `cwd` |
| `packages/vibepy-studio/tests/test_isolation.py` | acceptance: what one App can and cannot reach |
| `docs/decisions/ADR-038-…`, `ADR-039-…`, `docs/architecture/packaging.md`, `docs/architecture/lifecycle.md` | the decisions and current truth |

---

### Task 1: One place writes `-I`

**Files:**
- Modify: `packages/vibepy-studio/src/vibepy_studio/internals/processes.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/internals/describing.py:41`
- Modify: `packages/vibepy-studio/src/vibepy_studio/authoring/tools/invocation.py:35-48`
- Modify: `packages/vibepy-studio/src/vibepy_studio/operating/internals/installer.py:144-150`
- Test: `packages/vibepy-studio/tests/test_processes.py`

**Interfaces:**
- Produces: `python_command(python: Sequence[str], /, *args: str) -> list[str]` — `[*python, "-I", *args]`. `python` is the interpreter prefix: `[str(interpreter)]` for an installed App, `["uv", "run", "--project", dir, "python"]` for a source project.
- Produces: `run(command, /, *, stdin=None, env=None, cwd: PurePath | None = None)`.
- Produces: `describe(python, /, *, cwd: PurePath | None = None)` in `describing.py`.

- [ ] **Step 1: Write the failing tests** — append to `packages/vibepy-studio/tests/test_processes.py`:

```python
@pytest.mark.integration
async def test_a_child_does_not_see_what_pythonpath_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The outcome, not the list: `-I` is Python's guarantee that `PYTHON*`
    is ignored, and this is what that guarantee buys the App."""
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "planted_module.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(planted))

    completed = await run(python_command([sys.executable], "-c", "import planted_module"))

    assert completed.returncode != 0
    assert "planted_module" in completed.stderr


@pytest.mark.integration
async def test_a_child_does_not_see_the_launchers_current_directory(tmp_path: Path) -> None:
    """`python -m` and `python -c` put the current directory on `sys.path`;
    `-I` does not, so a module beside the Hub is not the App's."""
    (tmp_path / "beside_the_hub.py").write_text("", encoding="utf-8")

    completed = await run(
        python_command([sys.executable], "-c", "import beside_the_hub"), cwd=tmp_path
    )

    assert completed.returncode != 0


def test_python_command_puts_isolated_mode_before_the_program() -> None:
    assert python_command(["uv", "run", "python"], "-m", "vibepy_core.describe") == [
        "uv", "run", "python", "-I", "-m", "vibepy_core.describe",
    ]
```

Add `python_command` to the import from `vibepy_studio.internals.processes` at the top of the file.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/vibepy-studio/tests/test_processes.py -k "pythonpath or current_directory or python_command" -v`
Expected: FAIL — `ImportError: cannot import name 'python_command'`.

- [ ] **Step 3: Implement** in `vibepy_studio/internals/processes.py`:

Replace `DESCRIBES_THIS_PROCESS` and its docstring's first bullet:

```python
DESCRIBES_THIS_PROCESS = frozenset(
    {
        # the environment this process runs in, which is not the App's; the
        # `PYTHON*` variables are not here because `-I` has Python ignore them
        "VIRTUAL_ENV",
        # the test this process is running, if it is running one
        "PYTEST_CURRENT_TEST",
        # the server this process is serving, if it is serving one
        "NICEGUI_HOST",
        "NICEGUI_PORT",
        "NICEGUI_PROTOCOL",
        "NICEGUI_SCREEN_TEST_PORT",
    }
)
```

Add, after `child_environment`:

```python
def python_command(python: Sequence[str], /, *args: str) -> list[str]:
    """Return the command that runs `args` with the interpreter `python` names, isolated.

    `-I` is Python's own flag for running one party's code with another party's
    interpreter: `sys.path` holds neither the current directory nor the user's
    site-packages, and every `PYTHON*` variable is ignored
    (Python docs, Command line and environment). A virtual environment is still
    recognised, because that is decided by the `pyvenv.cfg` beside the
    interpreter and not by anything `-I` ignores. Every framework command Studio
    runs in an App's environment is built here, so the flag is written once.
    """
    return [*python, "-I", *args]
```

Change `run`'s signature and the spawn:

```python
async def run(
    command: Sequence[str],
    /,
    *,
    stdin: str | None = None,
    env: Mapping[str, str] | None = None,
    cwd: PurePath | None = None,
) -> Completed:
    ...
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL if stdin is None else asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**child_environment(), **(env or {})},
        cwd=None if cwd is None else str(cwd),
    )
```

Add `PurePath` to the `pathlib` import. Add one sentence to the docstring: "`cwd` is where the child runs; nothing here derives it."

In `describing.py`:

```python
async def describe(
    python: Sequence[str], /, *, cwd: PurePath | None = None
) -> tuple[DescribedApp, ...]:
    ...
    completed = await run(python_command(python, "-m", "vibepy_core.describe"), cwd=cwd)
```

Import `python_command` beside `run`, and `PurePath` from `pathlib`.

In `authoring/tools/invocation.py`, replace the list literal handed to `run` with:

```python
            python_command(
                python(project),
                "-m",
                "vibepy_core.invoke",
                payload.app,
                payload.tool,
                "--channel",
                ctx.channel.value,
                "--principal",
                ctx.principal.id,
                *[arg for role in sorted(ctx.principal.roles) for arg in ("--role", role)],
            ),
```

Import `python_command` from `vibepy_studio.internals.processes`.

`installer.describe` is unchanged in this task (it calls `describe_with([str(interpreter(env))])`, which now runs isolated).

- [ ] **Step 4: Run the tests**

Run: `uv run pytest packages/vibepy-studio/tests/test_processes.py -v`
Expected: PASS, including `test_child_environment_drops_vibepy_prefixed_variables` unchanged.

- [ ] **Step 5: Gate and commit**

Run: `make lint typecheck test`
Expected: all pass.

```bash
git add packages/vibepy-studio/src/vibepy_studio/internals/processes.py packages/vibepy-studio/src/vibepy_studio/internals/describing.py packages/vibepy-studio/src/vibepy_studio/authoring/tools/invocation.py packages/vibepy-studio/tests/test_processes.py
git commit -m "Studio runs an App's interpreter in isolated mode: -I is Python's guarantee that the user's site-packages, the launcher's directory and every PYTHON* variable stay out of the App, so the hand-kept list of variables to drop no longer has to be complete

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `serve --until-stdin-closes`

**Files:**
- Modify: `src/vibepy_core/serve.py`
- Test: `tests/test_serve_command.py`

**Interfaces:**
- Produces: `python -m vibepy_core.serve <app> --port <n> [--until-stdin-closes]`. With the flag, EOF on stdin ends the server through uvicorn's normal shutdown and the process exits 0. Without it, behaviour is unchanged.

- [ ] **Step 1: Write the failing test** — append to `tests/test_serve_command.py`:

```python
@pytest.mark.integration
def test_closing_standard_input_ends_the_command_when_asked_to(tmp_path: Path) -> None:
    """The Hub holds the pipe; the OS closes it when the Hub is gone for any
    reason. The App sees end-of-file and leaves through its own shutdown: the
    lifespan's exit runs, and the exit code is a clean one."""
    port = free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vibepy_core.serve",
            "todo-app",
            "--port",
            str(port),
            "--until-stdin-closes",
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=todo_environment(tmp_path),
    )
    assert process.stdin is not None
    wait_for(f"http://127.0.0.1:{port}/todos", process)

    process.stdin.close()
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 0, stderr.decode(errors="replace")
    with pytest.raises(URLError):
        urlopen(f"http://127.0.0.1:{port}/todos", timeout=5)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_serve_command.py::test_closing_standard_input_ends_the_command_when_asked_to -v`
Expected: FAIL — argparse `error: unrecognized arguments: --until-stdin-closes`, exit code 2.

- [ ] **Step 3: Implement** in `src/vibepy_core/serve.py`:

```python
import argparse
import sys
import threading
from collections.abc import Sequence

import uvicorn
...

STARTUP_FAILURE = 3
"""uvicorn's own exit code for a server that never started (`uvicorn.main`)."""


def _end_on_stdin_eof(server: uvicorn.Server, /) -> None:
    """Block on standard input until it closes, then ask the server to leave.

    `should_exit` is what uvicorn's loop polls each tick; the documentation
    exposes no other programmatic stop, so the server's code is the authority.
    Reached only when the launcher asked for it, because a process manager gives
    a service `/dev/null` as standard input and a command that ended on
    end-of-file regardless would end at once under it.
    """
    sys.stdin.buffer.read()
    server.should_exit = True


def _serve(entrypoint: AppEntrypoint[object, AppConfig], port: int, /, *, until_stdin_closes: bool) -> int:
    """Serve one App for as long as its window is open; return the exit code."""
    served = build_web_app(
        entrypoint.definition, entrypoint.lifespan, config={}, principal=OPERATOR
    )
    # The window is the served application's own lifespan, so the `async with`
    # that opens it is the whole of the server's life, and a window that
    # refuses to open fails the server's startup.
    server = uvicorn.Server(
        uvicorn.Config(
            served, host="127.0.0.1", port=port, log_level="warning", log_config=LOG_CONFIG
        )
    )
    if until_stdin_closes:
        threading.Thread(target=_end_on_stdin_eof, args=(server,), daemon=True).start()
    server.run()
    return 0 if server.started else STARTUP_FAILURE
```

In `main`:

```python
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--until-stdin-closes",
        action="store_true",
        help="end the server when standard input reaches end-of-file; for a launcher holding a pipe",
    )
    ...
    return _serve(entrypoint, int(parsed.port), until_stdin_closes=bool(parsed.until_stdin_closes))
```

Update the module docstring's last sentence: "the command reads no configuration from standard input; with `--until-stdin-closes` it reads standard input only to learn that its launcher has gone."

- [ ] **Step 4: Run the serve tests**

Run: `uv run pytest tests/test_serve_command.py -v`
Expected: all PASS — the existing refusal tests still see a non-zero exit (now `3`, which they assert as `!= 0`; `test_a_declaration_the_environment_does_not_hold_is_reported` asserts `== 1` and is unaffected, because that path returns before `_serve`).

- [ ] **Step 5: Gate and commit**

Run: `make lint typecheck test`

```bash
git add src/vibepy_core/serve.py tests/test_serve_command.py
git commit -m "serve ends when its launcher closes its standard input, if the launcher asks: the pipe pattern MCP's stdio transport specifies, so a Web channel process cannot outlive the Hub that holds it, and a process manager that hands a service /dev/null is not told to leave

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Timer's `probe` — the witness inside the App

**Files:**
- Modify: `fixtures/timer-app/src/timer_app/entry.py`
- Test: `tests/test_app_distributions.py` (check whether it asserts Timer's Tool list; adjust the expected list if so)

**Interfaces:**
- Produces: Tool `probe`, input `Probe(module: str)`, output `Probed(cwd: str, sys_path: list[str], importable: bool, wrote: str)`. Invoking it writes the relative file `probe.txt` in the process's working directory and reports where that landed.
- Produces: Page `/home` renders one `ui.label` per field: `cwd=<…>`, `importable=<True|False>`, `wrote=<…>`, and one label per `sys.path` entry prefixed `path=`. The Page probes module `planted_module`.

- [ ] **Step 1: Know what the suites assert about Timer**

Checked while planning: `tests/test_app_distributions.py:90` invokes `elapsed` and nothing asserts Timer's Tool list, so adding a Tool breaks no existing assertion.

- [ ] **Step 2: Implement** in `fixtures/timer-app/src/timer_app/entry.py`, after `Elapsed`:

```python
import importlib.util
import sys
from pathlib import Path


class Probe(BaseModel):
    module: str


class Probed(BaseModel):
    """What this process can see of its host: where it stands, what it imports."""

    cwd: str
    sys_path: list[str]
    importable: bool
    wrote: str


async def probe(_ctx: ToolContext[datetime], payload: Probe) -> Probed:
    """Report the process's working directory and import path, and write one relative file.

    Exists so that a test of the Hub can read, from inside the running App, what
    the Hub let it see. The file is what an App writes when it names a file and
    no folder.
    """
    wrote = Path("probe.txt")
    wrote.write_text("probed", encoding="utf-8")
    return Probed(
        cwd=str(Path.cwd()),
        sys_path=list(sys.path),
        importable=importlib.util.find_spec(payload.module) is not None,
        wrote=str(wrote.resolve()),
    )
```

Change `home`:

```python
async def home(ctx: PageContext) -> None:
    """The Page reaches its domain through a Tool, like any other."""
    since = Elapsed.model_validate(await ctx.tools.invoke("elapsed", {}))
    ui.label(f"open for {since.seconds:.0f}s")
    probed = Probed.model_validate(await ctx.tools.invoke("probe", {"module": "planted_module"}))
    ui.label(f"cwd={probed.cwd}")
    ui.label(f"importable={probed.importable}")
    ui.label(f"wrote={probed.wrote}")
    for entry in probed.sys_path:
        ui.label(f"path={entry}")
```

Add the Tool and widen the Page's declaration:

```python
        Tool(
            definition=ToolDefinition(
                name="probe",
                description="Where this process stands and what it can import",
                input_model=Probe,
                output_model=Probed,
                read_only=True,
            ),
            handler=probe,
        ),
    ...
            definition=PageDefinition(
                name="home", route="/home", title="Timer", tools=frozenset({"elapsed", "probe"})
            ),
```

Put the new imports with the others at the top of the file. Add to the module docstring: "Its `probe` Tool is the witness M17's isolation tests read: what the Hub let this process see, reported from inside it."

- [ ] **Step 3: Run the suites that install or describe Timer**

Run: `uv run pytest tests/test_app_distributions.py packages/vibepy-studio/tests/test_addresses.py -v`
Expected: PASS.

- [ ] **Step 4: Gate and commit**

Run: `make lint typecheck test`

```bash
git add fixtures/timer-app/src/timer_app/entry.py
git commit -m "Timer gains probe: the App-side witness that reports, from inside the running process, what the Hub let it see — its working directory, its import path, and whether a planted module imports

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: An App's folder — `vibepy-apps/<app>/env`

**Files:**
- Modify: `packages/vibepy-studio/src/vibepy_studio/operating/internals/installer.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/operating/internals/root.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/operating/internals/__init__.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/operating/tools/installation.py:264-268`
- Modify: `packages/vibepy-studio/tests/conftest.py:94,115,121`
- Modify: `packages/vibepy-studio/tests/test_installation.py:32-34,225,268,385`
- Modify: `packages/vibepy-studio/tests/test_addresses.py:96`
- Test: `packages/vibepy-studio/tests/test_installation.py`, `packages/vibepy-studio/tests/test_update.py`

**Interfaces:**
- Produces (installer): `APPS_DIR = "vibepy-apps"`, `ENV_DIR = "env"`; `app_folder(root, app_name, /) -> PurePath` (the name gate, returns `root/vibepy-apps/<app>`); `environment(root, app_name, /) -> PurePath` (= `app_folder(...) / "env"`); `remove_app_folder(folder, /)`; `environments(root)` returns every `vibepy-apps/*/env` that is a directory.
- Produces (root): `StudioRoot.app_folder(app_name) -> PurePath` (pure), `StudioRoot.remove_app_folder(app_name)`.
- `install(*, wheel, source, env)` creates `env.parent` first (`mkdir(parents=True, exist_ok=True)`), then `uv venv env`.
- `remove_environment` still deletes only `env/`.

- [ ] **Step 1: Write the failing tests** — in `packages/vibepy-studio/tests/test_installation.py` change the helper and add two tests:

```python
def environment(root: Path, app_name: str, /) -> Path:
    """Where Studio's declared root holds one App's environment, as the spec describes it."""
    return root / "vibepy-apps" / app_name / "env"
```

Replace the `envs` literals at the three other lines with `"vibepy-apps" / <name> / "env"` (line 225: `(root / "vibepy-apps" / "todo" / "env").mkdir(parents=True)`; line 268: `assert hub_environment(tmp_path, "todo") == tmp_path / "vibepy-apps" / "todo" / "env"`; line 385 likewise). Add:

```python
@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_removing_an_app_deletes_its_whole_folder(installed: Path) -> None:
    """The folder is the Hub's unit: what the App wrote beside its environment goes with it."""
    folder = installed / "vibepy-apps" / "vibepy-todo"
    (folder / "scratch.txt").write_text("mine", encoding="utf-8")

    async with studio(installed) as tools:
        await tools.invoke("remove_app", {"app_name": "vibepy-todo"}, principal=AGENT)

    assert not folder.exists()


def test_app_folder_is_the_environments_parent(tmp_path: Path) -> None:
    assert hub_app_folder(tmp_path, "todo") == tmp_path / "vibepy-apps" / "todo"
    assert hub_environment(tmp_path, "todo").parent == hub_app_folder(tmp_path, "todo")
```

Import `app_folder as hub_app_folder` beside `environment as hub_environment` (find the existing import line with `hub_environment`).

In `packages/vibepy-studio/tests/test_update.py`, extend `test_a_newer_wheel_is_offered_and_updating_keeps_configuration_port_and_route` with, before the update is invoked:

```python
    beside = installed / "vibepy-apps" / "vibepy-todo" / "kept.txt"
    beside.write_text("kept", encoding="utf-8")
```

and after it:

```python
    assert beside.read_text(encoding="utf-8") == "kept"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/vibepy-studio/tests/test_installation.py packages/vibepy-studio/tests/test_update.py -v -x`
Expected: FAIL — `ImportError` on `app_folder`, then path assertions against `envs`.

- [ ] **Step 3: Implement** in `installer.py`:

```python
APPS_DIR = "vibepy-apps"
"""Where the root keeps one folder per installed App."""

ENV_DIR = "env"
"""The virtual environment inside an App's folder; update remakes this alone."""


def app_folder(root: PurePath, app_name: str, /) -> PurePath:
    """Where Studio keeps one App: its environment, and whatever it writes beside it.

    <the existing `environment` docstring, with `envs` read as `vibepy-apps`>
    """
    apps = root / APPS_DIR
    candidate = PurePath(os.path.normpath(apps / app_name))
    if candidate.parent != apps or candidate.name != app_name:
        raise AppNameInvalid(app_name)
    return candidate


def environment(root: PurePath, app_name: str, /) -> PurePath:
    """Where one App's virtual environment lives, inside its folder."""
    return app_folder(root, app_name) / ENV_DIR
```

In `install`, before `uv venv`:

```python
    await asyncio.to_thread(Path(env).parent.mkdir, parents=True, exist_ok=True)
    await _run(["uv", "venv", str(env)])
```

Add:

```python
async def remove_app_folder(folder: PurePath, /) -> None:
    """Delete one App's folder — its environment and what it wrote beside it — if it is there."""
    await asyncio.to_thread(_remove_environment, folder)
```

Change `_environments`:

```python
def _environments(root: PurePath, /) -> tuple[PurePath, ...]:
    apps = Path(root) / APPS_DIR
    if not apps.is_dir():
        return ()
    return tuple(
        PurePath(folder / ENV_DIR)
        for folder in sorted(apps.iterdir())
        if (folder / ENV_DIR).is_dir()
    )
```

In `root.py`:

```python
    async def installed(self) -> tuple[str, ...]:
        """Return the name of every App this Studio installed, in a stable order."""
        return tuple(env.parent.name for env in await environments(self._path))

    def app_folder(self, app_name: str, /) -> PurePath:
        """Return this App's folder, where its process runs. Computes a path and reads nothing."""
        return app_folder(self._path, app_name)

    async def remove_app_folder(self, app_name: str, /) -> None:
        """Delete this App's folder whole, if it is there."""
        await remove_app_folder(app_folder(self._path, app_name))

    async def describe(self, app_name: str, /) -> tuple[AppFacts, ...]:
        """Return what the Apps in this App's environment declare, read in that environment and its folder."""
        return await describe_environment(
            environment(self._path, app_name), cwd=app_folder(self._path, app_name)
        )
```

`installer.describe` gains `cwd`:

```python
async def describe(env: PurePath, /, *, cwd: PurePath | None = None) -> tuple[AppFacts, ...]:
    """Return what the Apps in one environment declare, read in that environment, run in `cwd`."""
    try:
        described = await describe_with([str(interpreter(env))], cwd=cwd)
```

Export `app_folder`, `remove_app_folder`, `APPS_DIR`, `ENV_DIR` from `operating/internals/__init__.py` (add to the import and to `__all__`, sorted).

In `installation.py`, `remove_app`:

```python
    """Delete an App's folder — environment and what it wrote beside it — leaving the data it wrote elsewhere."""
    deps = ctx.dependencies
    await deps.processes.stop(payload.app_name)
    await deps.root.remove_app_folder(payload.app_name)
```

The three `remove_environment` calls in `_install_offered` and the one in `update_app` stay: a failed install or an update removes the environment, and the folder is the App's.

In `conftest.py`:
- line 94: `envs/` → `vibepy-apps/`
- line 115: `if Path(directory) != template_root / "vibepy-apps":`
- line 121: `for recorded in root.glob(f"vibepy-apps/*/env/{FACTS_FILE}"):`

In `test_addresses.py:96`: `env = (root / "vibepy-apps" / "vibepy-todo" / "env").is_dir()`.

- [ ] **Step 4: Run the Studio suite**

Run: `uv run pytest packages/vibepy-studio/tests -v`
Expected: PASS. If `test_a_traversing_app_name_deletes_nothing` fails, the gate in `app_folder` is not being reached by `remove_app_folder`; fix the call path, not the test.

- [ ] **Step 5: Recreate the development root and gate**

Run: `rm -rf .studio-dev` (confirm with the owner first if the directory holds anything but fixture installs) and `make lint typecheck test`.

```bash
git add packages/vibepy-studio/src packages/vibepy-studio/tests
git commit -m "An installed App has a folder of its own, vibepy-apps/<app>, and its environment lives inside it: the folder is what remove deletes and what the App's process will stand in, and env/ is what update remakes, so what an App writes beside its environment survives a new version

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: The child stands in its folder and dies with the Hub

**Files:**
- Modify: `packages/vibepy-studio/src/vibepy_studio/operating/internals/processes.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/operating/tools/runtime.py:80-87`
- Test: `packages/vibepy-studio/tests/test_processes.py`

**Interfaces:**
- Produces: `Processes.start(*, app_name, interpreter, config, known_as, port, cwd: PurePath)` — `cwd` is required; the command is `python_command([str(interpreter)], "-m", "vibepy_core.serve", app_name, "--port", str(port), "--until-stdin-closes")`; the child's stdin is a pipe this window holds in `_Child.stdin` and closes in `_release` and `stop`.

- [ ] **Step 1: Write the failing tests** — in `packages/vibepy-studio/tests/test_processes.py`, add `cwd=tmp_path` to every existing `processes.start(...)` call (four of them), then append:

```python
DRIVER = """
import asyncio, sys
from pathlib import Path
from vibepy_studio.operating.internals.processes import Processes

async def main() -> None:
    port = int(sys.argv[1])
    root = Path(sys.argv[2])
    processes = Processes(logs=root / "logs")
    await processes.start(
        app_name="todo-app",
        interpreter=Path(sys.executable),
        config={"db_path": str(root / "todo.json"), "db_key": "k"},
        known_as="todo-app",
        port=port,
        cwd=root,
    )
    print("started", flush=True)
    await asyncio.sleep(3600)

asyncio.run(main())
"""


@pytest.mark.integration
async def test_a_killed_launcher_leaves_no_live_child(tmp_path: Path) -> None:
    """The half of process isolation `aclose` cannot cover: the Hub that is
    killed runs no cleanup. The child holds the read end of a pipe whose write
    end died with the Hub, sees end-of-file, and leaves on its own."""
    port = free_port()
    driver = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        DRIVER,
        str(port),
        str(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        env=child_environment(),
    )
    assert driver.stdout is not None
    async with asyncio.timeout(OWNED_TIMEOUT):
        assert (await driver.stdout.readline()).strip() == b"started"

    driver.kill()
    await driver.wait()

    async with asyncio.timeout(OWNED_TIMEOUT):
        while True:
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", port)
            except OSError:
                break
            writer.transport.abort()
            await asyncio.sleep(0.05)


@pytest.mark.integration
async def test_a_child_stands_in_the_directory_it_is_given(tmp_path: Path) -> None:
    """`probe.txt` is what Timer writes when it names a file and no folder."""
    stand = tmp_path / "stand"
    stand.mkdir()
    processes = Processes(logs=tmp_path / "logs")
    port = free_port()
    await processes.start(
        app_name="timer-app",
        interpreter=Path(sys.executable),
        config={},
        known_as="timer-app",
        port=port,
        cwd=stand,
    )
    try:
        body = await asyncio.to_thread(_body, f"http://127.0.0.1:{port}/home")
    finally:
        await processes.aclose()

    assert f"cwd={stand.resolve()}" in body
    assert (stand / "probe.txt").is_file()
```

Add at the top:

```python
from urllib.request import urlopen


def _body(url: str, /) -> str:
    with urlopen(url, timeout=30) as answer:
        return answer.read().decode(errors="replace")
```

`timer-app` is declared in this interpreter's environment the way `todo-app` is (both fixtures are workspace members); if `test_a_child_stands_in_the_directory_it_is_given` fails with `app.not_declared`, run `make install` first.

NiceGUI writes a Page's labels into the initial HTML (verified while planning: `curl /home` on a served Timer returns `open for 0s` in the body), so reading the body is enough.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/vibepy-studio/tests/test_processes.py -v -x`
Expected: FAIL — `TypeError: start() got an unexpected keyword argument 'cwd'`.

- [ ] **Step 3: Implement** in `operating/internals/processes.py`:

```python
from vibepy_studio.internals.processes import child_environment, python_command, reported
...

class _Child:
    """One started App: the process, the pipe that is its lease on life, and whether it has answered.

    The port is not here. It belongs to the installation and the Hub holds it;
    this window is told which port to serve on and needs no memory of it.

    `stdin` is the write end of the child's standard input. The child was told
    to leave when it reaches end-of-file, so this window ends the child by
    closing it, and a window that dies without closing anything ends the child
    all the same: the operating system closes what a dead process held.
    """

    process: asyncio.subprocess.Process
    stdin: asyncio.StreamWriter
    answering: bool = False
```

In `start`:

```python
    async def start(
        self,
        *,
        app_name: str,
        interpreter: PurePath,
        config: Mapping[str, JsonValue],
        known_as: str,
        port: int,
        cwd: PurePath,
    ) -> None:
        """Serve one App on the port it was given, in an environment of its own, standing in `cwd`.

        <existing paragraphs>

        The child's standard input is a pipe this window holds, and the child is
        told `--until-stdin-closes`: its life is this window's. The child's
        working directory is `cwd`, the App's own folder, so a file it names
        without a folder lands there and nowhere the Hub or another App stands.
        """
        ...
            process = await asyncio.create_subprocess_exec(
                *python_command(
                    [str(interpreter)],
                    "-m",
                    "vibepy_core.serve",
                    app_name,
                    "--port",
                    str(port),
                    "--until-stdin-closes",
                ),
                stdin=asyncio.subprocess.PIPE,
                stderr=handle,
                env={**child_environment(), **environment_for(config)},
                cwd=str(cwd),
            )
        finally:
            await asyncio.to_thread(handle.close)
        assert process.stdin is not None
        child = _Child(process=process, stdin=process.stdin)
```

In `_release` and `stop`, close the pipe before terminating:

```python
    async def _release(self, known_as: str, /) -> None:
        """Give up a claimed name, killing and reaping its child if it got one."""
        child = self._running.pop(known_as, None)
        if child is None:
            return
        child.stdin.close()
        if child.process.returncode is None:
            child.process.kill()
        await child.process.wait()

    async def stop(self, app_name: str, /) -> bool:
        """Close the child's standard input and terminate it, then kill it if it does not leave."""
        child = self._running.pop(app_name, None)
        if child is None:
            return False
        child.stdin.close()
        process = child.process
        ...
```

In `runtime.py`, `start_app`:

```python
        await deps.processes.start(
            app_name=facts.described.app_name,
            interpreter=deps.root.interpreter(payload.app_name),
            config={**held, **payload.secrets},
            known_as=payload.app_name,
            port=port,
            cwd=deps.root.app_folder(payload.app_name),
        )
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest packages/vibepy-studio/tests/test_processes.py packages/vibepy-studio/tests/test_runtime.py -v`
Expected: PASS.

- [ ] **Step 5: Gate and commit**

Run: `make lint typecheck test`

```bash
git add packages/vibepy-studio/src/vibepy_studio/operating/internals/processes.py packages/vibepy-studio/src/vibepy_studio/operating/tools/runtime.py packages/vibepy-studio/tests/test_processes.py
git commit -m "A started App stands in its own folder and holds a pipe from the Hub: its working directory is vibepy-apps/<app>, and its standard input is what the Hub's death closes, so the child leaves with the window that started it — ADR-020 implemented for the case where the Hub runs no cleanup

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Acceptance — `test_isolation.py`

**Files:**
- Create: `packages/vibepy-studio/tests/test_isolation.py`

**Interfaces:**
- Consumes: `studio(root)`, `AGENT`, `served_body`-style HTTP reading from `tests_support`; the `installed` fixture with `@pytest.mark.apps("vibepy-todo", "vibepy-timer")`; Timer's `/home` labels from Task 3; `Processes.owned` for the pid to kill.

- [ ] **Step 1: Write the tests**

```python
"""What one installed App can and cannot reach of another App and of its host.

The isolation invariant (`docs/architecture/packaging.md`) is kept by the Hub's
construction; these are the tests that prove the construction holds, read from
inside a running App through Timer's `probe`.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.request import urlopen

import pytest

from tests_support import AGENT, studio
from vibepy_core import Channel
from vibepy_core.app.composition import tool_runtime_for
from vibepy_core.tool import ToolRuntime
from vibepy_studio.entry import APP, STUDIO_APP, StudioConfig
from vibepy_studio.operating.internals import StudioDeps
from vibepy_studio.operating.internals.state import read_state
from vibepy_studio.operating.models import AppListing, RunningApp

WAIT = 30.0


@asynccontextmanager
async def hub(root: Path, /) -> AsyncGenerator[tuple[ToolRuntime[StudioDeps], StudioDeps]]:
    """One Studio window, and the resource it opened over — so a test can reach the child.

    `ToolRuntime` keeps its dependencies private, rightly; a test that must kill
    a child by hand wraps the lifespan and keeps what it yielded.
    """
    held: list[StudioDeps] = []

    @asynccontextmanager
    async def capturing(config: StudioConfig) -> AsyncGenerator[StudioDeps]:
        async with APP.lifespan(config) as deps:
            held.append(deps)
            yield deps

    async with tool_runtime_for(
        STUDIO_APP, capturing, config={"root": str(root), "proxy_port": 8080}, channel=Channel.WEB
    ) as tools:
        yield tools, held[0]


async def _start(tools: ToolRuntime[StudioDeps], app_name: str, /) -> RunningApp:
    started = await tools.invoke(
        "start_app", {"app_name": app_name, "secrets": {}}, principal=AGENT
    )
    assert isinstance(started, RunningApp)
    assert started.diagnostic is None, started.diagnostic
    return started


def _body(url: str, /) -> str:
    with urlopen(url, timeout=WAIT) as answer:
        return answer.read().decode(errors="replace")


async def _states(tools: ToolRuntime[StudioDeps]) -> dict[str, str]:
    listed = await tools.invoke("list_apps", {}, principal=AGENT)
    assert isinstance(listed, AppListing)
    return {row.app_name: row.state for row in listed.apps}


async def _gone(port: int, /) -> None:
    async with asyncio.timeout(WAIT):
        while True:
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", port)
            except OSError:
                return
            writer.transport.abort()
            await asyncio.sleep(0.05)


@pytest.mark.apps("vibepy-todo", "vibepy-timer")
@pytest.mark.integration
async def test_one_apps_death_leaves_the_other_and_the_hub_standing(
    tmp_path: Path, installed: Path
) -> None:
    async with hub(installed) as (tools, deps):
        await tools.invoke(
            "configure_app",
            {"app_name": "vibepy-todo", "values": {"db_path": str(tmp_path / "todo.db"), "db_key": "k"}},
            principal=AGENT,
        )
        await _start(tools, "vibepy-todo")
        await _start(tools, "vibepy-timer")
        ports = (await read_state(installed)).ports

        todo = deps.processes.owned("vibepy-todo")
        assert todo is not None
        todo.kill()
        await todo.wait()

        body = await asyncio.to_thread(_body, f"http://127.0.0.1:{ports['vibepy-timer']}/home")
        assert "open for" in body
        states = await _states(tools)
        assert states["vibepy-todo"] == "installed"
        assert states["vibepy-timer"] == "running"

        await _gone(ports["vibepy-todo"])
        await _start(tools, "vibepy-todo")
        assert (await _states(tools))["vibepy-todo"] == "running"


@pytest.mark.apps("vibepy-timer")
@pytest.mark.integration
async def test_an_app_sees_neither_the_hubs_python_path_nor_its_directory(
    tmp_path: Path, installed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Planted on the Hub, in the two places Python would otherwise look."""
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "planted_module.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(planted))
    monkeypatch.chdir(planted)

    async with studio(installed) as tools:
        await _start(tools, "vibepy-timer")
        port = (await read_state(installed)).ports["vibepy-timer"]
        body = await asyncio.to_thread(_body, f"http://127.0.0.1:{port}/home")

    assert "importable=False" in body
    assert f"path={planted}" not in body
    assert f"cwd={installed / 'vibepy-apps' / 'vibepy-timer'}" in body


@pytest.mark.apps("vibepy-todo", "vibepy-timer")
@pytest.mark.integration
async def test_what_an_app_writes_beside_itself_is_its_own(tmp_path: Path, installed: Path) -> None:
    """Timer writes `probe.txt` where it stands; it lands in Timer's folder, not
    the Hub's directory and not Todo's folder, and leaves with Timer."""
    timer = installed / "vibepy-apps" / "vibepy-timer"
    todo = installed / "vibepy-apps" / "vibepy-todo"

    async with studio(installed) as tools:
        await _start(tools, "vibepy-timer")
        port = (await read_state(installed)).ports["vibepy-timer"]
        await asyncio.to_thread(_body, f"http://127.0.0.1:{port}/home")
        await tools.invoke("stop_app", {"app_name": "vibepy-timer"}, principal=AGENT)

        assert (timer / "probe.txt").is_file()
        assert not (todo / "probe.txt").exists()
        assert not (Path.cwd() / "probe.txt").exists()

        await tools.invoke("remove_app", {"app_name": "vibepy-timer"}, principal=AGENT)

    assert not timer.exists()
```

`StudioConfig` is exported from `vibepy_studio.entry` beside `APP` and `STUDIO_APP` (check with `grep -n "^class StudioConfig" packages/vibepy-studio/src/vibepy_studio/entry.py`; it is defined there).

- [ ] **Step 2: Run them**

Run: `uv run pytest packages/vibepy-studio/tests/test_isolation.py -v`
Expected: PASS. The survival of `update_app` for a file beside `env/` is asserted in Task 4's `test_update.py`, so it is not repeated here.

- [ ] **Step 3: Gate and commit**

Run: `make lint typecheck test`

```bash
git add packages/vibepy-studio/tests/test_isolation.py
git commit -m "The isolation invariant is tested, not believed: one App's death leaves the other and the Hub standing, a module planted on the Hub does not reach an App, and what an App writes beside itself is its own and leaves with it

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Decisions and current truth

**Files:**
- Create: `docs/decisions/ADR-038-isolation-between-installed-apps-is-against-accidents-not-adversaries.md`
- Create: `docs/decisions/ADR-039-a-channel-process-lives-while-its-host-holds-its-standard-input.md`
- Modify: `docs/architecture/packaging.md` (Running a channel; The isolation invariant)
- Modify: `docs/architecture/lifecycle.md` (Package lifecycle; This layer's capabilities)
- Modify: `packages/vibepy-studio/src/vibepy_studio/operating/internals/installer.py` (`install` docstring)

- [ ] **Step 1: ADR-038** — Nygard format, `Status: Accepted`, sections Context / Decision / Consequences. Context: the four gaps and the question of what isolation is *for*; the fact that processes of one user account are one security principal on macOS and Windows; the two classes of host (Android / `DynamicUser=` / snap versus pipx / conda / Homebrew services). Decision: isolation between installed Apps is against accidents — dependency conflicts, path collisions, crashes, orphaned processes — between Apps an operator chose to install; it is not a security boundary between mutually distrusting Apps. Consequences: an App can reach another App's loopback port and folder and a secret in another App's environment, and that is a consequence of this decision rather than an omission; CPU and memory limits have no mechanism common to both platforms and are not part of isolation; a future boundary means a principal per App or a sandbox, which is a different product shape and a new record. Cite `docs/milestones/M17/spec.md` sources for the platform facts; do not restate what `packaging.md` will own.

- [ ] **Step 2: ADR-039** — Context: ADR-020 places a runtime inside its host's window and ADR-017 has the agent platform end the Agent channel process, yet the Web channel process the Hub started outlived a Hub that died without cleanup, leaving a running App the Hub reports `installed`, cannot stop, and cannot restart. Two models exist — re-adoption (Docker live-restore, systemd cgroups) and linkage (LSP `processId`, MCP stdio, Erlang links) — and `processes.py` already rules out observing an arbitrary pid. Decision: a channel process the Hub starts lives while the Hub holds its standard input; `serve` is told so with `--until-stdin-closes`, and the Hub holds a pipe. Consequences: no platform branch (the OS closes a dead process's handles on both platforms; PEP 446 keeps the pipe out of other children); the Web and Agent channel processes obey one rule; the flag is opt-in because a process manager hands a service `/dev/null`; `serve` still reads no configuration from standard input; a Hub restart finds no child to re-adopt and none running.

- [ ] **Step 3: `packaging.md`**
  - Running a channel: after the command block, one paragraph: the Hub runs it as `python -I -m vibepy_core.serve … --until-stdin-closes` from the App's folder; `-I` is what keeps the App's `sys.path` its own, cite the Python docs sentence; `--until-stdin-closes` is ADR-039's flag and what it means. Same `-I` note in The self-description command and Invoking one Tool: "Studio runs this isolated (`-I`); see Running a channel."
  - The isolation invariant: rewrite the third row's Enforced-by to "the installation model, kept by construction: the Hub creates `vibepy-apps/<app>/env` per App with `uv venv`, runs the App's interpreter with `-I`, and `packages/vibepy-studio/tests/test_isolation.py` proves a module planted on the Hub does not reach an App. Python packaging cannot enforce it; nothing stops two Apps being installed into one environment by hand." Remove "M17 owns hardening it". Add a fourth row: "installed files are immutable | a contract of the App and the Hub: the Hub never writes inside an environment, and an App does not modify its installed files in place. `uv pip install --link-mode hardlink` shares the cache's inodes with every environment for the measured reason in `installer.install`, and sharing is correct exactly as long as this holds. Not enforceable by packaging." Add after the table: a sentence that what isolation is against, and what it is not, is ADR-038's.
  - What a command writes… unchanged. Invariants list: add "a channel process the Hub starts ends when the Hub's window closes or the Hub dies (ADR-039)".

- [ ] **Step 4: `lifecycle.md`**
  - Package lifecycle, the paragraph that starts "Operations such as install…": after "handing that process the App's configuration through its environment", add: "in the App's own folder, `<root>/vibepy-apps/<app>/`, whose `env/` is the App's virtual environment. The folder is the unit `remove_app` deletes and `update_app` remakes `env/` inside; the child's standard error goes to `<root>/logs/<app>.log`, which is the Hub's record and survives removal. The Hub holds the child's standard input, and the child leaves when that closes — with the window, or with a Hub that died (ADR-039)."
  - This layer's capabilities table, `install_app, update_app, remove_app` row: "a folder of its own per App, holding an environment: created, the environment remade at a newer version, the folder destroyed". The sentence "An update keeps what the Hub holds for an App — its configuration values, its port, its route — and remakes only the environment" gains "and what the App wrote beside its environment".

- [ ] **Step 5: `installer.install` docstring** — after "The Hub never writes inside an environment it installed, which is what makes sharing an inode with the cache safe.", add: "The other half of that premise is the App's: an App does not modify its installed files in place, as pnpm's and Nix's stores assume of what they link. `docs/architecture/packaging.md` states it as a row of the isolation invariant."

- [ ] **Step 6: Check references**

Run: `grep -rn "envs/\|M17 owns\|hardening it" docs/architecture docs/decisions/ADR-038* docs/decisions/ADR-039* packages/vibepy-studio/src`
Expected: no `envs/`, no "M17 owns hardening it" outside `docs/milestones/` and `docs/roadmap.md`.

- [ ] **Step 7: Gate and commit**

Run: `make lint typecheck test`

```bash
git add docs/decisions/ADR-038-isolation-between-installed-apps-is-against-accidents-not-adversaries.md docs/decisions/ADR-039-a-channel-process-lives-while-its-host-holds-its-standard-input.md docs/architecture/packaging.md docs/architecture/lifecycle.md packages/vibepy-studio/src/vibepy_studio/operating/internals/installer.py
git commit -m "Two decisions and the truth they leave: isolation between installed Apps is against accidents and not adversaries (ADR-038), a channel process lives while its host holds its standard input (ADR-039), and packaging.md's isolation invariant is now kept by construction, with immutability of installed files as its fourth row

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Convention pass and the gate

**Files:**
- Every file touched by Tasks 1–7.

- [ ] **Step 1: Docstring convention** — every new or changed public function, class and module docstring states what it does and why, in the repository's voice (see any neighbour); no docstring restates a signature. Fix in place.

- [ ] **Step 2: Structural audit** — for each: is there a second copy of something that already existed (`-I` written anywhere but `python_command`; a `vibepy-apps` literal anywhere but `installer.APPS_DIR` and tests; an `envs` left behind)? Run `grep -rn '"-I"\|vibepy-apps\|"envs"' src packages/vibepy-studio/src fixtures scripts` and resolve every hit outside its owner.

- [ ] **Step 3: The whole gate, twice**

Run: `make lint typecheck test` — then `uv run pytest -m integration -p no:randomly` if `pytest-randomly` is present, else `uv run pytest packages/vibepy-studio/tests/test_isolation.py packages/vibepy-studio/tests/test_processes.py tests/test_serve_command.py -v` a second time to catch an order-dependent child.
Expected: green both times. Record the macOS wall time of `make test` before and after the branch in the final commit message (from `git stash`-free measurement: check out `main` in a worktree and time it there).

- [ ] **Step 4: Commit any convention fixes**

```bash
git add -A
git commit -m "M17 convention pass: docstrings say why, and -I, vibepy-apps and env each have one owner

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

Then stop: the branch is ready for the two review rounds and the structural audit before merge (`finishing-a-development-branch`). Integration — promoting the spec into the architecture documents and deleting `docs/milestones/M17/` — happens on merge, per `AGENTS.md`.
