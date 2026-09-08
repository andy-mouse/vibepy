# M10 Hub Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Hub as a platform-tier App that installs, configures, starts, stops and lists other Apps, plus the framework command that opens an App's Web channel.

**Architecture:** The repository becomes a uv workspace with three distributions: `vibepy-framework` at the root, `vibepy-hub` in `hub/`, and `vibepy-todo` in `samples/todo/`. The Hub is an ordinary App — eight Tools over domain internals that call `uv`, read registered folders, hold child processes and read and write one state file. The framework gains `python -m vibepy.serve`, which opens a Page window inside NiceGUI's own startup and shutdown hooks and calls `ui.run`.

**Tech Stack:** Python 3.12, Pydantic v2, NiceGUI, uv (workspace and installer), stdlib `tomllib`, `asyncio.create_subprocess_exec`, pytest with `asyncio_mode = auto`.

## Global Constraints

- `requires-python = ">=3.12"` in every project file
- one `pyproject.toml` per distribution; the root file is also the workspace root
- `vibepy-hub` and `vibepy-todo` depend on `vibepy-framework` through `tool.uv.sources` with `workspace = true`; the framework depends on neither
- ruff `line-length = 100`; lint and format run over `src tests hub samples`
- pyright `typeCheckingMode = "strict"` over the same paths
- `Any` and `cast` are not acceptable in a public API; use `Protocol`, `TypedDict`, dataclass or `TypeVar`
- optional and configuration parameters are keyword-only
- filesystem paths are `pathlib.Path`, never strings
- standard `logging` only, `getLogger(__name__)` per module, no `print` (`vibepy.serve` writes to `sys.stdout`/`sys.stderr` as a command, like `vibepy.describe`)
- blocking calls inside async code are wrapped in `asyncio.to_thread`
- no new framework exception and no new entry in `vibepy/errors.py`; Hub diagnostics are fields in Tool output models
- a Tool output must round-trip `model_dump(by_alias=True)` into `model_validate`, so no live object travels in an output
- `make lint typecheck test` passes before a task is done

---

### Task 1: The workspace and the first real App distribution

**Files:**
- Modify: `pyproject.toml`
- Create: `samples/todo/pyproject.toml`
- Create: `samples/todo/src/todo_app/__init__.py`
- Create: `samples/todo/src/todo_app/entry.py`
- Create: `samples/notes/pyproject.toml`
- Create: `samples/notes/src/notes_app/__init__.py`
- Create: `samples/notes/src/notes_app/entry.py`
- Delete: `tests/todo_fixture.py`
- Modify: `tests/test_dual_channel.py`, `tests/test_app_composition.py`, `tests/test_app_config.py`, `tests/test_app_isolation.py`, `tests/test_execution_semantics.py`, `tests/test_mcp_adapter.py`, `tests/test_nicegui_adapter.py`, `tests/test_describe_command.py` (every importer of `tests.todo_fixture`)
- Test: `tests/test_todo_distribution.py`

**Interfaces:**
- Consumes: nothing
- Produces: `todo_app.entry.APP: AppEntrypoint[TodoStore, TodoConfig]`, `todo_app.entry.TODO_APP: AppDefinition[TodoStore, TodoConfig]`, `todo_app.entry.TodoConfig`, `todo_app.entry.TodoStore`, `todo_app.entry.TODO_CONFIG: dict[str, object]`. The distribution declares `todo = "todo_app.entry:APP"` in the `vibepy.apps` entry point group. A second distribution declares `notes = "notes_app.entry:APP"` and produces `notes_app.entry.APP`, an App with one Tool and no Pages — the App that has no Web channel to start.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_todo_distribution.py
"""The Todo App is a distribution, discoverable without importing it."""

from vibepy.app.package import discover_apps


def test_the_todo_distribution_declares_its_app() -> None:
    declared = {ref.app_name: ref for ref in discover_apps()}
    assert "todo" in declared
    ref = declared["todo"]
    assert ref.distribution == "vibepy-todo"
    assert (ref.module, ref.attr) == ("todo_app.entry", "APP")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_todo_distribution.py -v`
Expected: FAIL — `"todo" in declared` is false, because no distribution declares it.

- [ ] **Step 3: Declare the workspace**

Add to the root `pyproject.toml`, after `[project]`:

```toml
[tool.uv.workspace]
members = ["hub", "samples/*"]
```

`hub/` does not exist yet, so create `hub/pyproject.toml` in Task 3 — until then remove `"hub"` from `members` and add it back there. The `samples/*` glob covers both samples this task creates. Also widen the tool paths:

```toml
[tool.ruff]
line-length = 100
src = ["src", "tests", "hub/src", "samples/todo/src", "samples/notes/src"]

[tool.pyright]
include = ["src", "tests", "hub/src", "samples/todo/src", "samples/notes/src"]
pythonVersion = "3.12"
typeCheckingMode = "strict"
```

And in the `Makefile`, replace `src tests` with `src tests hub samples` in the `lint` and `format` targets.

- [ ] **Step 4: Create the Todo distribution**

```toml
# samples/todo/pyproject.toml
[project]
name = "vibepy-todo"
version = "0.1.0"
description = "The Todo sample App from docs/roadmap.md"
requires-python = ">=3.12"
dependencies = ["vibepy-framework"]

[project.entry-points."vibepy.apps"]
todo = "todo_app.entry:APP"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/todo_app"]

[tool.uv.sources]
vibepy-framework = { workspace = true }
```

- [ ] **Step 5: Move the App out of the test fixture**

`samples/todo/src/todo_app/__init__.py` holds the module docstring `"""The Todo sample App."""` and nothing else.

`samples/todo/src/todo_app/entry.py` is `tests/todo_fixture.py` moved verbatim, with two changes: the module docstring becomes

```python
"""The Todo sample App from docs/roadmap.md.

The App the Hub installs and starts. Its store keeps todos in memory, which is
enough for one window; an App that must agree across its channels reaches a
backing service, as `docs/architecture/app-model.md` requires.
"""
```

and the final binding is renamed so the entry point can name it:

```python
APP: AppEntrypoint[TodoStore, TodoConfig] = AppEntrypoint(
    definition=TODO_APP, lifespan=todo_lifespan
)
```

Delete `tests/todo_fixture.py`. In every test that imported it, replace
`from tests.todo_fixture import ...` with `from todo_app.entry import ...`, and replace the name
`TODO_ENTRYPOINT` with `APP`.

- [ ] **Step 6: Create the sample that has no Web channel**

`samples/notes/pyproject.toml` is `samples/todo/pyproject.toml` with `name = "vibepy-notes"`,
`packages = ["src/notes_app"]` and `notes = "notes_app.entry:APP"` in the entry point group.

```python
# samples/notes/src/notes_app/entry.py
"""A sample App with Tools and no Pages.

ADR-017 states that an App declaring no Pages has no Web channel and therefore no
runtime for the Hub to start, and is complete for an agent. This is that App.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import BaseModel

from vibepy.app import AppDefinition, AppEntrypoint, NoConfig
from vibepy.tool import Tool, ToolContext, ToolDefinition


class NoteInput(BaseModel):
    body: str


class Note(BaseModel):
    body: str
    length: int


@asynccontextmanager
async def notes_lifespan(_config: NoConfig) -> AsyncGenerator[None]:
    yield None


async def measure_note(_ctx: ToolContext[None], payload: NoteInput) -> Note:
    return Note(body=payload.body, length=len(payload.body))


NOTES_APP: AppDefinition[None, NoConfig] = AppDefinition(
    app_id="notes-app",
    name="Notes",
    version="0.1.0",
    config=NoConfig,
    tools=[
        Tool(
            definition=ToolDefinition(
                name="measure_note",
                description="Measure a note",
                input_model=NoteInput,
                output_model=Note,
            ),
            handler=measure_note,
        )
    ],
    pages=[],
)

APP: AppEntrypoint[None, NoConfig] = AppEntrypoint(
    definition=NOTES_APP, lifespan=notes_lifespan
)
```

`samples/notes/src/notes_app/__init__.py` holds `"""A sample App with no Web channel."""`.

Add to `tests/test_todo_distribution.py`:

```python
def test_the_notes_distribution_declares_an_app_without_pages() -> None:
    declared = {ref.app_name for ref in discover_apps()}
    assert "notes" in declared
```

- [ ] **Step 7: Sync and run the test**

Run: `uv sync && uv run pytest tests/test_todo_distribution.py -v`
Expected: PASS. `uv sync` installs workspace members editable, so the entry point is in the dev environment's metadata.

- [ ] **Step 8: Run the whole suite**

Run: `make lint typecheck test`
Expected: PASS. Every former importer of the fixture now imports `todo_app.entry`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml Makefile samples tests
git commit -m "Make the samples distributions of their own"
```

---

### Task 2: The Web channel command

**Files:**
- Create: `src/vibepy/serve.py`
- Test: `tests/test_serve_command.py`

**Interfaces:**
- Consumes: `todo_app.entry.APP` (through the entry point group, not by import), `vibepy.app.package.discover_apps`, `vibepy.app.package.APP_GROUP`, `vibepy.app.composition.page_runtime_for`, `vibepy.adapters.nicegui.register_pages`
- Produces: the command `python -m vibepy.serve <app-name> --port <n>`, reading one JSON object of configuration from standard input. `vibepy.serve.main(argv: Sequence[str], /) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_serve_command.py
"""The command that opens an App's Web channel, run as a real process."""

import json
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_for(url: str, process: subprocess.Popen[bytes], *, timeout: float = 20.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"the server exited with {process.returncode}")
        try:
            with urlopen(url) as answer:
                return answer.read().decode()
        except URLError:
            time.sleep(0.2)
    raise AssertionError(f"{url} did not answer within {timeout}s")


def test_a_declared_page_is_served(tmp_path) -> None:
    port = _free_port()
    config = json.dumps({"db_path": str(tmp_path / "todo.db")})
    process = subprocess.Popen(
        [sys.executable, "-m", "vibepy.serve", "todo", "--port", str(port)],
        stdin=subprocess.PIPE,
    )
    assert process.stdin is not None
    process.stdin.write(config.encode())
    process.stdin.close()
    try:
        body = _wait_for(f"http://127.0.0.1:{port}/todos", process)
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert "<!DOCTYPE html>" in body or "<html" in body


def test_an_unknown_app_name_fails_with_a_message() -> None:
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy.serve", "absent", "--port", "8123"],
        input=b"{}",
        capture_output=True,
    )
    assert finished.returncode == 1
    assert "absent" in finished.stderr.decode()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_serve_command.py -v`
Expected: FAIL — `No module named vibepy.serve`.

- [ ] **Step 3: Write the command**

```python
# src/vibepy/serve.py
"""Open one App's Web channel, in that App's own environment.

`vibepy.describe` reads a declaration; this runs one. Both are commands rather
than library calls for the same reason: the import belongs on the App's side of a
process boundary. See `docs/architecture/packaging.md`.

Composing a channel's running window is the framework's, which is why the command
lives here and not in the Hub. NiceGUI owns the server, and `app.on_startup` and
`app.on_shutdown` are its documented lifecycle hooks, so nothing here builds an
ASGI application or calls a server.
"""

import argparse
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from importlib.metadata import EntryPoint

from nicegui import app, ui

from vibepy.adapters.nicegui import register_pages
from vibepy.app.composition import page_runtime_for
from vibepy.app.entrypoint import AppEntrypoint
from vibepy.app.package import APP_GROUP, discover_apps
from vibepy.errors import AppEntrypointInvalidError, AppEntrypointUnloadableError, to_error_info

logger = logging.getLogger(__name__)


def _entrypoint(app_name: str, /) -> AppEntrypoint[object, object]:
    """Resolve one declared App in this environment, importing only that one."""
    for ref in discover_apps():
        if ref.app_name != app_name:
            continue
        reference = f"{ref.module}:{ref.attr}"
        entry = EntryPoint(name=ref.app_name, value=reference, group=APP_GROUP)
        try:
            loaded: object = entry.load()
        except (ImportError, AttributeError) as error:
            raise AppEntrypointUnloadableError(app_name, reference) from error
        if not isinstance(loaded, AppEntrypoint):
            raise AppEntrypointInvalidError(app_name, reference, type(loaded).__name__)
        return loaded
    raise SystemExit(f"No App named {app_name!r} is declared in this environment")


def _serve(entrypoint: AppEntrypoint[object, object], config: Mapping[str, object], port: int) -> None:
    """Hold the App's window open for as long as the server runs."""
    stack = AsyncExitStack()

    async def opened() -> None:
        pages = await stack.enter_async_context(
            page_runtime_for(entrypoint.definition, entrypoint.lifespan, config=config)
        )
        register_pages(entrypoint.definition, pages)

    async def closed() -> None:
        await stack.aclose()

    app.on_startup(opened)
    app.on_shutdown(closed)
    ui.run(host="127.0.0.1", port=port, reload=False, show=False)


def main(argv: Sequence[str], /) -> int:
    """Read configuration from standard input and serve one App."""
    parser = argparse.ArgumentParser(prog="vibepy.serve")
    parser.add_argument("app_name")
    parser.add_argument("--port", type=int, required=True)
    parsed = parser.parse_args(argv)
    raw: object = json.loads(sys.stdin.read() or "{}")
    if not isinstance(raw, dict):
        sys.stderr.write('{"code": "serve.config_invalid", "message": "expected a JSON object"}\n')
        return 1
    config: Mapping[str, object] = raw
    try:
        entrypoint = _entrypoint(parsed.app_name)
    except SystemExit as error:
        sys.stderr.write(f"{error}\n")
        return 1
    except (AppEntrypointUnloadableError, AppEntrypointInvalidError) as error:
        info = to_error_info(error)
        sys.stderr.write(json.dumps({"code": info.code, "message": info.message}) + "\n")
        return 1
    _serve(entrypoint, config, parsed.port)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

The generic parameters of `AppEntrypoint[object, object]` are read positions here: the command
never constructs a definition or calls a lifespan itself, so the widest arguments type-check
without `Any` or `cast`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_serve_command.py -v`
Expected: PASS. The first test also pins that routes registered during startup are served —
`register_pages` runs inside `on_startup`, which the ASGI lifespan completes before the first
request.

- [ ] **Step 5: Run the whole suite**

Run: `make lint typecheck test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vibepy/serve.py tests/test_serve_command.py
git commit -m "Open an App's Web channel with a command"
```

---

### Task 3: The Hub App and its package sources

**Files:**
- Create: `hub/pyproject.toml`
- Create: `hub/src/vibepy_hub/__init__.py`
- Create: `hub/src/vibepy_hub/state.py`
- Create: `hub/src/vibepy_hub/sources.py`
- Create: `hub/src/vibepy_hub/models.py`
- Create: `hub/src/vibepy_hub/tools.py`
- Create: `hub/src/vibepy_hub/entry.py`
- Modify: `pyproject.toml` (add `"hub"` back to `members`, and `vibepy-hub` to the dev group)
- Test: `hub/tests/test_sources.py`

**Interfaces:**
- Consumes: `vibepy.app.model.AppDefinition`, `vibepy.tool.{Tool, ToolContext, ToolDefinition}`
- Produces:
  - `vibepy_hub.state.HubState(sources: tuple[Path, ...], config: Mapping[str, Mapping[str, object]])`, `read_state(root: Path, /) -> HubState`, `write_state(root: Path, state: HubState, /) -> None`
  - `vibepy_hub.sources.Candidate(folder: Path, name: str | None, version: str | None, declares_app: bool)`, `candidates(source: Path, /) -> tuple[Candidate, ...]`
  - `vibepy_hub.models.Diagnostic(code: str, message: str, details: Mapping[str, str])`, `SourcePath(path: Path)`, `CandidateRow(...)`, `SourceListing(sources: list[Path], candidates: list[CandidateRow])`
  - `vibepy_hub.entry.HubConfig(root: Path)`, `HubDeps(root: Path)`, `hub_lifespan`, `HUB_APP`, `APP`
  - Tools `register_package_source`, `remove_package_source`

- [ ] **Step 1: Write the failing test**

```python
# hub/tests/test_sources.py
"""What a registered folder offers, read without building anything."""

from pathlib import Path

from vibepy_hub.sources import candidates


def _project(folder: Path, *, name: str, declares: bool) -> None:
    folder.mkdir(parents=True)
    declaration = '\n[project.entry-points."vibepy.apps"]\ndemo = "demo.entry:APP"\n'
    (folder / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "1.2.3"\n' + (declaration if declares else ""),
        encoding="utf-8",
    )


def test_a_declaring_folder_is_an_installable_candidate(tmp_path: Path) -> None:
    _project(tmp_path / "demo", name="demo-app", declares=True)
    found = candidates(tmp_path)
    assert [(row.name, row.version, row.declares_app) for row in found] == [
        ("demo-app", "1.2.3", True)
    ]


def test_a_folder_without_a_declaration_is_still_offered(tmp_path: Path) -> None:
    _project(tmp_path / "plain", name="plain", declares=False)
    assert [row.declares_app for row in candidates(tmp_path)] == [False]


def test_a_folder_without_a_project_file_is_not_a_candidate(tmp_path: Path) -> None:
    (tmp_path / "notes").mkdir()
    assert candidates(tmp_path) == ()


def test_candidates_are_ordered_by_folder_name(tmp_path: Path) -> None:
    _project(tmp_path / "zulu", name="zulu", declares=True)
    _project(tmp_path / "alpha", name="alpha", declares=True)
    assert [row.folder.name for row in candidates(tmp_path)] == ["alpha", "zulu"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest hub/tests/test_sources.py -v`
Expected: FAIL — `No module named vibepy_hub`.

- [ ] **Step 3: Create the distribution**

```toml
# hub/pyproject.toml
[project]
name = "vibepy-hub"
version = "0.1.0"
description = "Headless control plane for installed Vibepy Apps"
requires-python = ">=3.12"
dependencies = ["vibepy-framework", "pydantic>=2.9"]

[project.entry-points."vibepy.apps"]
hub = "vibepy_hub.entry:APP"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/vibepy_hub"]

[tool.uv.sources]
vibepy-framework = { workspace = true }
```

Add `"hub"` back to the root `members`, add `testpaths = ["tests", "hub/tests"]` to
`[tool.pytest.ini_options]`, and add `vibepy-hub` and `vibepy-todo` to the root
`[dependency-groups] dev` list with `tool.uv.sources` entries marking both `workspace = true`,
so `uv sync` installs them editable.

- [ ] **Step 4: Write the source reader**

```python
# hub/src/vibepy_hub/sources.py
"""What a registered folder offers, read from project files and nothing else.

Entry points are not core metadata and a build backend may add them, so a static
reading is a hint rather than a verdict: a folder with no visible declaration is
still offered, and installing it is what decides. See
`docs/milestones/M10/spec.md`.
"""

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

APP_GROUP = "vibepy.apps"


@dataclass(frozen=True)
class Candidate:
    """One installable folder inside a registered source."""

    folder: Path
    name: str | None
    version: str | None
    declares_app: bool


def candidates(source: Path, /) -> tuple[Candidate, ...]:
    """Every immediate subfolder of a source that carries a project file."""
    found: list[Candidate] = []
    for folder in sorted(path for path in source.iterdir() if path.is_dir()):
        project = folder / "pyproject.toml"
        if not project.is_file():
            continue
        try:
            document = tomllib.loads(project.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            logger.info("unreadable project file at %s", project)
            found.append(Candidate(folder=folder, name=None, version=None, declares_app=False))
            continue
        table = document.get("project")
        described = table if isinstance(table, dict) else {}
        name = described.get("name")
        version = described.get("version")
        groups = described.get("entry-points")
        declared = isinstance(groups, dict) and APP_GROUP in groups
        found.append(
            Candidate(
                folder=folder,
                name=name if isinstance(name, str) else None,
                version=version if isinstance(version, str) else None,
                declares_app=declared,
            )
        )
    return tuple(found)
```

- [ ] **Step 5: Run the source tests**

Run: `uv sync && uv run pytest hub/tests/test_sources.py -v`
Expected: PASS.

- [ ] **Step 6: Write the state file, the shared models, and the App**

```python
# hub/src/vibepy_hub/state.py
"""The two things the framework does not answer: registered folders and values.

What is installed is not kept here. Each App has an environment of its own and
`discover_apps(path=…)` reads an environment without importing it, so the file
system is the truth about installations.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILE = "state.json"


@dataclass(frozen=True)
class HubState:
    """Everything the Hub remembers between windows."""

    sources: tuple[Path, ...] = ()
    config: Mapping[str, Mapping[str, object]] = field(default_factory=dict)


def read_state(root: Path, /) -> HubState:
    """The stored state, or an empty one when nothing has been stored."""
    path = root / STATE_FILE
    if not path.is_file():
        return HubState()
    document: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        logger.warning("ignoring a state file that is not an object: %s", path)
        return HubState()
    sources = document.get("sources")
    values = document.get("config")
    return HubState(
        sources=tuple(Path(entry) for entry in sources if isinstance(entry, str))
        if isinstance(sources, list)
        else (),
        config={
            name: held
            for name, held in (values.items() if isinstance(values, dict) else ())
            if isinstance(held, dict)
        },
    )


def write_state(root: Path, state: HubState, /) -> None:
    """Replace the stored state."""
    root.mkdir(parents=True, exist_ok=True)
    (root / STATE_FILE).write_text(
        json.dumps(
            {
                "sources": [str(path) for path in state.sources],
                "config": dict(state.config),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
```

```python
# hub/src/vibepy_hub/models.py
"""What the Hub's Tools take and return.

A diagnostic is plain fields because an output model is revalidated, so no
exception instance and no live object can travel in one. See
`docs/decisions/ADR-007-framework-guarantees-tool-output.md`.
"""

from pathlib import Path

from pydantic import BaseModel


class Diagnostic(BaseModel):
    """An expected, actionable failure, in the form a channel can render."""

    code: str
    message: str
    details: dict[str, str] = {}


class Empty(BaseModel):
    """The input of a Tool that takes nothing."""


class SourcePath(BaseModel):
    path: Path


class CandidateRow(BaseModel):
    folder: Path
    name: str | None
    version: str | None
    declares_app: bool


class SourceListing(BaseModel):
    sources: list[Path]
    candidates: list[CandidateRow]
    diagnostic: Diagnostic | None = None
```

```python
# hub/src/vibepy_hub/entry.py
"""The Hub App: one declaration, one lifespan, one composition root.

The Hub is a platform-tier App. It is built with the framework and depends on it,
and the framework never depends on the Hub.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from vibepy.app import AppDefinition, AppEntrypoint

from vibepy_hub.tools import HUB_TOOLS

logger = logging.getLogger(__name__)


class HubConfig(BaseModel):
    """What the Hub requires of its host.

    The root is declared rather than assumed so that a test supplies a temporary
    directory and two Hubs never share one.
    """

    root: Path


@dataclass
class HubDeps:
    """The Hub's domain internals, reached only through ToolContext."""

    root: Path


@asynccontextmanager
async def hub_lifespan(config: HubConfig) -> AsyncGenerator[HubDeps]:
    """The Hub's resource for the life of one window."""
    config.root.mkdir(parents=True, exist_ok=True)
    yield HubDeps(root=config.root)


HUB_APP: AppDefinition[HubDeps, HubConfig] = AppDefinition(
    app_id="vibepy-hub",
    name="Hub",
    version="0.1.0",
    config=HubConfig,
    tools=HUB_TOOLS,
    pages=[],
)

APP: AppEntrypoint[HubDeps, HubConfig] = AppEntrypoint(
    definition=HUB_APP, lifespan=hub_lifespan
)
```

```python
# hub/src/vibepy_hub/tools.py
"""The Hub's public operations.

Eight Tools, each one affordance of the control plane. The work they call —
reading a folder, running uv, holding a child process, reading and writing the
state file — is domain internals and is not published as a Tool.
"""

import logging
from collections.abc import Sequence

from vibepy.tool import Tool, ToolContext, ToolDefinition

from vibepy_hub.entry_types import HubDeps
from vibepy_hub.models import CandidateRow, Diagnostic, SourceListing, SourcePath
from vibepy_hub.sources import candidates
from vibepy_hub.state import HubState, read_state, write_state

logger = logging.getLogger(__name__)


def _listing(deps: HubDeps) -> SourceListing:
    state = read_state(deps.root)
    rows: list[CandidateRow] = []
    for source in state.sources:
        rows.extend(
            CandidateRow(
                folder=row.folder,
                name=row.name,
                version=row.version,
                declares_app=row.declares_app,
            )
            for row in candidates(source)
        )
    return SourceListing(sources=list(state.sources), candidates=rows)


async def register_package_source(ctx: ToolContext[HubDeps], payload: SourcePath) -> SourceListing:
    folder = payload.path
    if not folder.is_dir():
        return SourceListing(
            sources=list(read_state(ctx.dependencies.root).sources),
            candidates=[],
            diagnostic=Diagnostic(
                code="hub.source_unreadable",
                message=f"{folder} is not a folder",
                details={"path": str(folder)},
            ),
        )
    state = read_state(ctx.dependencies.root)
    if folder not in state.sources:
        write_state(
            ctx.dependencies.root,
            HubState(sources=(*state.sources, folder), config=state.config),
        )
    return _listing(ctx.dependencies)


async def remove_package_source(ctx: ToolContext[HubDeps], payload: SourcePath) -> SourceListing:
    state = read_state(ctx.dependencies.root)
    write_state(
        ctx.dependencies.root,
        HubState(
            sources=tuple(path for path in state.sources if path != payload.path),
            config=state.config,
        ),
    )
    return _listing(ctx.dependencies)


HUB_TOOLS: Sequence[Tool[HubDeps]] = [
    Tool(
        definition=ToolDefinition(
            name="register_package_source",
            description="Offer the Apps in a local folder for installation",
            input_model=SourcePath,
            output_model=SourceListing,
        ),
        handler=register_package_source,
    ),
    Tool(
        definition=ToolDefinition(
            name="remove_package_source",
            description="Stop offering the Apps in a local folder",
            input_model=SourcePath,
            output_model=SourceListing,
        ),
        handler=remove_package_source,
    ),
]
```

`HubDeps` is imported from `vibepy_hub.entry_types` rather than from `entry`, because `entry`
imports `HUB_TOOLS`. Create `hub/src/vibepy_hub/entry_types.py` holding the `HubDeps` dataclass
and have `entry.py` import it from there instead of defining it.

`hub/src/vibepy_hub/__init__.py` holds `"""Headless control plane for installed Vibepy Apps."""`
and no imports, so importing the Hub's modules never imports its Tools by side effect.

- [ ] **Step 7: Write the Tool test**

```python
# hub/tests/test_package_sources.py
"""Registering a folder is what makes its Apps installable."""

from pathlib import Path

from vibepy.app.composition import tool_runtime_for

from vibepy_hub.entry import APP, HUB_APP


async def test_registering_a_folder_lists_its_candidates(tmp_path: Path) -> None:
    source = tmp_path / "packages"
    project = source / "demo"
    project.mkdir(parents=True)
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        '\n[project.entry-points."vibepy.apps"]\ndemo = "demo.entry:APP"\n',
        encoding="utf-8",
    )
    config = {"root": str(tmp_path / "hub")}
    async with tool_runtime_for(HUB_APP, APP.lifespan, config=config) as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})
        assert [row.name for row in listed.candidates] == ["demo"]
        remaining = await tools.invoke("remove_package_source", {"path": str(source)})
        assert remaining.sources == []


async def test_an_absent_folder_is_a_diagnostic(tmp_path: Path) -> None:
    config = {"root": str(tmp_path / "hub")}
    async with tool_runtime_for(HUB_APP, APP.lifespan, config=config) as tools:
        answered = await tools.invoke("register_package_source", {"path": str(tmp_path / "no")})
        assert answered.diagnostic is not None
        assert answered.diagnostic.code == "hub.source_unreadable"
```

- [ ] **Step 8: Run the tests**

Run: `uv sync && uv run pytest hub/tests -v`
Expected: PASS.

- [ ] **Step 9: Run the whole suite**

Run: `make lint typecheck test`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add hub pyproject.toml
git commit -m "Register a folder of Apps with the Hub"
```

---

### Task 4: Installing and removing an App

**Files:**
- Create: `hub/src/vibepy_hub/installer.py`
- Modify: `hub/src/vibepy_hub/models.py`, `hub/src/vibepy_hub/tools.py`
- Test: `hub/tests/test_installation.py`

**Interfaces:**
- Consumes: `vibepy_hub.sources.candidates`, `vibepy_hub.state.read_state`, `vibepy.app.package.discover_apps`
- Produces:
  - `vibepy_hub.installer.environment(root: Path, app_name: str, /) -> Path`, `interpreter(env: Path, /) -> Path`, `async install(*, folder: Path, env: Path) -> None`, `async describe(env: Path, /) -> list[AppFacts]`, and the exception `InstallFailed(step: str, output: str)`
  - `vibepy_hub.models.AppFacts(app_id, name, version, config_schema: dict[str, object], has_pages: bool)`, `AppRow(...)`, `AppListing(apps: list[AppRow])`, `Installation(app: AppRow, diagnostic: Diagnostic | None)`, `AppName(app_name: str)`
  - Tools `install_app`, `remove_app`, `list_apps`

- [ ] **Step 1: Write the failing test**

```python
# hub/tests/test_installation.py
"""Installing an App gives it an environment of its own."""

from pathlib import Path

from vibepy.app.composition import tool_runtime_for

from vibepy_hub.entry import APP, HUB_APP
from vibepy_hub.installer import environment, interpreter

REPO = Path(__file__).resolve().parents[2]


async def _hub(root: Path):
    return tool_runtime_for(HUB_APP, APP.lifespan, config={"root": str(root)})


async def test_installing_the_todo_app_creates_its_own_environment(tmp_path: Path) -> None:
    root = tmp_path / "hub"
    async with await _hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(REPO / "samples")})
        installed = await tools.invoke("install_app", {"app_name": "todo"})
        assert installed.diagnostic is None
        assert installed.app.version == "0.1.0"
        assert installed.app.has_pages is True
    env = environment(root, "todo")
    assert interpreter(env).is_file()


async def test_an_installed_app_is_listed_from_its_environment(tmp_path: Path) -> None:
    root = tmp_path / "hub"
    async with await _hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(REPO / "samples")})
        await tools.invoke("install_app", {"app_name": "todo"})
        listed = await tools.invoke("list_apps", {})
        rows = {row.app_name: row for row in listed.apps}
        assert rows["todo"].state == "installed"


async def test_removing_an_app_deletes_its_environment(tmp_path: Path) -> None:
    root = tmp_path / "hub"
    data = tmp_path / "todo.db"
    data.write_text("a todo", encoding="utf-8")
    async with await _hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(REPO / "samples")})
        await tools.invoke("install_app", {"app_name": "todo"})
        await tools.invoke("remove_app", {"app_name": "todo"})
        listed = await tools.invoke("list_apps", {})
        assert [row.state for row in listed.apps if row.app_name == "todo"] == ["available"]
    assert not environment(root, "todo").exists()
    assert data.is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest hub/tests/test_installation.py -v`
Expected: FAIL — `No module named vibepy_hub.installer`.

- [ ] **Step 3: Write the installer**

```python
# hub/src/vibepy_hub/installer.py
"""Creating an App's environment, and asking that environment what it holds.

`uv tool install` satisfies the isolation contract `docs/architecture/packaging.md`
states, and `uv venv` with `uv pip install` satisfies it for a local folder while
leaving the environment's path to the Hub. Describing runs in that environment's
interpreter, because reading a declaration imports it.
"""

import json
import logging
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from vibepy_hub.models import AppFacts

logger = logging.getLogger(__name__)


class InstallFailed(Exception):
    """A step of installation failed. Carries which step and what it wrote."""

    def __init__(self, step: str, output: str) -> None:
        super().__init__(f"{step} failed: {output}")
        self.step = step
        self.output = output


def environment(root: Path, app_name: str, /) -> Path:
    """Where this Hub keeps one App's environment."""
    return root / "envs" / app_name


def interpreter(env: Path, /) -> Path:
    """The Python of an environment, on either platform."""
    return env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


async def _run(command: Sequence[str], /) -> str:
    import asyncio

    if shutil.which(command[0]) is None:
        raise InstallFailed(command[0], f"{command[0]} is not on PATH")
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    output, _ = await process.communicate()
    written = output.decode(errors="replace")
    if process.returncode != 0:
        raise InstallFailed(" ".join(command[:2]), written.strip())
    return written


async def install(*, folder: Path, env: Path) -> None:
    """Create an environment of its own for one App and install it there."""
    await _run(["uv", "venv", str(env)])
    await _run(["uv", "pip", "install", "--python", str(interpreter(env)), str(folder)])


async def describe(env: Path, /) -> list[AppFacts]:
    """What the Apps in one environment declare, read in that environment."""
    written = await _run([str(interpreter(env)), "-m", "vibepy.describe"])
    described: object = json.loads(written)
    if not isinstance(described, list):
        raise InstallFailed("vibepy.describe", "expected a JSON array")
    facts: list[AppFacts] = []
    for entry in described:
        if not isinstance(entry, dict):
            continue
        facts.append(
            AppFacts(
                app_id=str(entry.get("app_id", "")),
                name=str(entry.get("name", "")),
                version=str(entry.get("version", "")),
                config_schema=entry.get("config_schema") or {},
                has_pages=bool(entry.get("pages")),
            )
        )
    return facts
```

- [ ] **Step 4: Add the models**

Append to `hub/src/vibepy_hub/models.py`:

```python
class AppFacts(BaseModel):
    """What an App declares, read after installation."""

    app_id: str
    name: str
    version: str
    config_schema: dict[str, object] = {}
    has_pages: bool


class AppName(BaseModel):
    app_name: str


class AppRow(BaseModel):
    """One App as the control plane sees it."""

    app_name: str
    name: str | None = None
    version: str | None = None
    state: str
    url: str | None = None
    configured: bool = False
    has_pages: bool = False
    diagnostic: Diagnostic | None = None


class AppListing(BaseModel):
    apps: list[AppRow]


class Installation(BaseModel):
    app: AppRow
    diagnostic: Diagnostic | None = None
```

`state` is one of `"available"`, `"installed"` and `"running"`. It is a string rather than an
enum because an output model must round-trip through JSON, and the set is the Hub's to publish.

- [ ] **Step 5: Add the Tools**

Add to `hub/src/vibepy_hub/tools.py` — `install_app` installs and then describes, `remove_app`
deletes the environment, and `list_apps` reads candidates and environments:

```python
async def install_app(ctx: ToolContext[HubDeps], payload: AppName) -> Installation:
    deps = ctx.dependencies
    folder = _candidate_folder(deps, payload.app_name)
    if folder is None:
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.candidate_absent",
                message=f"No registered source offers {payload.app_name!r}",
                details={"app_name": payload.app_name},
            ),
        )
    env = environment(deps.root, payload.app_name)
    try:
        await install(folder=folder, env=env)
        facts = await describe(env)
    except InstallFailed as failure:
        shutil.rmtree(env, ignore_errors=True)
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.install_failed",
                message=str(failure),
                details={"step": failure.step, "output": failure.output},
            ),
        )
    described = facts[0] if facts else None
    return Installation(
        app=AppRow(
            app_name=payload.app_name,
            name=described.name if described else None,
            version=described.version if described else None,
            state="installed",
            has_pages=bool(described and described.has_pages),
        )
    )
```

```python
def _candidate_folder(deps: HubDeps, app_name: str, /) -> Path | None:
    """The registered folder that offers this App, by project or folder name."""
    for source in read_state(deps.root).sources:
        for row in candidates(source):
            if app_name in {row.name, row.folder.name}:
                return row.folder
    return None


def _site_packages(env: Path, /) -> Path:
    """Where an environment keeps its metadata, on either platform."""
    if sys.platform == "win32":
        return env / "Lib" / "site-packages"
    return env / "lib" / f"python3.{sys.version_info.minor}" / "site-packages"


def _installed(deps: HubDeps) -> dict[str, AppRow]:
    """One row per environment this Hub created, read without importing."""
    envs = deps.root / "envs"
    rows: dict[str, AppRow] = {}
    if not envs.is_dir():
        return rows
    held = read_state(deps.root).config
    for env in sorted(path for path in envs.iterdir() if path.is_dir()):
        declared = discover_apps(path=[_site_packages(env)])
        found = next((ref for ref in declared if ref.app_name == env.name), None)
        port = deps.processes.running(env.name)
        rows[env.name] = AppRow(
            app_name=env.name,
            name=found.app_name if found else None,
            version=found.distribution_version if found else None,
            state="running" if port else "installed",
            url=f"http://127.0.0.1:{port}" if port else None,
            configured=env.name in held,
            has_pages=_declares_pages(env, env.name),
        )
    return rows


async def remove_app(ctx: ToolContext[HubDeps], payload: AppName) -> AppListing:
    deps = ctx.dependencies
    await deps.processes.stop(payload.app_name)
    shutil.rmtree(environment(deps.root, payload.app_name), ignore_errors=True)
    state = read_state(deps.root)
    write_state(
        deps.root,
        HubState(
            sources=state.sources,
            config={name: held for name, held in state.config.items() if name != payload.app_name},
        ),
    )
    return await list_apps(ctx, Empty())


async def list_apps(ctx: ToolContext[HubDeps], _payload: Empty) -> AppListing:
    deps = ctx.dependencies
    rows = _installed(deps)
    for source in read_state(deps.root).sources:
        for row in candidates(source):
            app_name = row.name or row.folder.name
            if app_name in rows:
                continue
            rows[app_name] = AppRow(
                app_name=app_name,
                name=row.name,
                version=row.version,
                state="available",
            )
    return AppListing(apps=[rows[name] for name in sorted(rows)])
```

`_declares_pages(env, app_name)` caches what `install_app` learned: write the `AppFacts` of an
installation to `<env>/.vibepy-facts.json` at the end of `install_app`, and read `has_pages` from
there. That file belongs to the Hub, sits inside the environment it describes, and disappears
with it — so removing an App leaves no record behind. Reading it is not a second truth about
what is installed: `discover_apps` still answers that, and this answers only what the App
declared when it was installed.

`Processes` arrives in Task 6; until then `_installed` reports `state="installed"` and
`deps.processes` does not exist. Write `_installed` without the port lookup in this task and add
those two lines in Task 6, Step 5.

`tools.py` gains these imports: `shutil`, `sys`, `pathlib.Path`,
`vibepy.app.package.discover_apps`, and from `vibepy_hub.installer` the names `InstallFailed`,
`describe`, `environment`, `install`.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest hub/tests/test_installation.py -v`
Expected: PASS. These call real `uv`, so allow up to a minute on a cold cache.

- [ ] **Step 7: Add the diagnostic test for a missing uv**

```python
async def test_a_missing_uv_is_a_diagnostic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    root = tmp_path / "hub"
    async with await _hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(REPO / "samples")})
        answered = await tools.invoke("install_app", {"app_name": "todo"})
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.install_failed"
    assert "uv" in answered.diagnostic.message
```

Run: `uv run pytest hub/tests/test_installation.py -v`
Expected: PASS.

- [ ] **Step 8: Run the whole suite and commit**

Run: `make lint typecheck test`

```bash
git add hub
git commit -m "Install an App into an environment of its own"
```

---

### Task 5: Holding an App's configuration

**Files:**
- Modify: `hub/src/vibepy_hub/models.py`, `hub/src/vibepy_hub/tools.py`
- Test: `hub/tests/test_configuration.py`

**Interfaces:**
- Consumes: `vibepy_hub.state.{read_state, write_state, HubState}`, `AppFacts.config_schema`
- Produces: `vibepy_hub.models.ConfigureRequest(app_name: str, values: dict[str, object])`, `HeldConfig(app_name: str, values: dict[str, object], required_secrets: list[str], diagnostic: Diagnostic | None)`, Tool `configure_app`, and `vibepy_hub.tools.secret_fields(schema: Mapping[str, object], /) -> tuple[str, ...]`

- [ ] **Step 1: Write the failing test**

```python
# hub/tests/test_configuration.py
"""The Hub holds an App's values, and never a secret."""

from pathlib import Path

from vibepy.app.composition import tool_runtime_for

from vibepy_hub.entry import APP, HUB_APP
from vibepy_hub.tools import secret_fields

SCHEMA = {
    "properties": {
        "api_base_url": {"type": "string"},
        "api_token": {"type": "string", "format": "password", "writeOnly": True},
    },
    "required": ["api_base_url", "api_token"],
}


def test_a_secret_field_is_recognised_from_the_schema() -> None:
    assert secret_fields(SCHEMA) == ("api_token",)


async def test_a_secret_value_is_not_stored(tmp_path: Path) -> None:
    root = tmp_path / "hub"
    async with tool_runtime_for(HUB_APP, APP.lifespan, config={"root": str(root)}) as tools:
        held = await tools.invoke(
            "configure_app",
            {"app_name": "todo", "values": {"db_path": "/tmp/todo.db"}},
        )
    assert held.values == {"db_path": "/tmp/todo.db"}
    assert "api_token" not in (root / "state.json").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest hub/tests/test_configuration.py -v`
Expected: FAIL — `cannot import name 'secret_fields'`.

- [ ] **Step 3: Write the secret reader and the Tool**

```python
def secret_fields(schema: Mapping[str, object], /) -> tuple[str, ...]:
    """The fields an App declared as secret, read from its projected schema.

    Pydantic projects `SecretStr` as `format: password` with `writeOnly: true`, so
    a Host tells a secret from an ordinary string without importing the App.
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return ()
    return tuple(
        name
        for name, described in properties.items()
        if isinstance(described, dict) and described.get("format") == "password"
    )
```

```python
async def configure_app(ctx: ToolContext[HubDeps], payload: ConfigureRequest) -> HeldConfig:
    deps = ctx.dependencies
    facts = _facts(deps, payload.app_name)
    if facts is None:
        return HeldConfig(
            app_name=payload.app_name,
            values={},
            required_secrets=[],
            diagnostic=Diagnostic(
                code="hub.not_installed",
                message=f"{payload.app_name!r} is not installed",
                details={"app_name": payload.app_name},
            ),
        )
    secrets = secret_fields(facts.config_schema)
    kept = {name: value for name, value in payload.values.items() if name not in secrets}
    state = read_state(deps.root)
    write_state(
        deps.root,
        HubState(sources=state.sources, config={**state.config, payload.app_name: kept}),
    )
    return HeldConfig(
        app_name=payload.app_name, values=kept, required_secrets=list(secrets)
    )
```

`_facts(deps, app_name)` reads the `AppFacts` written beside the App's environment in Task 4 and
returns `None` when no environment holds that App.

Add to `models.py`:

```python
class ConfigureRequest(BaseModel):
    app_name: str
    values: dict[str, object] = {}


class HeldConfig(BaseModel):
    app_name: str
    values: dict[str, object]
    required_secrets: list[str]
    diagnostic: Diagnostic | None = None
```

The test in Step 1 configures an App that is not installed, so make the Todo App installed
first with the same three calls Task 4's tests use, or assert the `hub.not_installed`
diagnostic instead — the second test as written expects stored values, so it installs first.

The Hub does not validate the values. The window validates them and raises `config.invalid`,
which is `docs/decisions/ADR-022-configuration-is-a-declaration.md`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest hub/tests/test_configuration.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole suite and commit**

Run: `make lint typecheck test`

```bash
git add hub
git commit -m "Hold an App's configuration without holding its secrets"
```

---

### Task 6: Starting and stopping an App

**Files:**
- Create: `hub/src/vibepy_hub/processes.py`
- Modify: `hub/src/vibepy_hub/entry_types.py`, `hub/src/vibepy_hub/entry.py`, `hub/src/vibepy_hub/models.py`, `hub/src/vibepy_hub/tools.py`
- Test: `hub/tests/test_runtime.py`

**Interfaces:**
- Consumes: `vibepy_hub.installer.interpreter`, `vibepy_hub.state.read_state`, `secret_fields`
- Produces:
  - `vibepy_hub.processes.Processes` with `async start(self, *, app_name: str, interpreter: Path, config: Mapping[str, object]) -> int`, `async stop(self, app_name: str, /) -> bool`, `running(self, app_name: str, /) -> int | None`, `async aclose(self) -> None`, and `free_port() -> int`
  - `HubDeps` gains `processes: Processes`
  - `vibepy_hub.models.StartRequest(app_name: str, secrets: dict[str, object])`, `RunningApp(app_name: str, url: str | None, state: str, diagnostic: Diagnostic | None)`
  - Tools `start_app`, `stop_app`

- [ ] **Step 1: Write the failing test**

```python
# hub/tests/test_runtime.py
"""An installed App starts, answers, and stops."""

from pathlib import Path
from urllib.request import urlopen

from vibepy.app.composition import tool_runtime_for

from vibepy_hub.entry import APP, HUB_APP

REPO = Path(__file__).resolve().parents[2]


async def test_an_installed_app_starts_and_stops(tmp_path: Path) -> None:
    root = tmp_path / "hub"
    async with tool_runtime_for(HUB_APP, APP.lifespan, config={"root": str(root)}) as tools:
        await tools.invoke("register_package_source", {"path": str(REPO / "samples")})
        await tools.invoke("install_app", {"app_name": "todo"})
        await tools.invoke(
            "configure_app",
            {"app_name": "todo", "values": {"db_path": str(tmp_path / "todo.db")}},
        )
        started = await tools.invoke("start_app", {"app_name": "todo", "secrets": {}})
        assert started.diagnostic is None
        assert started.url is not None
        listed = await tools.invoke("list_apps", {})
        assert [row.state for row in listed.apps if row.app_name == "todo"] == ["running"]
        with urlopen(f"{started.url}/todos") as answer:
            assert answer.status == 200
        stopped = await tools.invoke("stop_app", {"app_name": "todo"})
        assert stopped.state == "installed"


async def test_stopping_an_app_that_is_not_running_is_a_diagnostic(tmp_path: Path) -> None:
    root = tmp_path / "hub"
    async with tool_runtime_for(HUB_APP, APP.lifespan, config={"root": str(root)}) as tools:
        answered = await tools.invoke("stop_app", {"app_name": "todo"})
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_running"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest hub/tests/test_runtime.py -v`
Expected: FAIL — `No module named vibepy_hub.processes`.

- [ ] **Step 3: Write the process holder**

```python
# hub/src/vibepy_hub/processes.py
"""The child processes this window started.

Only a parent observes its own children: `subprocess` documents `poll`, `wait`,
`terminate` and `kill`, and documents no way to observe an arbitrary pid. So a
child is this window's resource, released when the window closes, and status
answers for what this window started — which is the same reading
`docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md` gives the Agent
channel's processes.
"""

import asyncio
import json
import logging
import socket
from collections.abc import Mapping
from pathlib import Path

logger = logging.getLogger(__name__)

STOP_TIMEOUT = 10.0


def free_port() -> int:
    """A port nothing is listening on, chosen by the operating system."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Processes:
    """One window's running Apps."""

    def __init__(self) -> None:
        self._running: dict[str, tuple[asyncio.subprocess.Process, int]] = {}

    def running(self, app_name: str, /) -> int | None:
        found = self._running.get(app_name)
        if found is None:
            return None
        process, port = found
        if process.returncode is not None:
            del self._running[app_name]
            return None
        return port

    async def start(
        self, *, app_name: str, interpreter: Path, config: Mapping[str, object]
    ) -> int:
        """Serve one App on a free port, handing it its configuration on stdin."""
        port = free_port()
        process = await asyncio.create_subprocess_exec(
            str(interpreter),
            "-m",
            "vibepy.serve",
            app_name,
            "--port",
            str(port),
            stdin=asyncio.subprocess.PIPE,
        )
        assert process.stdin is not None
        process.stdin.write(json.dumps(dict(config)).encode())
        await process.stdin.drain()
        process.stdin.close()
        self._running[app_name] = (process, port)
        return port

    async def stop(self, app_name: str, /) -> bool:
        """Terminate one App, then kill it if it does not leave."""
        found = self._running.pop(app_name, None)
        if found is None:
            return False
        process, _ = found
        if process.returncode is not None:
            return True
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=STOP_TIMEOUT)
        except TimeoutError:
            logger.warning("%s did not stop; killing it", app_name)
            process.kill()
            await process.wait()
        return True

    async def aclose(self) -> None:
        """Release every child this window started."""
        for app_name in list(self._running):
            await self.stop(app_name)
```

- [ ] **Step 4: Give the lifespan the holder**

`HubDeps` gains `processes: Processes`, and `hub_lifespan` becomes:

```python
@asynccontextmanager
async def hub_lifespan(config: HubConfig) -> AsyncGenerator[HubDeps]:
    config.root.mkdir(parents=True, exist_ok=True)
    processes = Processes()
    try:
        yield HubDeps(root=config.root, processes=processes)
    finally:
        await processes.aclose()
```

Acquisition is bound to release, so a window that closes leaves no child behind. This is
`docs/decisions/ADR-018-app-scoped-resource-is-an-async-context-manager.md`.

- [ ] **Step 5: Add the Tools**

```python
def _refusal(app_name: str, code: str, message: str) -> RunningApp:
    return RunningApp(
        app_name=app_name,
        url=None,
        state="installed",
        diagnostic=Diagnostic(code=code, message=message, details={"app_name": app_name}),
    )


async def start_app(ctx: ToolContext[HubDeps], payload: StartRequest) -> RunningApp:
    deps = ctx.dependencies
    facts = _facts(deps, payload.app_name)
    if facts is None:
        return _refusal(payload.app_name, "hub.not_installed", f"{payload.app_name!r} is not installed")
    if not facts.has_pages:
        return _refusal(
            payload.app_name,
            "hub.no_web_channel",
            f"{payload.app_name!r} declares no Pages, so it has no Web channel to start",
        )
    if deps.processes.running(payload.app_name) is not None:
        return _refusal(
            payload.app_name, "hub.already_running", f"{payload.app_name!r} is already running"
        )
    config = {**read_state(deps.root).config.get(payload.app_name, {}), **payload.secrets}
    port = await deps.processes.start(
        app_name=payload.app_name,
        interpreter=interpreter(environment(deps.root, payload.app_name)),
        config=config,
    )
    return RunningApp(
        app_name=payload.app_name, url=f"http://127.0.0.1:{port}", state="running"
    )


async def stop_app(ctx: ToolContext[HubDeps], payload: AppName) -> RunningApp:
    stopped = await ctx.dependencies.processes.stop(payload.app_name)
    if not stopped:
        return _refusal(
            payload.app_name, "hub.not_running", f"{payload.app_name!r} is not running here"
        )
    return RunningApp(app_name=payload.app_name, url=None, state="installed")
```

Add to `models.py`:

```python
class StartRequest(BaseModel):
    app_name: str
    secrets: dict[str, object] = {}


class RunningApp(BaseModel):
    app_name: str
    url: str | None
    state: str
    diagnostic: Diagnostic | None = None
```

`_installed` in `tools.py` gains the two lines Task 4 left out, so `list_apps` reports
`"running"` with the url for any App `Processes.running` answers for.

`start_app` waits for nothing: the child either serves or exits, and a caller that needs to know
reads the url. A start that fails to bind leaves a child that exits, and the next `list_apps`
reports the App as `"installed"` because `Processes.running` drops a child whose `returncode` is
set.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest hub/tests/test_runtime.py -v`
Expected: PASS.

- [ ] **Step 7: Add the no-Web-channel test**

```python
async def test_starting_an_app_that_is_not_installed_is_a_diagnostic(tmp_path: Path) -> None:
    root = tmp_path / "hub"
    async with tool_runtime_for(HUB_APP, APP.lifespan, config={"root": str(root)}) as tools:
        answered = await tools.invoke("start_app", {"app_name": "todo", "secrets": {}})
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_installed"


async def test_an_app_without_pages_reports_that_there_is_nothing_to_start(
    tmp_path: Path,
) -> None:
    root = tmp_path / "hub"
    async with tool_runtime_for(HUB_APP, APP.lifespan, config={"root": str(root)}) as tools:
        await tools.invoke("register_package_source", {"path": str(REPO / "samples")})
        installed = await tools.invoke("install_app", {"app_name": "notes"})
        assert installed.app.has_pages is False
        answered = await tools.invoke("start_app", {"app_name": "notes", "secrets": {}})
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.no_web_channel"
```

Run: `uv run pytest hub/tests/test_runtime.py -v`
Expected: PASS. The Notes sample from Task 1 is what makes this branch testable.

Every task that adds a handler also appends its `Tool(...)` declaration to `HUB_TOOLS`, in the
order the spec's table lists them: `register_package_source`, `remove_package_source`,
`list_apps`, `install_app`, `configure_app`, `start_app`, `stop_app`, `remove_app`. After this
task `HUB_TOOLS` holds all eight.

- [ ] **Step 8: Run the whole suite and commit**

Run: `make lint typecheck test`

```bash
git add hub
git commit -m "Start and stop an installed App's Web channel"
```

---

### Task 7: The decision and the documents

**Files:**
- Create: `docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md`
- Modify: `docs/architecture.md`, `docs/architecture/packaging.md`, `docs/architecture/lifecycle.md`
- Delete: `docs/milestones/M10/` (at integration, per `AGENTS.md`)

**Interfaces:**
- Consumes: everything the previous tasks built
- Produces: no code

- [ ] **Step 1: Write the ADR**

Follow the register of ADR-001 to ADR-007: one invariant, Context only where a reader needs it,
15 to 25 lines. Content: the Hub is an App built on the framework, it depends on the framework
and the framework never depends on it, and it therefore ships as its own distribution so that an
App's environment holds the framework and the App and never the control plane. Consequences: the
Hub's Tools are its API and its work is domain internals; Authoring takes the same position at
M12; an installed App's dependency tree never grows a control plane's.

Do not restate the layout, the choice of `uv`, the port policy or the secret boundary — those are
below the line `AGENTS.md` draws and belong to the commit messages of Tasks 1 to 6.

- [ ] **Step 2: Align the documents that own the changed facts**

- `docs/architecture.md`: the framework's ownership list gains the command that opens a Web
  channel window.
- `docs/architecture/packaging.md`: the third row of the isolation invariant table says the
  installation model satisfies the contract; name what does it now — the Hub creates an
  environment per App and installs into it.
- `docs/architecture/lifecycle.md`: the package lifecycle line says `install -> configure -> open
  a channel`; say that the Web channel's window is opened by `python -m vibepy.serve`, and
  replace `uninstall` with `remove` to match `docs/roadmap.md`.

Nothing else changes. `docs/hub-ui-mockup.html` belongs to M11, and `docs/roadmap.md` is never
edited.

- [ ] **Step 3: Verify the documents against the code**

Run: `make lint typecheck test`
Expected: PASS. Then read each changed paragraph against the module it describes and check that
no sentence states a fact another document owns.

- [ ] **Step 4: Commit**

```bash
git add docs
git commit -m "Record that the Hub is a platform-tier App"
```

---

## Integration

- [ ] Merge `m10-hub-core` into `main` with `--no-ff`, then delete the branch
- [ ] Promote what is still true out of `docs/milestones/M10/` and delete the folder
- [ ] Push, which happens once the milestone is merged and not before
