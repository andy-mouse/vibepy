# CR2 - Hub defects implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Hub one name per App and make every failure path it owns statable, so no
failure or resource loses its guarantees at a boundary.

**Architecture:** The Hub is an App (ADR-024): its Tools are its surface and everything behind
them lives in `internals/`. This plan moves all filesystem, subprocess and metadata work behind
`async` internals that wrap their synchronous bodies in `asyncio.to_thread`, keys every Tool on
one canonical distribution name, and makes each failure travel as a `Diagnostic` carrying a
category — or, when it crossed a process boundary, as the code the child itself reported.

**Tech Stack:** Python 3.12, pydantic, `packaging` (new, for name normalization), `uv` for
environments, pytest with `asyncio_mode = auto`, ruff + pyright strict.

## Global Constraints

- The spec is `docs/milestones/CR2/spec.md`. Its acceptance criteria are the tests.
- Cut the branch `cr2-hub-defects` from `main` before Task 1. Do not push.
- `make lint typecheck test` must pass at the end of every task. 189 tests pass at the start.
- Blocking calls inside async code are wrapped in `asyncio.to_thread`.
- `Any` and `cast` are not acceptable in the public API. Filesystem paths are `pathlib.Path`.
- Optional and configuration parameters are keyword-only.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- Tests verify public contracts. Two departures are named in the spec and only those two:
  `internals/state.py` for an interrupted write, and `Processes` for a cancelled start.
- Run tests with `uv run pytest`. The Hub's tests live in `packages/vibepy-hub/tests/`.
- Do not touch `docs/roadmap.md`.

---

### Task 1: A diagnostic carries a category

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/models.py:1-19`
- Modify: every `Diagnostic(...)` construction site: `tools/installation.py`,
  `tools/configuration.py`, `tools/packages.py`, `tools/runtime.py`
- Create: `docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md`
- Modify: `docs/architecture/errors.md`
- Test: `packages/vibepy-hub/tests/test_diagnostics.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `Diagnostic(code: str, category: ErrorCategory, message: str, details: dict[str, str])`
  — every later task constructs one with all four.

- [ ] **Step 1: Write the failing test**

```python
"""One failure model: a Hub diagnostic says what kind of failure it is."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from tests_support import hub
from vibepy_core.errors import ErrorCategory
from vibepy_hub.models import Diagnostic, RunningApp


def test_a_diagnostic_without_a_category_is_refused() -> None:
    with pytest.raises(ValidationError):
        Diagnostic.model_validate({"code": "hub.not_installed", "message": "no"})


async def test_a_hub_failure_says_whether_a_retry_could_succeed(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("start_app", {"app_name": "todo", "secrets": {}})

    assert isinstance(answered, RunningApp)
    assert answered.diagnostic is not None
    assert answered.diagnostic.category == ErrorCategory.CALLER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/vibepy-hub/tests/test_diagnostics.py -v`
Expected: FAIL — `ImportError` on `Diagnostic` having no `category`, then a `ValidationError`
that is not raised.

- [ ] **Step 3: Add the field**

In `models.py`, import `ErrorCategory` and add the required field. Replace the module docstring's
second paragraph with the code table (the Hub has no architecture document yet; CR3 gives it
one):

```python
"""What the Hub's Tools take and return.

A diagnostic is plain fields because an output model is revalidated, so no
exception instance and no live object can travel in one. It carries a category
because a caller reads that to learn whether a different call could succeed. See
`docs/decisions/ADR-007-framework-guarantees-tool-output.md` and
`docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md`.

The Hub's own codes, until CR3 gives the Hub a document to carry them:

| Code | Category |
| --- | --- |
| `hub.candidate_absent` | caller |
| `hub.install_failed` | execution |
| `hub.no_app_declared` | declaration |
| `hub.multiple_apps_declared` | declaration |
| `hub.declaration_missing` | declaration |
| `hub.facts_unreadable` | execution |
| `hub.source_unreadable` | caller |
| `hub.not_installed` | caller |
| `hub.no_web_channel` | caller |
| `hub.already_running` | caller |
| `hub.not_running` | caller |
| `hub.secret_masked_value` | caller |
| `hub.start_failed` | execution |
"""

from vibepy_core.errors import ErrorCategory


class Diagnostic(BaseModel):
    """An expected, actionable failure, in the form a channel can render."""

    code: str
    category: ErrorCategory
    message: str
    details: dict[str, str] = {}
```

- [ ] **Step 4: Give every existing construction site its category**

Use the table above. `tools/runtime.py`'s `_refusal` takes the category as a keyword-only
parameter so each caller states it:

```python
def _refusal(
    app_name: str, code: str, message: str, /, *, category: ErrorCategory
) -> RunningApp:
    """An App that will not start or stop, and why."""
    return RunningApp(
        app_name=app_name,
        state="installed",
        diagnostic=Diagnostic(
            code=code, category=category, message=message, details={"app_name": app_name}
        ),
    )
```

`hub.not_installed`, `hub.no_web_channel`, `hub.already_running` and `hub.not_running` are
`ErrorCategory.CALLER`; `hub.start_failed` is `ErrorCategory.EXECUTION`. In
`tools/installation.py`, `hub.candidate_absent` is `CALLER`, `hub.install_failed` is `EXECUTION`,
`hub.no_app_declared` and `hub.declaration_missing` are `DECLARATION`. In `tools/packages.py`,
`hub.source_unreadable` is `CALLER`. In `tools/configuration.py`, `hub.not_installed` is
`CALLER`.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest packages/vibepy-hub -v`
Expected: PASS, including the two new tests.

- [ ] **Step 6: Write ADR-029**

Nygard format, `Status: Accepted`. Context: `Diagnostic` was invented with no record;
`code-review/decisions.md` lists the Hub's `Diagnostic` vocabulary among three decisions that
were live and undocumented, and no record in `docs/decisions/` mentions it. `errors.md` defines
the framework's model and is silent on an App's own expected failures, so axis 4 and axis 7
reached the same question from opposite sides. Decision: an App's expected, actionable failure
travels as data inside its own output model, carrying the same `code`, `category`, `message` and
`details` an `ErrorInfo` carries. Rejected alternative: raising for an expected failure, which
would make every actionable Hub answer a protocol error on the Agent channel and, per ADR-007,
cannot travel in a revalidated output model. Consequences: an App publishes codes the framework's
table does not own; a category is required rather than defaulted, so no site inherits a guess; a
renderer and an agent read one shape for both kinds of failure.

- [ ] **Step 7: State it in errors.md**

Under *What the framework does not do*, add a short section: an App may publish an expected,
actionable failure as data in its own output model provided it carries `code`, `category`,
`message` and `details`; the framework's table stays the framework's, and an App's codes are the
App's. Cite ADR-029.

- [ ] **Step 8: Verify and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add packages/vibepy-hub docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md docs/architecture/errors.md
git commit -m "Have a Hub diagnostic say what kind of failure it is (ADR-029)"
```

---

### Task 2: One name, taken from the distribution

**Files:**
- Modify: `packages/vibepy-hub/pyproject.toml` (add `packaging`)
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/projects.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/models.py` (`AppNameField`, `CandidateRow.name`)
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/installation.py:42-48,84-152`
- Create: `docs/decisions/ADR-028-an-app-is-addressed-by-its-distribution-name.md`
- Test: `packages/vibepy-hub/tests/test_installation.py`,
  `packages/vibepy-hub/tests/test_package_sources.py`

**Interfaces:**
- Consumes: `Diagnostic` with a category (Task 1).
- Produces: `Candidate(folder: Path, name: str, version: str | None, declares_app: bool)` where
  `name` is the canonical distribution name; `AppNameField` canonicalizes what a Tool is given;
  `_candidate(deps, app_name) -> Candidate | None` in `tools/installation.py`.

- [ ] **Step 1: Write the failing tests**

In `test_installation.py`:

```python
async def test_one_app_is_one_row_however_it_was_installed(tmp_path: Path) -> None:
    """Installing by the distribution name lists that App once, not twice."""
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    rows = [row for row in listed.apps if row.app_name == "vibepy-todo"]
    assert [row.state for row in rows] == ["installed"]
    assert [row.app_name for row in listed.apps].count("todo") == 0


async def test_a_folder_name_is_not_an_app_name(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        answered = await tools.invoke("install_app", {"app_name": "todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.candidate_absent"


async def test_two_spellings_of_one_name_address_one_app(tmp_path: Path) -> None:
    """The specification compares names by normalizing them, and so does the Hub."""
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "Vibepy_Todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    assert [row.state for row in listed.apps if row.app_name == "vibepy-todo"] == ["installed"]
    assert a_python_lives_in(environment(root, "vibepy-todo"))
```

In `test_package_sources.py`:

```python
async def test_a_folder_whose_project_declares_no_name_offers_nothing(tmp_path: Path) -> None:
    """`name` is required and static, so a project file without one is not a project."""
    source = tmp_path / "packages"
    (source / "nameless").mkdir(parents=True)
    (source / "nameless" / "pyproject.toml").write_text(
        '[project]\nversion = "1.0.0"\n', encoding="utf-8"
    )

    async with hub(tmp_path / "hub") as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})

    assert isinstance(listed, SourceListing)
    assert listed.candidates == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/vibepy-hub/tests/test_installation.py packages/vibepy-hub/tests/test_package_sources.py -v`
Expected: FAIL — `vibepy-todo` is `hub.candidate_absent`, `todo` installs, and the nameless
folder is offered.

- [ ] **Step 3: Declare the dependency**

In `packages/vibepy-hub/pyproject.toml`, add to `dependencies`:

```toml
    "packaging>=24.0",
```

Then `uv lock`.

- [ ] **Step 4: Read the name as the specification defines it**

In `internals/projects.py`:

```python
from packaging.utils import canonicalize_name


@dataclass(frozen=True)
class Candidate:
    """One installable folder inside a registered source.

    `name` is the canonical distribution name, which is what a Hub Tool
    addresses this App by. See
    `docs/decisions/ADR-028-an-app-is-addressed-by-its-distribution-name.md`.
    """

    folder: Path
    name: str
    version: str | None
    declares_app: bool


class _Project(BaseModel):
    """The `[project]` fields a candidate is read from.

    `name` is required and is one of the keys the specification says must be
    static, so a table without one is not a project table. `version` may be
    dynamic, so it stays optional.
    """

    model_config = {"populate_by_name": True}

    name: str
    version: str | None = None
    entry_points: dict[str, dict[str, str]] = Field(default={}, alias="entry-points")
```

`_described` returns `_Project | None`, answering `None` where it previously answered an empty
`_Project`:

```python
def _described(project: Path, /) -> _Project | None:
    """The `[project]` table of a project file, or nothing when there is none."""
    try:
        document = tomllib.loads(project.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        logger.info("unreadable project file at %s", project)
        return None
    try:
        return _Document.model_validate(document).project
    except ValidationError:
        logger.info("no usable project table at %s", project)
        return None
```

`_Document.project` loses its default, since a document without a `[project]` table is not one:

```python
class _Document(BaseModel):
    """A project file, as much of it as a candidate needs."""

    project: _Project
```

And `candidates` skips what it cannot read:

```python
def candidates(source: Path, /) -> tuple[Candidate, ...]:
    """Every immediate subfolder of a source that carries a usable project file."""
    found: list[Candidate] = []
    for folder in sorted(path for path in source.iterdir() if path.is_dir()):
        project = folder / "pyproject.toml"
        if not project.is_file():
            continue
        described = _described(project)
        if described is None:
            continue
        found.append(
            Candidate(
                folder=folder,
                name=str(canonicalize_name(described.name)),
                version=described.version,
                declares_app=APP_GROUP in described.entry_points,
            )
        )
    return tuple(found)
```

- [ ] **Step 5: Canonicalize what a Tool is given**

In `models.py`, `CandidateRow.name` narrows to `str`, and the field every Tool input uses
canonicalizes after it has been gated:

```python
def _one_segment(value: str) -> str:
    """An App name addresses one environment and cannot address its neighbours.

    Every Hub Tool is on the Agent channel (ADR-024), so an App name is a
    model-controlled string that reaches the file system. Refusing it here is
    what makes the channel answer `tool.input_invalid` rather than the Hub grow
    a diagnostic of its own.

    What survives the gate is canonicalized, because an App is addressed by its
    distribution name and the specification compares two of those by
    normalizing them. The gate runs first: normalization does not remove a
    separator.
    """
    if value in {"", ".", ".."} or _SEPARATORS & set(value):
        raise ValueError("an App name is one path segment")
    return str(canonicalize_name(value))
```

- [ ] **Step 6: Key every row on it**

In `tools/installation.py`, `_candidate_folder` becomes `_candidate` and matches the canonical
name alone; `install_app` files the environment under `payload.app_name`, which is already
canonical; `list_apps` keys available rows by `row.name` rather than `row.folder.name`:

```python
def _candidate(deps: HubDeps, app_name: str, /) -> Candidate | None:
    """The registered folder that offers this App, by its distribution name."""
    for source in read_state(deps.root).sources:
        for row in candidates(source):
            if row.name == app_name:
                return row
    return None
```

```python
    for source in read_state(deps.root).sources:
        for row in candidates(source):
            if row.name in rows:
                continue
            rows[row.name] = AppRow(
                app_name=row.name,
                name=row.name,
                version=row.version,
                state="available",
            )
```

`AppRow.name` is the App's own declared name once installed and the distribution name before
that, which is all a listing knows about a folder it has not installed.

- [ ] **Step 7: Update the existing tests to the one name**

Every `install_app`, `configure_app`, `start_app`, `stop_app` and `remove_app` payload in
`packages/vibepy-hub/tests/` takes the distribution name: `todo` becomes `vibepy-todo`, `notes`
becomes `vibepy-notes`, and `plain` becomes `plain-package`. `environment(root, "todo")` becomes
`environment(root, "vibepy-todo")`. `test_an_app_is_started_by_the_name_it_declares` keeps its
subject — a folder's name is not a declaration — and asserts that the App filed as
`vibepy-todo` is started as `todo-app`.

- [ ] **Step 8: Run the tests**

Run: `uv run pytest packages/vibepy-hub -v`
Expected: PASS.

- [ ] **Step 9: Correct the key the mockup joins on**

`docs/hub-ui-mockup.html` keys every row on `id` — `declaredConfig`, `visibleApps` and
`installations` all join on it — and its values are short declared names. The key a Hub Tool
answers to is the distribution name, so the mockup's ids become distribution names, or M11 is
built on a key the Hub does not have: `'todo'` becomes `'vibepy-todo'` in `sourceApps`, and
`'customer-desk'`, `'expense-review'` and `'field-notes'` gain the distribution spelling their
own `name` implies. Nothing else in the file changes: it displays `app.name` and `app.version`,
which are unaffected.

- [ ] **Step 10: Write ADR-028**

Nygard format, `Status: Accepted`. Context: the four name spaces, and what each name can answer
before installation and after it — `[project].name` is required and static and dist-info carries
it afterwards; an entry-point name is not statically reliable because a build backend may add
one; a folder's name is not packaging metadata. Cite the name-normalization specification and
pipx's one-environment-per-package-named-after-the-package. Decision: an App is addressed by its
canonical distribution name, across install, configure, start, stop and list, and that name is
its environment's directory. Rejected: the folder name, which axis 4's own fix proposed and which
is the accidental choice I11 complains about; the declared name, which would leave a folder with
no visible declaration unaddressable. Consequences: a user installs `vibepy-todo` rather than
`todo`; the Hub's own UI is unaffected because it keys rows by identity and displays the App's
declared name; R1 keys a stable port by this name; `AppFacts.declared_name` remains, because the
name `vibepy_core.serve` is addressed by is the declared one.

- [ ] **Step 11: Verify and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add packages/vibepy-hub uv.lock docs/hub-ui-mockup.html docs/decisions/ADR-028-an-app-is-addressed-by-its-distribution-name.md
git commit -m "Address an App by its distribution name (ADR-028)"
```

---

### Task 3: The Hub's work leaves the loop

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/state.py`,
  `internals/projects.py`, `internals/installer.py`, `internals/__init__.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/*.py`,
  `packages/vibepy-hub/src/vibepy_hub/entry.py:38`
- Test: `packages/vibepy-hub/tests/test_concurrency.py` (create)

**Interfaces:**
- Consumes: `candidates`, `read_state`, `write_state`, `read_facts`, `write_facts`,
  `installed_facts` (Task 2's shapes).
- Produces: those six as `async def`, plus
  `async def remove_environment(env: Path, /) -> None`. Every Tool handler awaits them.

- [ ] **Step 1: Write the failing test**

```python
"""Two Hub Tool calls overlap, because no handler holds the loop.

The assertion is an ordering and not a duration: `docs/architecture/runtime.md`
requires overlap to be proven by what happened rather than by how long it took.
Installing runs `uv` twice and reads an environment; listing reads directories.
While the Hub's filesystem work sat on the loop, the light call could not answer
first.
"""

import asyncio
from pathlib import Path

from tests_support import EXAMPLES, hub
from vibepy_hub.models import AppListing


async def test_a_light_hub_call_answers_while_a_slow_one_is_still_running(
    tmp_path: Path,
) -> None:
    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        installing = asyncio.create_task(tools.invoke("install_app", {"app_name": "vibepy-todo"}))
        await asyncio.sleep(0)

        listed = await tools.invoke("list_apps", {})

        assert isinstance(listed, AppListing)
        assert not installing.done()
        await installing
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest packages/vibepy-hub/tests/test_concurrency.py -v`
Expected: FAIL on `assert not installing.done()` — the listing cannot answer until the install
releases the loop.

- [ ] **Step 3: Move each internal behind a thread**

Every function that touches the filesystem keeps its synchronous body under a private name and
gains an `async` face. `state.py`:

```python
async def read_state(root: Path, /) -> HubState:
    """The stored state, or an empty one when nothing readable has been stored."""
    return await asyncio.to_thread(_read_state, root)


def _read_state(root: Path, /) -> HubState:
    path = root / STATE_FILE
    if not path.is_file():
        return HubState()
    try:
        return HubState.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError:
        logger.warning("ignoring an unreadable state file: %s", path)
        return HubState()


async def write_state(root: Path, state: HubState, /) -> None:
    await asyncio.to_thread(_write_state, root, state)
```

Do the same for `candidates` in `projects.py` and for `read_facts`, `write_facts` and
`installed_facts` in `installer.py`. `purelib`, `install` and `describe` are already `async`.
Add the one operation that had no internal at all:

```python
async def remove_environment(env: Path, /) -> None:
    """Delete one App's environment, if it is there."""
    await asyncio.to_thread(shutil.rmtree, env, ignore_errors=True)
```

and the one reading that `_installed` performs on the loop today, in `installer.py`:

```python
async def environments(root: Path, /) -> tuple[Path, ...]:
    """Every environment this Hub created, in a stable order."""
    return await asyncio.to_thread(_environments, root)


def _environments(root: Path, /) -> tuple[Path, ...]:
    envs = root / "envs"
    if not envs.is_dir():
        return ()
    return tuple(sorted(path for path in envs.iterdir() if path.is_dir()))
```

Export `remove_environment` and `environments` from `internals/__init__.py` and add both to
`__all__`. `_installed` uses `environments` in place of its own `envs.is_dir()` / `iterdir()`.

- [ ] **Step 4: Await them from the handlers**

In `tools/installation.py`, `tools/configuration.py`, `tools/packages.py` and
`tools/runtime.py`, every call to those functions gains an `await`, and `shutil.rmtree` is
replaced by `await remove_environment(...)`. `shutil` is no longer imported in
`tools/installation.py`. `_candidate` and `_listing` become `async def` because they now await.
In `entry.py`:

```python
    await asyncio.to_thread(config.root.mkdir, parents=True, exist_ok=True)
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest packages/vibepy-hub -v`
Expected: PASS, the new test included.

- [ ] **Step 6: Verify and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add packages/vibepy-hub
git commit -m "Take the Hub's filesystem work off the event loop"
```

---

### Task 4: State a second call or a crash cannot lose

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/state.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/deps.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/entry.py:39-41`
- Modify: `tools/configuration.py`, `tools/packages.py`, `tools/installation.py`
- Test: `packages/vibepy-hub/tests/test_state.py` (create)

**Interfaces:**
- Consumes: `read_state`, `write_state` (Task 3, async).
- Produces: `HubDeps(root: Path, processes: Processes, state_lock: asyncio.Lock)` and
  `async def update_state(deps: HubDeps, change: Callable[[HubState], HubState], /) -> HubState`,
  which every read-modify-write goes through.

- [ ] **Step 1: Write the failing tests**

```python
"""The Hub's state survives a second caller and an interrupted write."""

import asyncio
from pathlib import Path

import pytest
from tests_support import EXAMPLES, hub
from vibepy_hub.internals.state import STATE_FILE, HubState, read_state, write_state
from vibepy_hub.models import HeldConfig


async def test_two_overlapping_configurations_both_survive(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke("install_app", {"app_name": "vibepy-notes"})

        first, second = await asyncio.gather(
            tools.invoke(
                "configure_app",
                {"app_name": "vibepy-todo", "values": {"db_path": str(tmp_path / "t.db")}},
            ),
            tools.invoke(
                "configure_app",
                {"app_name": "vibepy-notes", "values": {"api_base_url": "https://n"}},
            ),
        )
        assert isinstance(first, HeldConfig)
        assert isinstance(second, HeldConfig)

    held = (await read_state(root)).config
    assert set(held) == {"vibepy-todo", "vibepy-notes"}


async def test_a_write_that_fails_leaves_the_previous_state_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A departure from testing public contracts only, named in the spec: no
    Tool can interrupt a write halfway."""
    root = tmp_path / "hub"
    await write_state(root, HubState(sources=[tmp_path / "kept"], config={}))

    def refuse(src: object, dst: object) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr("vibepy_hub.internals.state.os.replace", refuse)
    with pytest.raises(OSError):
        await write_state(root, HubState(sources=[], config={"lost": {}}))

    assert (await read_state(root)).sources == [tmp_path / "kept"]
    assert [path.name for path in root.iterdir()] == [STATE_FILE]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/vibepy-hub/tests/test_state.py -v`
Expected: FAIL — the gathered pair loses one update, and `os.replace` is not reached because the
file is written in place.

- [ ] **Step 3: Write through a neighbour**

In `state.py`, `_write_state` writes a temporary file beside the target, gives it the
owner-only bits before it is visible under the real name, and moves it into place. `os.replace`
overwrites the destination and the rename is atomic where POSIX requires it, so no reader sees a
half-written file:

```python
def _write_state(root: Path, state: HubState, /) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / STATE_FILE
    pending = root / f"{STATE_FILE}.pending"
    pending.write_text(state.model_dump_json(indent=1), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(root, OWNER_ONLY_DIRECTORY)
        os.chmod(pending, OWNER_ONLY_FILE)
    try:
        os.replace(pending, path)
    except OSError:
        pending.unlink(missing_ok=True)
        raise
```

- [ ] **Step 4: Serialize read-modify-write**

`HubDeps` gains the lock the window owns:

```python
@dataclass
class HubDeps:
    """What one Hub window owns."""

    root: Path
    processes: Processes
    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
```

and `internals/state.py` gains the one operation every mutation uses:

```python
async def update_state(deps: HubDeps, change: Callable[[HubState], HubState], /) -> HubState:
    """Read, change and store the state, with no other call in between.

    ToolRuntime permits concurrent invocations and does not serialize them, so
    a read-modify-write is the App's own to make safe —
    `docs/architecture/runtime.md` puts overlapping mutation in the domain row.
    The lock is the window's, which is where application-scoped state belongs.
    """
    async with deps.state_lock:
        changed = change(await read_state(deps.root))
        await write_state(deps.root, changed)
        return changed
```

Import `HubDeps` lazily where a cycle would form: put `update_state` in `internals/state.py` and
have `internals/deps.py` keep importing only `Processes`, so `state.py` imports `deps.py` and not
the reverse.

- [ ] **Step 5: Route every mutation through it**

`configure_app`, `register_package_source`, `remove_package_source` and `remove_app` replace
their `read_state` / `write_state` pair with one `update_state(deps, ...)` call, each passing a
function of the old state:

```python
    def hold(state: HubState) -> HubState:
        return HubState(
            sources=state.sources,
            config={
                **state.config,
                payload.app_name: {**state.config.get(payload.app_name, {}), **payload.values},
            },
        )

    changed = await update_state(deps, hold)
    kept = changed.config[payload.app_name]
```

`update_state` answers with the state it stored, so a handler reads what it wrote rather than
reading the file a second time. `HubDeps` needs `from dataclasses import dataclass, field`.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest packages/vibepy-hub -v`
Expected: PASS.

- [ ] **Step 7: Verify and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add packages/vibepy-hub
git commit -m "Hold the Hub's state against a second caller and a broken write"
```

---

### Task 5: Facts joined by identity

**Files:**
- Modify: `src/vibepy_core/describe.py`
- Modify: `docs/architecture/packaging.md`
- Modify: `packages/vibepy-hub/src/vibepy_hub/models.py` (`AppFacts`)
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/installer.py:116-145`
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/installation.py:51-134`
- Test: `tests/test_describe_command.py`, `packages/vibepy-hub/tests/test_installation.py`

**Interfaces:**
- Consumes: `Candidate.name` (Task 2), `remove_environment` (Task 3).
- Produces: the `describe` command's objects carry `app_name`, `distribution` and
  `distribution_version`; `AppFacts` carries `distribution`; `describe(env)` returns facts whose
  `declared_name` is that App's own.

- [ ] **Step 1: Write the failing tests**

In `tests/test_describe_command.py`, whose `Described` TypedDict gains the three keys first —
pyright is strict, so a key a test reads must be declared:

```python
class Described(TypedDict):
    """The JSON shape `vibepy_core.describe` writes, as a test reads it."""

    app_name: str
    distribution: str
    distribution_version: str
    app_id: str
    name: str
    version: str
    config_schema: DescribedConfig
    tools: list[DescribedTool]
    pages: list[DescribedPage]


def test_a_description_says_which_declaration_it_describes(tmp_path: Path) -> None:
    """A reader joins two answers about one environment on identity, so the
    command reports the identity of what it described."""
    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    described = described_app(result, "todo-app")
    assert described["app_name"] == "todo-app"
    assert described["distribution"] == "vibepy-todo"
    assert described["distribution_version"] == "0.1.0"
```

In `packages/vibepy-hub/tests/test_installation.py`, the refusal is tested where the join is
made, because a synthesized folder declaring two entry points cannot be installed at all — it
would fail for the wrong reason:

```python
async def test_a_distribution_declaring_two_apps_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One environment holds one App, so two declarations are reported rather
    than one of them silently dropped."""
    root = tmp_path / "hub"

    async def describes_two(env: Path, /) -> tuple[AppFacts, ...]:
        return (
            AppFacts(
                app_id="todo-app",
                name="Todo",
                version="0.0.0",
                declared_name="todo-app",
                distribution="vibepy-todo",
            ),
            AppFacts(
                app_id="second-app",
                name="Second",
                version="0.0.0",
                declared_name="second",
                distribution="vibepy-todo",
            ),
        )

    monkeypatch.setattr("vibepy_hub.tools.installation.describe", describes_two)

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        answered = await tools.invoke("install_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.multiple_apps_declared"
    assert "second" in answered.diagnostic.details["declared"]
    assert not environment(root, "vibepy-todo").exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_describe_command.py packages/vibepy-hub/tests/test_installation.py -v`
Expected: FAIL — `KeyError: 'app_name'` from the command's output, and the two-App install
succeeds with the first of them.

- [ ] **Step 3: Report the identity from the command**

`describe.py` writes what it described alongside the description. `AppDescription` is untouched:
an entrypoint does not know the name it is declared under, and the command is iterating
`AppRef`s already:

```python
def main() -> int:
    """Write one JSON object per declared App to standard output.

    Each object carries the identity of the declaration it describes, so a
    reader that also enumerates the environment joins the two on a name rather
    than on a position.
    """
    try:
        described = [
            {
                "app_name": ref.app_name,
                "distribution": ref.distribution,
                "distribution_version": ref.distribution_version,
                **asdict(describe_app(ref)),
            }
            for ref in discover_apps()
        ]
    except VibepyError as error:
        info = to_error_info(error)
        sys.stderr.write(json.dumps({"code": info.code, "message": info.message}) + "\n")
        return 1
    sys.stdout.write(json.dumps(described) + "\n")
    return 0
```

- [ ] **Step 4: Carry it into the facts**

`AppFacts` gains `distribution: str = ""` beside `declared_name`, with a docstring line saying
it is the distribution that declared this App. In `installer.py`, `_Described` gains
`app_name: str` and `distribution: str`, and `describe` fills both:

```python
    return tuple(
        AppFacts(
            app_id=entry.app_id,
            name=entry.name,
            version=entry.version,
            config_schema=entry.config_schema,
            has_pages=bool(entry.pages),
            declared_name=entry.app_name,
            distribution=entry.distribution,
        )
        for entry in described
    )
```

- [ ] **Step 5: Join on it**

`install_app` selects the facts whose canonical distribution is the App being installed, and
reports rather than truncates:

```python
    mine = [
        facts
        for facts in described
        if str(canonicalize_name(facts.distribution)) == payload.app_name
    ]
    if not mine:
        await remove_environment(env)
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.no_app_declared",
                category=ErrorCategory.DECLARATION,
                message=f"{folder} installs no App",
                details={"folder": str(folder)},
            ),
        )
    if len(mine) > 1:
        await remove_environment(env)
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.multiple_apps_declared",
                category=ErrorCategory.DECLARATION,
                message=f"{payload.app_name!r} declares more than one App",
                details={
                    "app_name": payload.app_name,
                    "declared": ", ".join(sorted(facts.declared_name for facts in mine)),
                },
            ),
        )
    facts = mine[0].model_copy(update={"purelib": metadata})
```

`tools/installation.py` imports `canonicalize_name` from `packaging.utils` for that comparison,
as `internals/projects.py` already does.

The `discover_apps(path=[metadata])` call in `install_app` goes: `describe` running in that
environment is what proves an App is declared there, and it now says which. `_installed` keeps
its `discover_apps` read and joins on both names:

```python
        present = any(
            ref.app_name == wanted and ref.distribution == facts.distribution
            for ref in declared
        )
```

with `wanted` read from the facts alone, so a missing facts file is no longer reported as a
missing declaration.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest -v`
Expected: PASS.

- [ ] **Step 7: Say it in packaging.md**

In *The self-description command*, add that each object carries the `app_name`, `distribution`
and `distribution_version` of the declaration it describes, so a host that also enumerates the
environment joins the two on identity.

- [ ] **Step 8: Verify and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add src/vibepy_core/describe.py docs/architecture/packaging.md packages/vibepy-hub tests
git commit -m "Join an App's facts to its declaration by identity"
```

---

### Task 6: Failure paths inside the Hub's own vocabulary

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/projects.py` (`candidates`)
- Modify: `packages/vibepy-hub/src/vibepy_hub/models.py` (`AppListing.diagnostic`)
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/installation.py:51-134`,
  `tools/packages.py:10-24`
- Test: `packages/vibepy-hub/tests/test_installation.py`,
  `packages/vibepy-hub/tests/test_package_sources.py`

**Interfaces:**
- Consumes: `candidates` (async, Task 3), `remove_environment` (Task 3), the join (Task 5).
- Produces: `candidates` answers `()` for an unreadable source; `AppListing.diagnostic`;
  `hub.facts_unreadable` on a row.

- [ ] **Step 1: Write the failing tests**

```python
async def test_a_source_that_has_disappeared_is_a_diagnostic_not_an_exception(
    tmp_path: Path,
) -> None:
    source = tmp_path / "packages"
    write_project(source / "demo", name="demo", declares=True)
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)})

    shutil.rmtree(source)

    async with hub(root) as tools:
        listed = await tools.invoke("list_apps", {})
        withdrawn = await tools.invoke("remove_package_source", {"path": str(source)})

    assert isinstance(listed, AppListing)
    assert listed.diagnostic is not None
    assert listed.diagnostic.code == "hub.source_unreadable"
    assert isinstance(withdrawn, SourceListing)
    assert withdrawn.sources == []


async def test_a_failed_description_leaves_no_environment_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`purelib` and `describe` run in the App's interpreter, and a failure
    there is a diagnostic like every other failure here."""
    root = tmp_path / "hub"

    async def refuse(env: Path, /) -> Path:
        raise InstallFailed("purelib", "the interpreter did not answer")

    monkeypatch.setattr("vibepy_hub.tools.installation.purelib", refuse)

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        answered = await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.install_failed"
    assert not environment(root, "vibepy-todo").exists()
    assert isinstance(listed, AppListing)
    assert [row.state for row in listed.apps if row.app_name == "vibepy-todo"] == ["available"]


async def test_an_environment_that_cannot_be_interrogated_is_a_row(tmp_path: Path) -> None:
    root = tmp_path / "hub"
    (root / "envs" / "vibepy-todo").mkdir(parents=True)

    async with hub(root) as tools:
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["vibepy-todo"].diagnostic is not None
    assert rows["vibepy-todo"].diagnostic.code == "hub.facts_unreadable"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/vibepy-hub -v -k "disappeared or failed_description or interrogated"`
Expected: FAIL with `FileNotFoundError` out of `list_apps`, an `InstallFailed` escaping
`install_app`, and an `InstallFailed` out of `list_apps` for the bare directory.

- [ ] **Step 3: Let an unreadable source answer with nothing**

In `projects.py`:

```python
def _candidates(source: Path, /) -> tuple[Candidate, ...]:
    try:
        folders = sorted(path for path in source.iterdir() if path.is_dir())
    except OSError:
        logger.info("unreadable source at %s", source)
        return ()
    ...


async def readable(source: Path, /) -> bool:
    """Whether a registered source is still there to be read."""
    return await asyncio.to_thread(Path.is_dir, source)
```

- [ ] **Step 4: Carry the diagnostic where the listing is built**

`AppListing` gains `diagnostic: Diagnostic | None = None`. `list_apps` and `_listing` collect the
sources they could not read and answer with one diagnostic naming them:

```python
    unreadable = [source for source in state.sources if not await readable(source)]
    ...
    return AppListing(
        apps=[rows[name] for name in sorted(rows)],
        diagnostic=None
        if not unreadable
        else Diagnostic(
            code="hub.source_unreadable",
            category=ErrorCategory.CALLER,
            message="a registered source could not be read",
            details={"paths": ", ".join(str(source) for source in unreadable)},
        ),
    )
```

- [ ] **Step 5: Bring the rest of the install inside the guard**

In `install_app`, `purelib`, `describe` and the join all sit inside one
`try/except InstallFailed`, whose handler removes the environment and answers `hub.install_failed`.
`write_facts` is the last statement inside it.

- [ ] **Step 6: Make the listing total**

In `_installed`, an environment whose facts are missing or unreadable becomes a row rather than
an exception:

```python
    for env in await environments(deps.root):
        facts = await read_facts(env)
        if facts is None:
            rows[env.name] = AppRow(
                app_name=env.name,
                state="installed",
                diagnostic=Diagnostic(
                    code="hub.facts_unreadable",
                    category=ErrorCategory.EXECUTION,
                    message=f"{env} holds no readable record of what was installed",
                    details={"app_name": env.name},
                ),
            )
            continue
```

The `await purelib(env)` fallback goes with it: the facts file is written by the only code that
creates an environment, so an environment without one is a broken installation and says so
rather than being interrogated again.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest packages/vibepy-hub -v`
Expected: PASS.

- [ ] **Step 8: Verify and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add packages/vibepy-hub
git commit -m "Answer the Hub's failure paths with diagnostics rather than exceptions"
```

---

### Task 7: A child owned from the moment it exists

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/processes.py:78-201`
- Test: `packages/vibepy-hub/tests/test_processes.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Processes.start(*, app_name, interpreter, config, known_as) -> int` unchanged in
  signature; `Processes.running`, `stop` and `aclose` unchanged; a child is in `_running` from
  the moment it exists.

- [ ] **Step 1: Write the failing tests**

```python
"""A child is this window's resource from the moment it exists.

`Processes` is an internal, and this file is the departure from testing public
contracts that the spec names: an orphaned child is invisible to every Hub Tool,
which is the defect itself.
"""

import asyncio
import sys
from pathlib import Path

import pytest
from vibepy_hub.internals.processes import Processes, StartFailed


async def test_a_cancelled_start_leaves_no_live_child(tmp_path: Path) -> None:
    """`todo-app` is declared in this interpreter's own environment and takes a
    moment to answer, so the cancellation lands while the child is starting."""
    processes = Processes(logs=tmp_path / "logs")
    starting = asyncio.create_task(
        processes.start(
            app_name="todo-app",
            interpreter=Path(sys.executable),
            config={"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
            known_as="todo-app",
        )
    )
    await asyncio.sleep(0.2)
    owned = processes.owned("todo-app")
    assert owned is not None, "the child was not owned while it was starting"

    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting

    assert owned.returncode is not None
    assert processes.running("todo-app") is None
    await processes.aclose()


async def test_a_child_that_dies_before_reading_its_stdin_is_a_start_failure(
    tmp_path: Path,
) -> None:
    """An environment without the framework cannot run the command at all, so
    the child is gone before it reads a configuration large enough to fill the
    pipe. That used to escape as `BrokenPipeError`."""
    env = tmp_path / "bare"
    made = await asyncio.create_subprocess_exec(
        "uv", "venv", str(env), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    assert await made.wait() == 0

    processes = Processes(logs=tmp_path / "logs")
    with pytest.raises(StartFailed):
        await processes.start(
            app_name="gone",
            interpreter=interpreter(env),
            config={"payload": "x" * 500_000},
            known_as="gone",
        )

    assert processes.running("gone") is None
    await processes.aclose()
```

`interpreter` comes from `vibepy_hub.internals`, and `owned` is the one accessor this test needs:
`running` answers for an App that is serving, and what is under test is a child that is owned
before it serves.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/vibepy-hub/tests/test_processes.py -v`
Expected: FAIL — `Processes()` takes no `logs` argument yet, and once it does, the second test
raises `BrokenPipeError`/`ConnectionResetError` rather than `StartFailed`.

- [ ] **Step 3: Own the child**

```python
@dataclass
class _Child:
    """One started App: the process, its port, and whether it has answered."""

    process: asyncio.subprocess.Process
    port: int
    answering: bool = False


class Processes:
    """One window's running Apps."""

    def __init__(self, *, logs: Path) -> None:
        self._running: dict[str, _Child] = {}
        self._logs = logs

    def running(self, app_name: str, /) -> int | None:
        """The port an App is serving on, or nothing when it is not serving."""
        child = self._running.get(app_name)
        if child is None:
            return None
        if child.process.returncode is not None:
            del self._running[app_name]
            return None
        return child.port if child.answering else None

    def owned(self, app_name: str, /) -> asyncio.subprocess.Process | None:
        """The child this window holds for an App, serving or not yet serving.

        `running` answers with a port and therefore only for a child that has
        answered. Ownership begins earlier, and a caller that must release a
        child — or a test that must see one — asks this.
        """
        child = self._running.get(app_name)
        return None if child is None else child.process

    async def _release(self, known_as: str, /) -> None:
        """Kill and reap a child this window can no longer wait for."""
        child = self._running.pop(known_as, None)
        if child is None:
            return
        if child.process.returncode is None:
            child.process.kill()
        await child.process.wait()
```

`start` registers before it does anything a caller can interrupt:

```python
        process = await asyncio.create_subprocess_exec(
            str(interpreter),
            "-m",
            "vibepy_core.serve",
            app_name,
            "--port",
            str(port),
            stdin=asyncio.subprocess.PIPE,
            env=child_environment(),
        )
        child = _Child(process=process, port=port)
        self._running[known_as] = child
        try:
            if process.stdin is not None:
                process.stdin.write(json.dumps(dict(config)).encode())
                await process.stdin.drain()
                process.stdin.close()
            await self._wait_until_answering(process, port)
        except OSError as broken:
            await self._release(known_as)
            raise StartFailed(f"the App did not take its configuration: {broken}") from broken
        except BaseException:
            await self._release(known_as)
            raise
        child.answering = True
        logger.info("started %s on port %d", known_as, port)
        return port
```

`stop` reads `_Child` instead of a tuple, and `aclose` is unchanged. The module docstring gains a
sentence: a child is owned from the moment it exists, so nothing between the spawn and the first
answer can leave one this window cannot release.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest packages/vibepy-hub -v`
Expected: PASS. `entry.py` constructs `Processes(logs=config.root / "logs")`, which Task 8 also
relies on; add it here so the suite passes.

- [ ] **Step 5: Verify and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add packages/vibepy-hub
git commit -m "Own a started child from the moment it exists"
```

---

### Task 8: A refusal that survives the process boundary

**Files:**
- Modify: `src/vibepy_core/app/composition.py:81-94` (rename `_validated`)
- Modify: `src/vibepy_core/errors.py`, `src/vibepy_core/__init__.py`
- Modify: `src/vibepy_core/serve.py:78-109`
- Modify: `docs/architecture/errors.md`, `docs/architecture/packaging.md`
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/processes.py`,
  `packages/vibepy-hub/src/vibepy_hub/tools/runtime.py`
- Test: `tests/test_serve_command.py`, `packages/vibepy-hub/tests/test_runtime.py`

**Interfaces:**
- Consumes: `_Child` and `Processes(logs=...)` (Task 7).
- Produces: `validated_config(definition, raw)` in `vibepy_core.app.composition`;
  `ServeConfigInvalidError`; `StartFailed(reason, *, reported: ChildFailure | None = None)`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_serve_command.py`, `test_a_window_that_will_not_open_stops_the_server` is the
test the finding names — it accepts either a code or a traceback. It keeps its subject and now
asserts the shape:

```python
def test_a_window_that_will_not_open_stops_the_server() -> None:
    """A refused configuration is a server that does not serve, and it says so
    in the shape every other failure of this command uses.

    The App's window is the served application's lifespan, and ASGI defines that
    a server seeing `lifespan.startup.failed` logs the message and exits. What
    makes the refusal legible to whatever started the process is the command
    reporting it before it hands the application over.
    """
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.serve", "todo-app", "--port", str(free_port())],
        input=b"{}",
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode == 1
    written = json.loads(finished.stderr.decode().strip().splitlines()[-1])
    assert written["code"] == "config.invalid"
    assert written["category"] == "caller"
    assert "db_path" in written["details"]["fields"]


def test_configuration_that_is_not_an_object_fails_with_a_framework_code() -> None:
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.serve", "todo-app", "--port", str(free_port())],
        input=b"[]",
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode == 1
    written = json.loads(finished.stderr.decode().strip().splitlines()[-1])
    assert written["code"] == "serve.config_invalid"
    assert written["category"] == "caller"
```

`test_an_unknown_app_name_fails_with_the_framework_code` keeps passing: it reads `code` and
`message`, and both stay.

In `packages/vibepy-hub/tests/test_runtime.py`, replace
`test_an_app_whose_window_rejects_its_configuration_does_not_start`'s assertion:

```python
    assert isinstance(started, RunningApp)
    assert started.url is None
    assert started.diagnostic is not None
    assert started.diagnostic.code == "config.invalid"
    assert started.diagnostic.category == ErrorCategory.CALLER
    assert "db_path" in started.diagnostic.details["fields"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_serve_command.py packages/vibepy-hub/tests/test_runtime.py -v`
Expected: FAIL — the command writes a traceback, and the Hub answers `hub.start_failed`.

- [ ] **Step 3: Make the validation reachable from the command**

In `composition.py`, rename `_validated` to `validated_config` and update its two callers. It
stays out of `vibepy_core/__init__.py`, so the package root's public surface is unchanged:

```python
def validated_config[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT], raw: Mapping[str, object], /
) -> ConfigT:
    """Validate raw configuration against what the App declared.

    Raised before a lifespan is entered, so a window that cannot run acquires
    nothing. The command that opens a channel calls this before it hands the
    application to a server, so a refusal is reported with its code rather than
    only with an exit status.
    """
```

- [ ] **Step 4: Give the command's own code an exception**

In `errors.py`, beside the other `package.`/`config.` failures:

```python
class ServeConfigInvalidError(VibepyError):
    """Standard input did not carry one JSON object of configuration."""

    code = "serve.config_invalid"

    def __init__(self) -> None:
        super().__init__("Configuration on standard input is not a JSON object")
```

Map it `ErrorCategory.CALLER` in `_CATEGORIES` and export it from `vibepy_core/__init__.py`. Add
its row to `errors.md`'s table. CR1 recorded this string as CR2's: it was a published code with
no class behind it.

- [ ] **Step 5: Report every failure the same way**

In `serve.py`, one writer, and configuration validated before the server is handed anything:

```python
def _report(error: VibepyError, /) -> None:
    """Write one failure where whatever started this process can read it."""
    info = to_error_info(error)
    sys.stderr.write(
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

```python
    try:
        config: Mapping[str, object] = _CONFIG.validate_json(sys.stdin.read() or "{}")
    except ValidationError as invalid:
        _report(ServeConfigInvalidError())
        logger.debug("configuration on standard input was unreadable", exc_info=invalid)
        return 1
    try:
        entrypoint = _entrypoint(str(parsed.app_name))
        validated_config(entrypoint.definition, config)
    except (
        AppNotDeclaredError,
        AppEntrypointUnloadableError,
        AppEntrypointInvalidError,
        AppConfigInvalidError,
    ) as error:
        _report(error)
        return 1
    _serve(entrypoint, config, int(parsed.port))
    return 0
```

The validated model is discarded: the window validates again as it opens, which is where
ADR-022 puts it. This call is what makes the refusal legible, not what enforces it.

- [ ] **Step 6: Keep the child's stderr where the Hub can read it**

In `processes.py`, a started App's standard error goes to a file of its own, which is what a
process supervisor does — supervisord gives each program its own `stderr_logfile`. A pipe would
have to be drained for as long as the child lives, because a child that fills the buffer blocks:

```python
@dataclass(frozen=True)
class ChildFailure:
    """What a child said about its own failure, in the framework's shape."""

    code: str
    category: str
    message: str
    details: dict[str, str]


class StartFailed(Exception):
    """A started App never answered. Carries what the child did."""

    def __init__(self, reason: str, *, reported: ChildFailure | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.reported = reported


LOG_TAIL = 4000
"""How much of a child's standard error a failed start carries back."""


def _log_path(logs: Path, known_as: str, /) -> Path:
    logs.mkdir(parents=True, exist_ok=True)
    return logs / f"{known_as}.log"


def _reported(path: Path, /) -> ChildFailure | None:
    """The failure a child described, read from the last object it wrote."""
    try:
        written = path.read_text(encoding="utf-8", errors="replace")[-LOG_TAIL:]
    except OSError:
        return None
    for line in reversed(written.splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("code"), str):
            return ChildFailure(
                code=str(parsed["code"]),
                category=str(parsed.get("category", "execution")),
                message=str(parsed.get("message", "")),
                details={str(k): str(v) for k, v in dict(parsed.get("details", {})).items()},
            )
    return None
```

`start` opens the file in a thread, hands it to the child, closes it when the child is released,
and a `StartFailed` raised after the child has exited carries what `_reported` found:

```python
        path = await asyncio.to_thread(_log_path, self._logs, known_as)
        handle = await asyncio.to_thread(path.open, "wb")
        try:
            process = await asyncio.create_subprocess_exec(
                ..., stderr=handle, env=child_environment()
            )
        finally:
            await asyncio.to_thread(handle.close)
```

and in the failure paths:

```python
        except StartFailed as failure:
            await self._release(known_as)
            raise StartFailed(
                failure.reason, reported=await asyncio.to_thread(_reported, path)
            ) from failure
```

- [ ] **Step 7: Answer with the code the child reported**

In `tools/runtime.py`:

```python
    except StartFailed as failure:
        reported = failure.reported
        if reported is None:
            return _refusal(
                payload.app_name,
                "hub.start_failed",
                str(failure),
                category=ErrorCategory.EXECUTION,
            )
        return RunningApp(
            app_name=payload.app_name,
            state="installed",
            diagnostic=Diagnostic(
                code=reported.code,
                category=ErrorCategory(reported.category),
                message=reported.message,
                details={"app_name": payload.app_name, **reported.details},
            ),
        )
```

A category the enum does not know falls back to `ErrorCategory.EXECUTION`; wrap the conversion in
`try/except ValueError` and log the value at debug.

- [ ] **Step 8: Run the tests**

Run: `uv run pytest -v`
Expected: PASS.

- [ ] **Step 9: Say it in packaging.md**

In *Running a channel*, add that the command validates the configuration against the declaration
before it hands the application to a server, and writes one JSON object of `code`, `category`,
`message` and `details` to standard error for every failure it reports; the window still
validates as it opens, which is where ADR-022 puts it.

- [ ] **Step 10: Verify and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add src docs packages/vibepy-hub tests
git commit -m "Carry a refused configuration across the process boundary"
```

---

### Task 9: The masked sentinel is refused

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/configuration.py`
- Test: `packages/vibepy-hub/tests/test_configuration.py`

**Interfaces:**
- Consumes: `update_state` (Task 4), `Diagnostic` with a category (Task 1).
- Produces: `hub.secret_masked_value`.

- [ ] **Step 1: Write the failing test**

```python
async def test_sending_a_masked_secret_back_is_refused(tmp_path: Path) -> None:
    """`HeldConfig` reports a secret as set, and `set` is not a value.

    The natural round trip — read the form, edit one field, send it back — would
    otherwise write the mask over the secret, and nothing would notice until a
    start failed.
    """
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-notes"})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-notes",
                "values": {"api_base_url": "https://notes.internal", "api_token": TOKEN},
            },
        )
        answered = await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-notes",
                "values": {"api_base_url": "https://elsewhere", "api_token": "set"},
            },
        )

    assert isinstance(answered, HeldConfig)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.secret_masked_value"
    assert "api_token" in answered.diagnostic.details["fields"]
    assert TOKEN in (root / STATE_FILE).read_text(encoding="utf-8")
    assert answered.values["api_base_url"] == "https://notes.internal"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest packages/vibepy-hub/tests/test_configuration.py -v -k masked`
Expected: FAIL — the call succeeds and the token is gone from the state file.

- [ ] **Step 3: Refuse it before anything is written**

In `configure_app`, after `secrets` is read from the schema and before the state is changed:

```python
    masked_back = sorted(
        name for name in payload.values if name in secrets and payload.values[name] == SET
    )
    if masked_back:
        state = await read_state(deps.root)
        kept = state.config.get(payload.app_name, {})
        return HeldConfig(
            app_name=payload.app_name,
            values=masked(kept, secrets),
            secret_fields=list(secrets),
            diagnostic=Diagnostic(
                code="hub.secret_masked_value",
                category=ErrorCategory.CALLER,
                message=f"{SET!r} is how a held secret is reported, not a value it can take",
                details={"app_name": payload.app_name, "fields": ", ".join(masked_back)},
            ),
        )
```

Nothing partial is written: the whole call is refused, so a client that sent one real edit
alongside the mask resends the edit. The docstring gains a line saying so.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest packages/vibepy-hub -v`
Expected: PASS.

- [ ] **Step 5: Verify and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add packages/vibepy-hub
git commit -m "Refuse the mask a held secret is reported as"
```

---

### Task 10: The Todo example teaches the right shape

**Files:**
- Modify: `examples/todo/src/todo_app/entry.py`
- Modify: `tests/test_nicegui_adapter.py:16,134`, `tests/test_dual_channel.py:25,34,55,58`
- Modify: `docs/hub-ui-mockup.html:615-618`
- Test: `examples/todo/tests/test_todo_store.py` (create),
  `packages/vibepy-hub/tests/*` (configuration payloads)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `TodoConfig(db_path: Path, db_key: SecretStr)`;
  `TodoStore(db_path: Path, db_key: SecretStr)` with `create(title) -> Todo` and
  `list_all() -> list[Todo]`, both blocking and both called through `asyncio.to_thread`.

- [ ] **Step 1: Write the failing tests**

```python
"""The sample's store keeps what it was given, where it was told to keep it."""

from pathlib import Path

import pytest
from pydantic import SecretStr
from todo_app.entry import TodoConfig, TodoStore, TodoStoreUnreadable


def test_a_todo_survives_a_new_store_over_the_same_path(tmp_path: Path) -> None:
    config = TodoConfig(db_path=tmp_path / "todo.json", db_key=SecretStr("k"))

    TodoStore(config.db_path, config.db_key).create("buy milk")

    assert [todo.title for todo in TodoStore(config.db_path, config.db_key).list_all()] == [
        "buy milk"
    ]


def test_a_file_stamped_under_another_key_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "todo.json"
    TodoStore(path, SecretStr("one")).create("buy milk")

    with pytest.raises(TodoStoreUnreadable):
        TodoStore(path, SecretStr("two")).list_all()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest examples/todo -v`
Expected: FAIL — `TodoConfig` has no `db_key`, the store keeps a list in memory, and
`TodoStoreUnreadable` does not exist. Add `examples/todo/tests/` to `[tool.pytest.ini_options]
testpaths` if the file is not collected.

- [ ] **Step 3: Honour the path and the key**

```python
class TodoConfig(BaseModel):
    """What the Todo App requires of its host.

    `db_key` is a secret by type, so a Host can tell it from an ordinary string
    without importing this App (ADR-022). The store stamps its file with it, so
    the secret is one this App uses rather than one it merely declares.
    """

    db_path: Path
    db_key: SecretStr


class TodoStoreUnreadable(Exception):
    """The stored file was not written by a holder of this key.

    Raised rather than answered as data: `docs/decisions/ADR-029` gives data to
    an App's *expected* failures, and a store whose file does not match its key
    is a broken resource rather than a step in this App's workflow. The
    framework describes it as `app.unhandled`.
    """


class TodoStore:
    """The app's domain internals. Not a Tool, and no channel reaches it."""

    def __init__(self, db_path: Path, db_key: SecretStr) -> None:
        self.db_path = db_path
        self._key = db_key.get_secret_value().encode()

    def create(self, title: str) -> Todo:
        todos = self.list_all()
        todo = Todo(id=len(todos) + 1, title=title, done=False)
        self._write([*todos, todo])
        return todo

    def list_all(self) -> list[Todo]:
        if not self.db_path.is_file():
            return []
        stored = _Stored.model_validate_json(self.db_path.read_text(encoding="utf-8"))
        body = _TODOS.dump_json(stored.todos)
        if not hmac.compare_digest(stored.stamp, self._stamp(body)):
            raise TodoStoreUnreadable(f"{self.db_path} was not written under this key")
        return list(stored.todos)

    def _write(self, todos: list[Todo], /) -> None:
        body = _TODOS.dump_json(todos)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.write_text(
            _Stored(todos=todos, stamp=self._stamp(body)).model_dump_json(indent=1),
            encoding="utf-8",
        )

    def _stamp(self, body: bytes, /) -> str:
        return hmac.new(self._key, body, hashlib.sha256).hexdigest()
```

with the two small declarations the store reads and writes through:

```python
class _Stored(BaseModel):
    """The file the store keeps, and the digest that says who wrote it."""

    todos: list[Todo]
    stamp: str


_TODOS = TypeAdapter(list[Todo])
```

`_TODOS.dump_json` is what both the stamp and the comparison are computed over, so the bytes
stamped are the bytes stored.

- [ ] **Step 4: Keep the loop free and drop the constant**

The lifespan passes both values; the Tool handlers call the blocking store in a thread; and
`TODO_CONFIG` is deleted:

```python
@asynccontextmanager
async def todo_lifespan(config: TodoConfig) -> AsyncGenerator[TodoStore]:
    """The Todo App's resource, acquired at startup and dropped at shutdown."""
    yield TodoStore(config.db_path, config.db_key)


async def create_todo(ctx: ToolContext[TodoStore], payload: CreateTodoInput) -> Todo:
    return await asyncio.to_thread(ctx.dependencies.create, payload.title)


async def list_todos(ctx: ToolContext[TodoStore], _payload: EmptyInput) -> TodoList:
    return TodoList(todos=await asyncio.to_thread(ctx.dependencies.list_all))
```

- [ ] **Step 5: Narrow a Tool result by validation**

In `todos_page`, `assert isinstance(...)` goes, both times:

```python
    listing = TodoList.model_validate(await ctx.tools.invoke("list_todos", {}))
    ...
    async def add() -> None:
        await ctx.tools.invoke("create_todo", {"title": title.value})
        rendered.refresh(TodoList.model_validate(await ctx.tools.invoke("list_todos", {})))
```

The docstring says why: a Tool's output model is the contract, and `assert` is removed by
`python -O`.

- [ ] **Step 6: Update every consumer**

`tests/test_nicegui_adapter.py` and `tests/test_dual_channel.py` build the configuration
themselves from `tmp_path`:

```python
    config = {"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}
```

Every Hub test that configures `vibepy-todo` adds `"db_key"` — except the two that exist to show
an incomplete configuration, which keep passing `db_path` alone.
`tests/test_describe_command.py`'s
`test_the_command_writes_a_description_of_every_declared_app` asserts the projected schema's
properties, so `["db_path"]` becomes `["db_key", "db_path"]` — the sample now declares two. `docs/hub-ui-mockup.html`'s
Todo entry gains the field it now declares:

```javascript
          config: [
            { name: 'db_path', type: 'path', required: true },
            { name: 'db_key', type: 'secret', required: true }
          ]
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest -v`
Expected: PASS.

- [ ] **Step 8: Verify and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add examples docs/hub-ui-mockup.html tests packages/vibepy-hub pyproject.toml
git commit -m "Have the Todo example keep what it is given, where it says"
```

---

### Task 11: The tests that were not testing

**Files:**
- Modify: `packages/vibepy-hub/tests/test_installation.py:72-95`
- Modify: `packages/vibepy-hub/tests/test_configuration.py:73-79`
- Modify: `tests/test_app_isolation.py:27-31`
- Modify: `packages/vibepy-hub/tests/test_runtime.py`
- Test: the same files

**Interfaces:**
- Consumes: everything from Tasks 1-10.
- Produces: nothing later tasks rely on.

- [ ] **Step 1: Make "leaves its data" mean it**

The store now writes, so the data is written through the App's own Tool and then outlives the
removal:

```python
async def test_removing_an_app_deletes_its_environment_and_leaves_its_data(
    tmp_path: Path,
) -> None:
    root = tmp_path / "hub"
    data = tmp_path / "todo.json"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(data), "db_key": "k"},
            },
        )
        await asyncio.to_thread(TodoStore(data, SecretStr("k")).create, "keep me")
        assert data.is_file()

        await tools.invoke("remove_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    assert [row.state for row in listed.apps if row.app_name == "vibepy-todo"] == ["available"]
    assert not environment(root, "vibepy-todo").exists()
    assert data.is_file()
    assert [todo.title for todo in TodoStore(data, SecretStr("k")).list_all()] == ["keep me"]
```

The App's own store writes the file, at the path the App was configured with, because that is
what makes the assertion mean something: the data is real and it lies outside the environment
`remove_app` deletes. `todo_app` is a development dependency of this workspace, so the Hub's
tests can import it.

- [ ] **Step 2: Make "a restart needs no one" restart**

```python
async def test_a_secret_is_held_so_a_restart_needs_no_one(tmp_path: Path) -> None:
    """A second window over the same root starts the App with nobody present."""
    root = tmp_path / "hub"

    await held_notes_secret(root)

    async with hub(root) as tools:
        held = await tools.invoke("configure_app", {"app_name": "vibepy-notes", "values": {}})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(held, HeldConfig)
    assert held.secret_fields == ["api_token"]
    assert held.values["api_token"] == "set"
    assert isinstance(listed, AppListing)
    assert [row.configured for row in listed.apps if row.app_name == "vibepy-notes"] == [True]
```

It asserts through Tools and no longer reads `STATE_FILE`. The one test that must read the file —
that a held secret is on disk and owner-only — keeps doing so, because that is its subject.

- [ ] **Step 3: Make the isolation test assert isolation**

```python
def test_a_description_is_obtained_without_this_process_loading_the_app(tmp_path: Path) -> None:
    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    assert described_app(result, "todo-app")["name"] == "Todo"
    assert "todo_app" not in sys.modules
    assert "todo_app.entry" not in sys.modules
```

- [ ] **Step 4: Test `secrets`, `already_running` and `declaration_missing`**

In `test_runtime.py`:

```python
async def test_a_secret_supplied_at_start_reaches_the_app(tmp_path: Path) -> None:
    """`start_app`'s `secrets` is merged over what the Hub holds, and the App's
    window validates the result: without the secret it refuses to open."""
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke(
            "configure_app",
            {"app_name": "vibepy-todo", "values": {"db_path": str(tmp_path / "todo.json")}},
        )
        refused = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        started = await tools.invoke(
            "start_app", {"app_name": "vibepy-todo", "secrets": {"db_key": "supplied"}}
        )

    assert isinstance(refused, RunningApp)
    assert refused.diagnostic is not None
    assert refused.diagnostic.code == "config.invalid"
    assert "db_key" in refused.diagnostic.details["fields"]
    assert isinstance(started, RunningApp)
    assert started.diagnostic is None
    assert started.url is not None


async def test_starting_a_running_app_says_it_is_already_running(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
            },
        )
        await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        again = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})

    assert isinstance(again, RunningApp)
    assert again.diagnostic is not None
    assert again.diagnostic.code == "hub.already_running"
```

and in `test_installation.py`:

```python
async def test_an_environment_that_no_longer_declares_its_app_says_so(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        installed = await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        assert isinstance(installed, Installation)

        facts = await read_facts(environment(root, "vibepy-todo"))
        assert facts is not None and facts.purelib is not None
        for info in facts.purelib.glob("vibepy_todo-*.dist-info"):
            shutil.rmtree(info)

        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["vibepy-todo"].diagnostic is not None
    assert rows["vibepy-todo"].diagnostic.code == "hub.declaration_missing"
```

`read_facts` is `async` after Task 3, so await it.

- [ ] **Step 5: Run the whole suite**

Run: `make lint typecheck test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/vibepy-hub tests
git commit -m "Have the Hub's tests assert what their names claim"
```

---

### Task 12: Close the stage

**Files:**
- Modify: `docs/milestones/code-review-roadmap.md`
- Test: the whole suite

- [ ] **Step 1: Mark what is merged**

L1 and CR1 are merged and the file still calls L1 next. Add `Merged.` under L1's and CR1's
acceptance lists, as A0 and Q1 have, and change the order section's "L1 — next" to name CR2.

- [ ] **Step 2: Check the spec off**

Read `docs/milestones/CR2/spec.md`'s acceptance criteria one at a time and name the test that
covers each. Every criterion must have one; if any does not, that is a missing task rather than
a criterion to reinterpret.

- [ ] **Step 3: Verify**

Run: `make lint typecheck test`
Expected: PASS, with more tests than the 189 this stage began with and no test deleted except
where its subject is gone.

- [ ] **Step 4: Commit**

```bash
git add docs/milestones/code-review-roadmap.md
git commit -m "Record that L1 and CR1 are behind us"
```

- [ ] **Step 5: Hand off**

Use `superpowers:finishing-a-development-branch`. The branch merges into `main` with `--no-ff`
and is then deleted; nothing is pushed until the milestone is merged.
