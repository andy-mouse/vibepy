# M11 Hub UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One NiceGUI Page over Hub Core, after Hub Core learns to read a wheelhouse, update an App, and describe an App's configuration.

**Architecture:** Hub Core changes come first (Tasks 2–7), each a Tool-level contract with its own tests, so the Page (Tasks 8–9) has something to be thin over. The Page's rules live in a pure module `presentation.py` that imports no NiceGUI; `board.py` draws and calls Tools through `ctx.tools.invoke` only. Spec: `docs/milestones/M11/spec.md`; screen: `docs/milestones/M11/hub-ui-mockup.html`.

**Tech Stack:** Python 3.12, pydantic 2, NiceGUI 3.16 (`ui.refreshable`, `ui.timer`, `ui.dialog`, `ui.notify`, `nicegui.testing.User`), uv (`uv build`, `uv pip install --find-links`), `packaging.utils.parse_wheel_filename`, pytest + pytest-asyncio (`asyncio_mode = auto`).

## Global Constraints

- `AGENTS.md` rules apply in full: no `Any`/`cast` in public API; keyword-only optional parameters; blocking calls in async code wrapped in `asyncio.to_thread`; `pathlib.Path` never `str` for paths; `logging.getLogger(__name__)`, no `print`; tests verify public contracts, one subject per file.
- Tools are channel-neutral; the Page reaches Hub Core through `ctx.tools.invoke(name, mapping)` and never imports `vibepy_hub.internals`.
- A change is done when `make lint typecheck test` passes. Run it before every commit that touches Python.
- Commit messages follow the repository's voice: a short imperative sentence saying what is now true (see `git log --oneline -20`). No `feat:`/`fix:` prefixes.
- Work on branch `m11-hub-ui`, cut from `main` in Task 1. Do not push. `docs/roadmap.md` has an uncommitted edit of the owner's: never stage it.
- Test markers: `@pytest.mark.integration` on any test that runs `uv` or a child process; `@pytest.mark.apps("vibepy-todo", ...)` on any test taking the `installed` fixture. `strict_markers` is on.
- Ruff's `D` rules are on for `packages/*/src`. Every new public module, class and function gets a docstring in the style of the neighbouring code: what it is, and why, when the why is not obvious. Test files are exempt.
- The suite runs on macOS and Windows. Nothing in a test assumes `/` in paths or `bin/python`; `tests_support` and `installer.interpreter` already handle that.

---

## File structure

| Path | Responsibility |
| --- | --- |
| `packages/vibepy-hub/src/vibepy_hub/internals/wheels.py` | **new**, replaces `projects.py`: what a wheelhouse offers, read from file names and `entry_points.txt` |
| `packages/vibepy-hub/src/vibepy_hub/internals/state.py` | `HubState.source: Path \| None` replaces `sources` |
| `packages/vibepy-hub/src/vibepy_hub/internals/installer.py` | `install(*, wheel, source, env)` with `--find-links` |
| `packages/vibepy-hub/src/vibepy_hub/internals/configuration.py` | `config_fields(schema)`; `is_configured` unchanged |
| `packages/vibepy-hub/src/vibepy_hub/internals/__init__.py` | export list |
| `packages/vibepy-hub/src/vibepy_hub/models.py` | `SourceListing`, `CandidateRow.wheel`, `AppFacts.distribution_version`, `AppRow.distribution_version`/`available_version`, `ConfigField`, `ConfigDescription`, code table |
| `packages/vibepy-hub/src/vibepy_hub/tools/packages.py` | one source: register replaces, remove clears |
| `packages/vibepy-hub/src/vibepy_hub/tools/installation.py` | install from a wheel; `update_app`; `available_version` |
| `packages/vibepy-hub/src/vibepy_hub/tools/configuration.py` | `describe_config` |
| `packages/vibepy-hub/src/vibepy_hub/tools/__init__.py` | `HUB_TOOLS` gains two |
| `packages/vibepy-hub/src/vibepy_hub/pages/__init__.py` | **new** package |
| `packages/vibepy-hub/src/vibepy_hub/pages/presentation.py` | **new**: pure rules from the mockup |
| `packages/vibepy-hub/src/vibepy_hub/pages/board.py` | **new**: the Page |
| `packages/vibepy-hub/src/vibepy_hub/entry.py` | `pages=[BOARD]` |
| `packages/vibepy-hub/tests/tests_support.py` | `build_wheelhouse`, `write_wheel`, `bumped_fixture_wheel`; `write_project` removed |
| `packages/vibepy-hub/tests/conftest.py` | session `wheelhouse` fixture; template root registers it; NiceGUI user plugin |
| `packages/vibepy-hub/tests/test_package_sources.py` | rewritten for one wheelhouse |
| `packages/vibepy-hub/tests/test_installation.py` | wheel-based; port reuse |
| `packages/vibepy-hub/tests/test_update.py` | **new**: `update_app` |
| `packages/vibepy-hub/tests/test_configuration.py` | `describe_config` cases added |
| `packages/vibepy-hub/tests/test_presentation.py` | **new**: the mockup's rules |
| `packages/vibepy-hub/tests/test_board.py` | **new**: the Page through `User` |
| `docs/architecture/lifecycle.md` | Hub Tool table; one wheelhouse |

---

### Task 1: Branch and wheelhouse test support

**Files:**
- Modify: `packages/vibepy-hub/tests/tests_support.py`
- Modify: `packages/vibepy-hub/tests/conftest.py`

**Interfaces:**
- Produces: `build_wheelhouse(out: Path, /) -> None` — builds the framework wheel and the three fixture wheels into `out` with `uv build --wheel`.
- Produces: `bumped_fixture_wheel(fixture: Path, out: Path, /, *, version: str) -> Path` — copies a fixture source tree, sets `[project].version`, drops `[tool.uv.sources]`, builds its wheel into `out`, returns the wheel path.
- Produces: `write_wheel(folder: Path, /, *, name: str, version: str, declares: bool) -> Path` — writes a minimal synthetic wheel (no code) for unit tests of candidate reading.
- Produces: session fixture `wheelhouse: Path`; `template_root` registers it. `FIXTURES` constant stays (the bump helper reads source trees from it).

- [ ] **Step 1: Cut the branch**

```bash
git checkout -b m11-hub-ui
```

- [ ] **Step 2: Replace `write_project` with the three wheel helpers in `tests_support.py`**

Delete `write_project` (bottom of the file) and add, with `import shutil`, `import subprocess`, `import tomllib`, `import zipfile`, `from collections.abc import Sequence` at the top as needed:

```python
CORE = REPO
FIXTURE_PACKAGES = ("vibepy-notes", "vibepy-todo", "vibepy-timer")


def build_wheelhouse(out: Path, /) -> None:
    """Build the framework and every fixture App into one folder of wheels.

    `uv build --wheel` from the workspace root, once for the framework and once per
    fixture member, so the folder is what an in-house wheelhouse is: the Apps and
    the framework they depend on, resolvable with `--find-links` and no index.
    """
    out.mkdir(parents=True, exist_ok=True)
    _build(["uv", "build", "--wheel", "--no-build-logs", "-o", str(out)])
    for package in FIXTURE_PACKAGES:
        _build(["uv", "build", "--wheel", "--no-build-logs", "--package", package, "-o", str(out)])


def bumped_fixture_wheel(fixture: Path, out: Path, /, *, version: str) -> Path:
    """Build one fixture App at another version, for a test whose subject is updating.

    The source tree is copied so the fixture in the repository is never edited, and
    `[tool.uv.sources]` is dropped from the copy because it names a workspace the
    copy is no longer in. The wheel's dependencies still say `vibepy-core`, which the
    wheelhouse resolves.
    """
    staged = out / f"{fixture.name}-{version}-src"
    shutil.copytree(fixture, staged, ignore=shutil.ignore_patterns("__pycache__", "dist"))
    project = staged / "pyproject.toml"
    document = tomllib.loads(project.read_text(encoding="utf-8"))
    lines = [
        line
        for line in project.read_text(encoding="utf-8").splitlines()
        if not line.startswith("[tool.uv.sources]") and not line.startswith("vibepy-core = {")
    ]
    lines = [
        f'version = "{version}"' if line.startswith("version = ") else line for line in lines
    ]
    project.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _build(["uv", "build", "--wheel", "--no-build-logs", str(staged), "-o", str(out)])
    name = str(document["project"]["name"]).replace("-", "_")
    return next(out.glob(f"{name}-{version}-*.whl"))


def _build(command: Sequence[str], /) -> None:
    subprocess.run(command, cwd=REPO, check=True, capture_output=True)


def write_wheel(folder: Path, /, *, name: str, version: str, declares: bool) -> Path:
    """A wheel that installs nothing, shaped as the specification shapes one.

    Enough for what reads a wheelhouse: a parseable file name and a `.dist-info`
    with `entry_points.txt` when `declares`. Installing it is not its purpose.
    """
    folder.mkdir(parents=True, exist_ok=True)
    normalized = name.replace("-", "_").lower()
    info = f"{normalized}-{version}.dist-info"
    path = folder / f"{normalized}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{info}/METADATA", f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
        archive.writestr(f"{info}/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        if declares:
            archive.writestr(f"{info}/entry_points.txt", "[vibepy.apps]\ndemo = demo.entry:APP\n")
        archive.writestr(f"{info}/RECORD", "")
    return path
```

- [ ] **Step 3: Add the session wheelhouse to `conftest.py` and register it in the template**

Replace the `template_root` fixture's body and add `wheelhouse` above it. Add `from tests_support import FIXTURES, build_wheelhouse, hub` (keep `FIXTURES` only if still imported elsewhere in the file; it is not — drop it here).

```python
@pytest.fixture(scope="session")
def wheelhouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One folder of wheels — the framework and the fixture Apps — built once a session.

    What a user registers is a folder of built wheels, so that is what the suite
    registers. Built here rather than committed, because a wheel of this checkout
    is a function of this checkout.
    """
    out = tmp_path_factory.mktemp("wheelhouse")
    build_wheelhouse(out)
    return out


@pytest.fixture(scope="session")
def template_root(tmp_path_factory: pytest.TempPathFactory, wheelhouse: Path) -> Path:
    """Build a Hub root with every fixture App installed, once for the session.

    Built through the Hub's own Tools rather than the installer's functions, so
    the root holds exactly what a user's install leaves: environments, facts,
    state with a port per App, and a route per App declaring Pages.
    """
    root = tmp_path_factory.mktemp("template") / "hub"

    async def build() -> None:
        async with hub(root) as tools:
            await tools.invoke("register_package_source", {"path": str(wheelhouse)})
            for app_name in APPS:
                installed = await tools.invoke("install_app", {"app_name": app_name})
                assert isinstance(installed, Installation)
                assert installed.diagnostic is None, installed.diagnostic

    asyncio.run(build())
    return root
```

Also append, at module bottom:

```python
pytest_plugins = ["nicegui.testing.user_plugin"]
"""The Hub has a Page from this milestone on, and its tests drive it as
`tests/test_nicegui_adapter.py` drives one: through the User fixture."""
```

- [ ] **Step 4: Run the hub suite to see what now fails**

Run: `uv run pytest packages/vibepy-hub -q -x 2>&1 | tail -20`
Expected: FAIL — `template_root` installs from a wheelhouse but `install_app` still reads folders; `test_package_sources.py` and `test_installation.py` import `write_project`. This is the red state Tasks 2–4 turn green. Do not fix anything here.

- [ ] **Step 5: Commit**

```bash
git add packages/vibepy-hub/tests/tests_support.py packages/vibepy-hub/tests/conftest.py
git commit -m "What the Hub's tests register is a folder of wheels"
```

---

### Task 2: Read a wheelhouse

**Files:**
- Create: `packages/vibepy-hub/src/vibepy_hub/internals/wheels.py`
- Delete: `packages/vibepy-hub/src/vibepy_hub/internals/projects.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/__init__.py`
- Create: `packages/vibepy-hub/tests/test_wheels.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Candidate: wheel: Path; name: str; version: str; declares_app: bool` (note `version: str`, no longer optional).
- Produces: `async def candidates(source: Path, /) -> tuple[Candidate, ...]` — sorted by `name`, one per name (highest version).
- Produces: `async def readable(source: Path, /) -> bool` (unchanged signature).
- Produces: `APP_GROUP = "vibepy.apps"`.

- [ ] **Step 1: Write the failing tests**

`packages/vibepy-hub/tests/test_wheels.py`:

```python
"""What a folder of wheels offers, read without installing any of them."""

from pathlib import Path

from tests_support import write_wheel
from vibepy_hub.internals import candidates


async def test_each_wheel_is_a_candidate_named_by_its_distribution(tmp_path: Path) -> None:
    write_wheel(tmp_path, name="Zulu_App", version="1.2.3", declares=True)
    write_wheel(tmp_path, name="alpha-app", version="0.1.0", declares=False)

    found = await candidates(tmp_path)

    assert [(row.name, row.version, row.declares_app) for row in found] == [
        ("alpha-app", "0.1.0", False),
        ("zulu-app", "1.2.3", True),
    ]
    assert all(row.wheel.parent == tmp_path for row in found)


async def test_of_several_versions_the_highest_is_the_candidate(tmp_path: Path) -> None:
    """A wheelhouse keeps old versions; that is not a diagnostic."""
    write_wheel(tmp_path, name="demo", version="1.9.0", declares=True)
    write_wheel(tmp_path, name="demo", version="1.10.0", declares=True)
    write_wheel(tmp_path, name="demo", version="1.2.0", declares=True)

    found = await candidates(tmp_path)

    assert [(row.name, row.version) for row in found] == [("demo", "1.10.0")]


async def test_a_file_that_is_not_a_wheel_is_not_a_candidate(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("not a wheel", encoding="utf-8")
    (tmp_path / "demo.whl").write_bytes(b"not a zip")
    (tmp_path / "sub").mkdir()
    write_wheel(tmp_path / "sub", name="nested", version="1.0.0", declares=True)

    assert await candidates(tmp_path) == ()


async def test_an_absent_folder_offers_nothing_and_is_not_readable(tmp_path: Path) -> None:
    gone = tmp_path / "gone"

    assert await candidates(gone) == ()
    assert await readable(gone) is False
```

Add `readable` to the import line.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/vibepy-hub/tests/test_wheels.py -q`
Expected: FAIL — `ImportError: cannot import name 'write_wheel'` is already fixed by Task 1, so the failure is `candidates` reading folders: `assert [] == [...]`.

- [ ] **Step 3: Write `wheels.py` and delete `projects.py`**

```python
"""What a registered wheelhouse offers, read from file names and one metadata file.

A wheel is a finished build. Its name and version are in its file name by
specification, and its entry points are in `entry_points.txt` inside it, so both
are read without installing or importing anything — and, unlike a project file,
neither is a hint.
"""

import asyncio
import configparser
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path

from packaging.utils import InvalidWheelFilename, parse_wheel_filename
from packaging.version import Version

logger = logging.getLogger(__name__)

APP_GROUP = "vibepy.apps"


@dataclass(frozen=True)
class Candidate:
    """One installable wheel inside a registered source.

    `name` is the canonical distribution name, which is what a Hub Tool addresses
    this App by.
    """

    wheel: Path
    name: str
    version: str
    declares_app: bool


async def candidates(source: Path, /) -> tuple[Candidate, ...]:
    """Every distribution the source offers, one wheel each: the highest version."""
    return await asyncio.to_thread(_candidates, source)


def _candidates(source: Path, /) -> tuple[Candidate, ...]:
    try:
        wheels = sorted(path for path in source.iterdir() if path.is_file() and path.suffix == ".whl")
    except OSError:
        logger.info("unreadable source at %s", source)
        return ()
    best: dict[str, tuple[Version, Path]] = {}
    for wheel in wheels:
        try:
            name, version, _build, _tags = parse_wheel_filename(wheel.name)
        except InvalidWheelFilename:
            logger.info("not a wheel file name: %s", wheel)
            continue
        held = best.get(name)
        if held is None or version > held[0]:
            best[name] = (version, wheel)
    return tuple(
        Candidate(wheel=wheel, name=name, version=str(version), declares_app=_declares_app(wheel))
        for name, (version, wheel) in sorted(best.items())
    )


def _declares_app(wheel: Path, /) -> bool:
    """Whether the wheel's `entry_points.txt` carries the `vibepy.apps` group."""
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = [n for n in archive.namelist() if n.endswith(".dist-info/entry_points.txt")]
            if not names:
                return False
            text = archive.read(names[0]).decode("utf-8", errors="replace")
    except (OSError, zipfile.BadZipFile):
        logger.info("unreadable wheel at %s", wheel)
        return False
    parser = configparser.ConfigParser()
    parser.read_string(text)
    return parser.has_section(APP_GROUP)


async def readable(source: Path, /) -> bool:
    """Whether a registered source is still there to be read."""
    return await asyncio.to_thread(Path.is_dir, source)
```

Note: `parse_wheel_filename` returns the name already normalized (`packaging.utils.NormalizedName`), so `canonicalize_name` is not needed. A `.whl` that is not a zip (`demo.whl`) fails `parse_wheel_filename` first (no version/tags), so it never reaches `zipfile`; a well-named non-zip is caught by `BadZipFile`.

Then:

```bash
git rm -q packages/vibepy-hub/src/vibepy_hub/internals/projects.py
```

In `internals/__init__.py`, replace `from vibepy_hub.internals.projects import Candidate, candidates, readable` with `from vibepy_hub.internals.wheels import APP_GROUP, Candidate, candidates, readable` and add `"APP_GROUP"` to `__all__` (alphabetical).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/vibepy-hub/tests/test_wheels.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add -A packages/vibepy-hub/src/vibepy_hub/internals packages/vibepy-hub/tests/test_wheels.py
git commit -m "A source is a folder of wheels, read by file name and entry points"
```

(`ruff` in the pre-commit hook may flag the still-broken tools modules only for unused imports; if it does, the hook fails — proceed to Task 3 and commit both together with the same message.)

---

### Task 3: One source

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/state.py` (`HubState`)
- Modify: `packages/vibepy-hub/src/vibepy_hub/models.py` (`SourceListing`, `CandidateRow`, code table)
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/packages.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/installation.py` (`_offering`, `_ambiguous`, `list_apps`)
- Rewrite: `packages/vibepy-hub/tests/test_package_sources.py`
- Modify: `packages/vibepy-hub/tests/test_state.py` (`sources=` → `source=`)

**Interfaces:**
- Produces: `HubState.source: Path | None = None` (field `sources` removed).
- Produces: `SourceListing(source: Path | None, candidates: list[CandidateRow], diagnostic: Diagnostic | None = None)`; `CandidateRow(wheel: Path, name: str, version: str, declares_app: bool)`.
- Produces: `AppListing.source: Path | None = None`, the registered folder, set by `list_apps`.
- Produces: Tool `register_package_source(SourcePath) -> SourceListing` replaces the source; Tool `remove_package_source(Empty) -> SourceListing` clears it.
- Produces: `async def _offered(deps: HubDeps, app_name: str, /) -> Candidate | None` in `installation.py` (used by Task 4 and Task 5).
- Removes: `hub.candidate_ambiguous`.

- [ ] **Step 1: Rewrite `test_package_sources.py`**

```python
"""Registering a folder of wheels is what makes its Apps installable."""

import shutil
from pathlib import Path

from tests_support import hub, write_wheel
from vibepy_hub.models import AppListing, SourceListing


async def test_registering_a_folder_lists_what_it_offers(tmp_path: Path) -> None:
    source = tmp_path / "wheels"
    write_wheel(source, name="zulu-app", version="1.2.3", declares=True)
    write_wheel(source, name="alpha-app", version="0.4.0", declares=False)

    async with hub(tmp_path / "hub") as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})

    assert isinstance(listed, SourceListing)
    assert listed.source == source
    assert [(row.name, row.version, row.declares_app) for row in listed.candidates] == [
        ("alpha-app", "0.4.0", False),
        ("zulu-app", "1.2.3", True),
    ]


async def test_registering_a_second_folder_replaces_the_first(tmp_path: Path) -> None:
    """One folder is registered at a time: the Hub has one wheelhouse, not a search path."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_wheel(first, name="one", version="1.0.0", declares=True)
    write_wheel(second, name="two", version="1.0.0", declares=True)

    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(first)})
        listed = await tools.invoke("register_package_source", {"path": str(second)})
        apps = await tools.invoke("list_apps", {})

    assert isinstance(listed, SourceListing)
    assert listed.source == second
    assert [row.name for row in listed.candidates] == ["two"]
    assert isinstance(apps, AppListing)
    assert [row.app_name for row in apps.apps] == ["two"]
    assert apps.source == second


async def test_an_empty_folder_offers_nothing(tmp_path: Path) -> None:
    source = tmp_path / "wheels"
    source.mkdir()

    async with hub(tmp_path / "hub") as tools:
        listed = await tools.invoke("register_package_source", {"path": str(source)})

    assert isinstance(listed, SourceListing)
    assert listed.source == source
    assert listed.candidates == []


async def test_an_absent_folder_is_a_diagnostic_and_registers_nothing(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("register_package_source", {"path": str(tmp_path / "no")})

    assert isinstance(answered, SourceListing)
    assert answered.source is None
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.source_unreadable"


async def test_a_registered_folder_outlives_the_window_and_removing_clears_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "wheels"
    write_wheel(source, name="demo", version="1.0.0", declares=True)
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)})

    async with hub(root) as tools:
        kept = await tools.invoke("list_apps", {})
        removed = await tools.invoke("remove_package_source", {})

    assert isinstance(kept, AppListing)
    assert [row.app_name for row in kept.apps] == ["demo"]
    assert isinstance(removed, SourceListing)
    assert removed.source is None
    assert removed.candidates == []

    async with hub(root) as tools:
        after = await tools.invoke("list_apps", {})

    assert isinstance(after, AppListing)
    assert after.source is None


async def test_a_source_that_has_disappeared_is_a_diagnostic_not_an_exception(
    tmp_path: Path,
) -> None:
    source = tmp_path / "wheels"
    write_wheel(source, name="demo", version="1.0.0", declares=True)
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)})

    shutil.rmtree(source)

    async with hub(root) as tools:
        listed = await tools.invoke("list_apps", {})
        withdrawn = await tools.invoke("remove_package_source", {})

    assert isinstance(listed, AppListing)
    assert listed.diagnostic is not None
    assert listed.diagnostic.code == "hub.source_unreadable"
    assert isinstance(withdrawn, SourceListing)
    assert withdrawn.source is None
```

In `test_state.py`, change `HubState(sources=[tmp_path / "kept"], config={})` to `HubState(source=tmp_path / "kept", config={})`, `HubState(sources=[], config={"lost": {}})` to `HubState(source=None, config={"lost": {}})`, and the assertion `.sources == [tmp_path / "kept"]` to `.source == tmp_path / "kept"`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/vibepy-hub/tests/test_package_sources.py packages/vibepy-hub/tests/test_state.py -q 2>&1 | tail -5`
Expected: FAIL — `SourceListing` has no `source`; `HubState` has no `source`.

- [ ] **Step 3: State and models**

`state.py`: replace `sources: list[Path] = []` with:

```python
    source: Path | None = None
    """The one folder of wheels this Hub installs from. One, because in-house deployment is one
    wheelhouse, and two folders offering one App is a mistake to prevent rather than a case to
    explain."""
```

Update the module docstring's first line to "The two things the framework does not answer: the registered wheelhouse and values."

`models.py`:

```python
class SourcePath(BaseModel):
    """A folder of wheels, as `register_package_source` takes it."""

    path: Path


class CandidateRow(BaseModel):
    """One wheel the source offers: the highest version of one distribution."""

    wheel: Path
    name: str
    version: str
    declares_app: bool


class SourceListing(BaseModel):
    """The registered source, if any, and the candidates found in it."""

    source: Path | None
    candidates: list[CandidateRow]
    diagnostic: Diagnostic | None = None
```

Remove the `| \`hub.candidate_ambiguous\` | caller |` row from the code table in the module docstring.

In `AppFacts`, add after `version`:

```python
    distribution_version: str
    """The version of the wheel that was installed, which is what an update changes.

    An App's own `version` is what its definition declares; the two need not agree,
    and only the distribution's is compared with what the source offers.
    """
```

In `AppRow`, add after `version`:

```python
    distribution_version: str | None = None
    """The installed or offered wheel's version. What the board shows and `update_app` compares."""
```

In `installer.py`, `_Described` gains `distribution_version: str` and `describe` passes
`distribution_version=entry.distribution_version` into `AppFacts`. In `installation.py`, every
`AppRow(...)` built from facts passes `distribution_version=facts.distribution_version`. In
`test_installation.py`, the three monkeypatched `AppFacts(...)` literals gain
`distribution_version="0.0.0"`.

In `AppListing`, add after `apps`:

```python
    source: Path | None = None
    """The registered folder, said with the rows so one read draws the whole board."""
```

- [ ] **Step 4: `tools/packages.py`**

Replace the module body below the imports (keep `Diagnostic`, `SourceListing`, `SourcePath`; add `Empty` to the models import; drop `Sequence` if unused):

```python
async def _listing(deps: HubDeps, /) -> SourceListing:
    """The registered source and what it offers.

    A source that can no longer be read is reported here as `list_apps` reports
    it. One fact, one answer: a Tool that stayed silent about it would contradict
    the other about the same source.
    """
    state = await read_state(deps.root)
    if state.source is None:
        return SourceListing(source=None, candidates=[])
    if not await readable(state.source):
        return SourceListing(source=state.source, candidates=[], diagnostic=_unreadable(state.source))
    return SourceListing(
        source=state.source,
        candidates=[
            CandidateRow(
                wheel=row.wheel, name=row.name, version=row.version, declares_app=row.declares_app
            )
            for row in await candidates(state.source)
        ],
    )


def _unreadable(path: Path, /) -> Diagnostic:
    """Describe a source this Hub could not read, named so a caller can replace it."""
    return Diagnostic(
        code="hub.source_unreadable",
        category=ErrorCategory.CALLER,
        message=f"{path} is not a folder",
        details={"path": str(path)},
    )


async def register_package_source(ctx: ToolContext[HubDeps], payload: SourcePath) -> SourceListing:
    """Offer the wheels in a local folder for installation, replacing the folder before it."""
    deps = ctx.dependencies
    if not await readable(payload.path):
        state = await read_state(deps.root)
        return SourceListing(source=state.source, candidates=[], diagnostic=_unreadable(payload.path))
    await update_state(deps, lambda held: held.model_copy(update={"source": payload.path}))
    return await _listing(deps)


async def remove_package_source(ctx: ToolContext[HubDeps], _payload: Empty) -> SourceListing:
    """Stop offering wheels for installation. Installed Apps are unchanged."""
    await update_state(ctx.dependencies, lambda held: held.model_copy(update={"source": None}))
    return await _listing(ctx.dependencies)


PACKAGE_SOURCE_TOOLS: Sequence[Tool[HubDeps]] = [
    Tool(
        definition=ToolDefinition(
            name="register_package_source",
            description="Offer the wheels in a local folder for installation",
            input_model=SourcePath,
            output_model=SourceListing,
        ),
        handler=register_package_source,
    ),
    Tool(
        definition=ToolDefinition(
            name="remove_package_source",
            description="Stop offering wheels for installation",
            input_model=Empty,
            output_model=SourceListing,
        ),
        handler=remove_package_source,
    ),
]
```

Imports needed: `from pathlib import Path`, `CandidateRow` and `Empty` from models, `HubState` no longer needed. `readable` is imported from `vibepy_hub.internals` already. The absent-folder case answers with the *current* source kept, so a mistyped path does not clear a working registration.

- [ ] **Step 5: `tools/installation.py` — one source**

Replace `_offering` and `_ambiguous` with:

```python
async def _offered(deps: HubDeps, app_name: str, /) -> Candidate | None:
    """The wheel the registered source offers under this name, or nothing."""
    source = (await read_state(deps.root)).source
    if source is None or not await readable(source):
        return None
    return next((row for row in await candidates(source) if row.name == app_name), None)
```

In `install_app`, replace the `offered = await _offering(...)` block through `folder = offered[0].folder` with:

```python
    offered = await _offered(deps, payload.app_name)
    if offered is None:
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available"),
            diagnostic=Diagnostic(
                code="hub.candidate_absent",
                category=ErrorCategory.CALLER,
                message=f"The registered source offers no {payload.app_name!r}",
                details={"app_name": payload.app_name},
            ),
        )
```

(and keep using `offered` below; Task 4 changes what is done with it — for now pass `folder=offered.wheel.parent`? No: leave `install(folder=..., env=env)` calls referring to `offered.wheel` so the file type-checks, and accept that installing is broken until Task 4. Concretely, change `install(folder=folder, env=env)` to `install(folder=offered.wheel, env=env)` and `details={"folder": str(folder)}` to `details={"wheel": str(offered.wheel)}`, message `f"{offered.wheel} installs no App"`.)

In `list_apps`, replace the source loop with:

```python
    source = (await read_state(deps.root)).source
    unreadable = source is not None and not await readable(source)
    if source is not None and not unreadable:
        for row in await candidates(source):
            if row.name in rows:
                continue
            rows[row.name] = AppRow(
                app_name=row.name, name=row.name, distribution_version=row.version, state="available"
            )
    return AppListing(
        apps=[rows[name] for name in sorted(rows)],
        source=source,
        diagnostic=None
        if not unreadable
        else Diagnostic(
            code="hub.source_unreadable",
            category=ErrorCategory.CALLER,
            message="the registered source could not be read",
            details={"path": str(source)},
        ),
    )
```

Drop the `offered`/`claiming` ambiguity loop and its imports (`Sequence` stays if used by `INSTALLATION_TOOLS`).

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest packages/vibepy-hub/tests/test_package_sources.py packages/vibepy-hub/tests/test_state.py packages/vibepy-hub/tests/test_wheels.py -q`
Expected: all pass. `test_state.py`'s `installed`-fixture test still fails until Task 4 (installing from a wheel); that is expected — run only the two source tests plus wheels here: add `-k "not overlapping"`.

- [ ] **Step 7: Lint and typecheck, then commit**

Run: `make lint typecheck`
Expected: clean (fix unused imports it names).

```bash
git add -A packages/vibepy-hub/src packages/vibepy-hub/tests/test_package_sources.py packages/vibepy-hub/tests/test_state.py
git commit -m "The Hub has one wheelhouse, not a search path"
```

---

### Task 4: Install from a wheel

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/installer.py` (`install`)
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/installation.py` (`install_app`)
- Modify: `packages/vibepy-hub/tests/test_installation.py`

**Interfaces:**
- Produces: `async def install(*, wheel: Path, source: Path, env: Path) -> None` — `uv venv env` then `uv pip install --link-mode hardlink --python <env python> --find-links <source> <wheel>`.
- Produces: `install_app` answers `hub.no_app_declared` before creating an environment when `declares_app` is false; reuses a held port.

- [ ] **Step 1: Adjust the installation tests**

In `test_installation.py`:

- Replace `from tests_support import FIXTURES, hub, write_project` with `from tests_support import hub, write_wheel`.
- Every `await tools.invoke("register_package_source", {"path": str(FIXTURES)})` becomes `{"path": str(wheelhouse)}` and the test takes the `wheelhouse: Path` fixture as a parameter.
- Replace `test_a_folder_that_installs_no_app_is_a_diagnostic` with:

```python
async def test_a_wheel_that_declares_no_app_is_refused_before_an_environment_exists(
    tmp_path: Path,
) -> None:
    """A wheel's entry points are a fact, so the answer needs no install to find out."""
    source = tmp_path / "wheels"
    write_wheel(source, name="plain-package", version="1.0.0", declares=False)
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)})
        answered = await tools.invoke("install_app", {"app_name": "plain-package"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.no_app_declared"
    assert not environment(root, "plain-package").exists()
```

(no `integration` marker: nothing runs.)

- Add a port-reuse test:

```python
@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_installing_again_after_a_removal_that_kept_the_port_reuses_it(
    installed: Path, wheelhouse: Path
) -> None:
    """A held port is the App's until `remove_app` forgets it; an install finding one reuses it.

    Reached by `update_app`, whose remove step keeps the port. Driven here through
    the state directly because no Tool removes an environment without its port.
    """
    from vibepy_hub.internals import read_state, remove_environment

    before = (await read_state(installed)).ports["vibepy-todo"]
    await remove_environment(environment(installed, "vibepy-todo"))

    async with hub(installed) as tools:
        again = await tools.invoke("install_app", {"app_name": "vibepy-todo"})

    assert isinstance(again, Installation)
    assert again.diagnostic is None
    assert (await read_state(installed)).ports["vibepy-todo"] == before
```

Also change the docstring of `test_a_traversing_app_name_deletes_nothing` no further; change `test_a_folder_name_is_not_an_app_name` to use `wheelhouse` and app name `"todo"` (still absent).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/vibepy-hub/tests/test_installation.py -q -x 2>&1 | tail -8`
Expected: FAIL at the `wheelhouse` template build: `install()` is handed a wheel as `folder` and `uv pip install <wheel>` cannot resolve `vibepy-core` (no `--find-links`).

- [ ] **Step 3: `installer.install`**

```python
async def install(*, wheel: Path, source: Path, env: Path) -> None:
    """Create an environment of its own for one App and install one wheel there.

    `--find-links` names the wheelhouse the wheel came from, so its dependencies —
    the framework first — resolve from the same folder. That is what a wheelhouse
    is for, and what lets an in-house Hub install with no index reachable.

    The link mode is stated rather than defaulted. [keep the existing paragraph]
    """
    await _run(["uv", "venv", str(env)])
    await _run(
        [
            "uv",
            "pip",
            "install",
            "--link-mode",
            "hardlink",
            "--python",
            str(interpreter(env)),
            "--find-links",
            str(source),
            str(wheel),
        ]
    )
```

Update the module docstring's second sentence: "`uv venv` with `uv pip install` gives an App an environment of its own for one wheel, resolved against the wheelhouse it sits in."

- [ ] **Step 4: `install_app`**

After the `_offered` check and before `env = environment(...)`:

```python
    if not offered.declares_app:
        return Installation(
            app=AppRow(app_name=payload.app_name, state="available", distribution_version=offered.version),
            diagnostic=Diagnostic(
                code="hub.no_app_declared",
                category=ErrorCategory.DECLARATION,
                message=f"{offered.wheel.name} declares no App",
                details={"wheel": str(offered.wheel)},
            ),
        )
```

Change the install call to `await install(wheel=offered.wheel, source=offered.wheel.parent, env=env)`. Delete the post-install `if not mine:` branch (it cannot happen now that the wheel is known to declare the group... but keep it: `describe` may still find no App under this distribution if the entry point is in another group's namespace or fails to load — keep the branch, it is the install-time truth, and the comment says the pre-check covers the common case).

Port: replace the `if facts.has_pages:` block's allocation with:

```python
    if facts.has_pages:

        def hold(state: HubState) -> HubState:
            if payload.app_name in state.ports:
                return state
            return state.model_copy(
                update={"ports": {**state.ports, payload.app_name: allocate(state.ports.values())}}
            )

        port = (await update_state(deps, hold)).ports[payload.app_name]
        await write_route(deps.root, payload.app_name, port=port)
```

Update the comment above `_installed`/`install_app` docstrings where they say "folder".

- [ ] **Step 5: Run the whole hub suite**

Run: `uv run pytest packages/vibepy-hub -q 2>&1 | tail -8`
Expected: all pass (template root now installs from the wheelhouse). Then `make lint typecheck`.

- [ ] **Step 6: Commit**

```bash
git add -A packages/vibepy-hub
git commit -m "An App is installed from its wheel, resolved against the wheelhouse"
```

---

### Task 5: `available_version` and `update_app`

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/models.py` (`AppRow`, code table)
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/installation.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/__init__.py`
- Create: `packages/vibepy-hub/tests/test_update.py`

**Interfaces:**
- Produces: `AppRow.available_version: str | None = None`, compared against `distribution_version`.
- Produces: Tool `update_app(AppName) -> Installation`; code `hub.up_to_date` (caller).
- Produces: `list_apps` sets `available_version` on an installed row whose candidate version differs.

- [ ] **Step 1: Write the failing tests**

```python
"""Updating an installed App keeps what the Hub holds for it."""

from pathlib import Path

import pytest

from tests_support import FIXTURES, hub
from vibepy_hub.internals import read_state
from vibepy_hub.internals.routing import ROUTES
from vibepy_hub.models import AppListing, HeldConfig, Installation, RunningApp


@pytest.fixture(scope="session")
def newer_wheelhouse(tmp_path_factory: pytest.TempPathFactory, wheelhouse: Path) -> Path:
    """The session wheelhouse plus a Todo one version up, built once."""
    from tests_support import bumped_fixture_wheel
    import shutil

    out = tmp_path_factory.mktemp("newer")
    for wheel in wheelhouse.glob("*.whl"):
        shutil.copy(wheel, out / wheel.name)
    bumped_fixture_wheel(FIXTURES / "todo-app", out, version="0.2.0")
    return out


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_a_newer_wheel_shows_as_an_available_version(
    installed: Path, newer_wheelhouse: Path
) -> None:
    async with hub(installed) as tools:
        await tools.invoke("register_package_source", {"path": str(newer_wheelhouse)})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    row = next(row for row in listed.apps if row.app_name == "vibepy-todo")
    assert row.state == "installed"
    assert row.version == "0.0.0"
    assert row.distribution_version == "0.1.0"
    assert row.available_version == "0.2.0"
    notes = next(row for row in listed.apps if row.app_name == "vibepy-notes")
    assert notes.available_version is None


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_updating_keeps_configuration_port_and_route(
    tmp_path: Path, installed: Path, newer_wheelhouse: Path
) -> None:
    async with hub(installed) as tools:
        await tools.invoke("register_package_source", {"path": str(newer_wheelhouse)})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.db"), "db_key": "k"},
            },
        )
        port_before = (await read_state(installed)).ports["vibepy-todo"]
        route_before = (installed / ROUTES / "vibepy-todo.yml").read_text(encoding="utf-8")

        updated = await tools.invoke("update_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})
        started = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        await tools.invoke("stop_app", {"app_name": "vibepy-todo"})

    assert isinstance(updated, Installation)
    assert updated.diagnostic is None
    assert updated.app.distribution_version == "0.2.0"
    assert isinstance(listed, AppListing)
    row = next(row for row in listed.apps if row.app_name == "vibepy-todo")
    assert row.distribution_version == "0.2.0"
    assert row.available_version is None
    assert row.configured is True
    assert (await read_state(installed)).ports["vibepy-todo"] == port_before
    assert (installed / ROUTES / "vibepy-todo.yml").read_text(encoding="utf-8") == route_before
    assert isinstance(started, RunningApp)
    assert started.diagnostic is None


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_updating_an_app_at_the_offered_version_is_a_diagnostic(installed: Path) -> None:
    async with hub(installed) as tools:
        answered = await tools.invoke("update_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.up_to_date"
    assert answered.app.state == "installed"


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_updating_a_running_app_is_refused(
    tmp_path: Path, installed: Path, newer_wheelhouse: Path
) -> None:
    async with hub(installed) as tools:
        await tools.invoke("register_package_source", {"path": str(newer_wheelhouse)})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.db"), "db_key": "k"},
            },
        )
        await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        answered = await tools.invoke("update_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})
        await tools.invoke("stop_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.already_running"
    assert isinstance(listed, AppListing)
    assert [row.distribution_version for row in listed.apps if row.app_name == "vibepy-todo"] == [
        "0.1.0"
    ]


async def test_updating_an_app_that_is_not_installed_is_a_diagnostic(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("update_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_installed"


@pytest.mark.apps("vibepy-todo")
@pytest.mark.integration
async def test_updating_an_app_the_source_no_longer_offers_is_a_diagnostic(
    tmp_path: Path, installed: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    async with hub(installed) as tools:
        await tools.invoke("register_package_source", {"path": str(empty)})
        answered = await tools.invoke("update_app", {"app_name": "vibepy-todo"})

    assert isinstance(answered, Installation)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.candidate_absent"
```

Move the `import shutil` and `bumped_fixture_wheel` import to the top of the file (ruff will insist). `HeldConfig` unused → remove.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/vibepy-hub/tests/test_update.py -q -x 2>&1 | tail -5`
Expected: FAIL — `ToolNotFoundError: update_app` (first test fails on `available_version` attribute).

- [ ] **Step 3: Models**

In `AppRow`, after `version`:

```python
    available_version: str | None = None
    """The version the source offers when it is not the installed one; `update_app` installs it."""
```

Code table: add `| \`hub.up_to_date\` | caller |` after `hub.already_installed`.

- [ ] **Step 4: `list_apps` sets `available_version`**

In the candidate loop from Task 3 Step 5, replace the `if row.name in rows: continue` with:

```python
            held = rows.get(row.name)
            if held is not None:
                if held.distribution_version is not None and held.distribution_version != row.version:
                    rows[row.name] = held.model_copy(update={"available_version": row.version})
                continue
```

- [ ] **Step 5: `update_app`**

Refactor `install_app` so the part after the offered/declared checks becomes a helper both Tools call:

```python
async def _install_offered(deps: HubDeps, app_name: str, offered: Candidate, /) -> Installation:
    """Create the environment, describe it, keep its facts, give it an address.

    Shared by installing and updating: an update is this, over an environment that
    was removed while the Hub kept everything else it held for the App.
    """
    env = environment(deps.root, app_name)
    try:
        ...  # the existing body from `await install(...)` through `await write_facts(env, facts)`
    except InstallFailed as failure:
        ...  # unchanged
    if facts.has_pages:
        ...  # the port-reusing block from Task 4
    return Installation(app=AppRow(...))  # unchanged
```

`install_app` keeps: `_offered` → `hub.candidate_absent`; `declares_app` → `hub.no_app_declared`; env exists → `hub.already_installed`; then `return await _install_offered(deps, payload.app_name, offered)`.

```python
async def update_app(ctx: ToolContext[HubDeps], payload: AppName) -> Installation:
    """Replace an installed App with the version its source offers, keeping what the Hub holds.

    Configuration values, the port, the route and the data the App wrote elsewhere
    all survive: only the environment is remade. A running App is refused rather
    than restarted, because a restart policy is a decision this Tool does not own,
    and the user has Stop.
    """
    deps = ctx.dependencies
    facts = await installed_facts(deps.root, payload.app_name)
    if facts is None:
        return _refused(payload.app_name, "hub.not_installed", f"{payload.app_name!r} is not installed", state="available")
    if deps.processes.running(payload.app_name):
        return _refused(payload.app_name, "hub.already_running", f"{payload.app_name!r} is running; stop it first", state="running", version=facts.distribution_version)
    offered = await _offered(deps, payload.app_name)
    if offered is None:
        return _refused(payload.app_name, "hub.candidate_absent", f"The registered source offers no {payload.app_name!r}", state="installed", version=facts.distribution_version)
    if offered.version == facts.distribution_version:
        return _refused(payload.app_name, "hub.up_to_date", f"{payload.app_name!r} is already at {facts.distribution_version}", state="installed", version=facts.distribution_version)
    await remove_environment(environment(deps.root, payload.app_name))
    return await _install_offered(deps, payload.app_name, offered)


def _refused(app_name: str, code: str, message: str, /, *, state: str, version: str | None = None) -> Installation:
    """An update that did not happen, and why. Every refusal here is the caller's to act on."""
    return Installation(
        app=AppRow(app_name=app_name, state=state, distribution_version=version),
        diagnostic=Diagnostic(
            code=code, category=ErrorCategory.CALLER, message=message, details={"app_name": app_name}
        ),
    )
```

Wrap long lines to 100 columns. Add `installed_facts` and `Candidate` to the `vibepy_hub.internals` import. Register in `INSTALLATION_TOOLS`:

```python
    Tool(
        definition=ToolDefinition(
            name="update_app",
            description="Replace an installed App with the version its source offers",
            input_model=AppName,
            output_model=Installation,
        ),
        handler=update_app,
    ),
```

Export `update_app` from `tools/__init__.py` (import and `__all__`).

- [ ] **Step 6: Run to verify pass, then the whole hub suite**

Run: `uv run pytest packages/vibepy-hub/tests/test_update.py -q` then `uv run pytest packages/vibepy-hub -q 2>&1 | tail -5`, then `make lint typecheck`.
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add -A packages/vibepy-hub
git commit -m "An App updates to the version its wheelhouse offers, keeping what the Hub holds"
```

---

### Task 6: `describe_config`

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/configuration.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/__init__.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/models.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/configuration.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/__init__.py`
- Modify: `packages/vibepy-hub/tests/test_configuration.py`

**Interfaces:**
- Produces: `class ConfigField(BaseModel): name: str; type: str; required: bool` — `type ∈ {"string", "path", "integer", "secret", "other"}`.
- Produces: `class ConfigDescription(BaseModel): app_name: str; fields: list[ConfigField]; values: dict[str, object]; secrets_set: list[str]; diagnostic: Diagnostic | None = None`.
- Produces: `def config_fields(schema: Mapping[str, object], /) -> tuple[ConfigField, ...]` in `internals/configuration.py`.
- Produces: Tool `describe_config(AppName) -> ConfigDescription`.

- [ ] **Step 1: Write the failing tests** (append to `test_configuration.py`)

```python
@pytest.mark.apps("vibepy-notes", "vibepy-todo")
@pytest.mark.integration
async def test_an_apps_configuration_is_described_by_field(installed: Path) -> None:
    """Notes declares a string and a secret; Todo a path and a secret. Both required."""
    async with hub(installed) as tools:
        notes = await tools.invoke("describe_config", {"app_name": "vibepy-notes"})
        todo = await tools.invoke("describe_config", {"app_name": "vibepy-todo"})

    assert isinstance(notes, ConfigDescription)
    assert notes.diagnostic is None
    assert [(f.name, f.type, f.required) for f in notes.fields] == [
        ("api_base_url", "string", True),
        ("api_token", "secret", True),
    ]
    assert notes.values == {}
    assert notes.secrets_set == []
    assert isinstance(todo, ConfigDescription)
    assert [(f.name, f.type, f.required) for f in todo.fields] == [
        ("db_path", "path", True),
        ("db_key", "secret", True),
    ]


@pytest.mark.apps("vibepy-notes")
@pytest.mark.integration
async def test_a_description_carries_held_values_and_names_held_secrets(installed: Path) -> None:
    await held_notes_secret(installed)

    async with hub(installed) as tools:
        described = await tools.invoke("describe_config", {"app_name": "vibepy-notes"})

    assert isinstance(described, ConfigDescription)
    assert described.values == {"api_base_url": "https://notes.internal"}
    assert described.secrets_set == ["api_token"]
    assert TOKEN not in described.model_dump_json()


async def test_describing_an_app_that_is_not_installed_is_a_diagnostic(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("describe_config", {"app_name": "vibepy-todo"})

    assert isinstance(answered, ConfigDescription)
    assert answered.fields == []
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_installed"
```

Add `ConfigDescription` to the models import.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/vibepy-hub/tests/test_configuration.py -q -k describ 2>&1 | tail -5`
Expected: FAIL — `ImportError: ConfigDescription`.

- [ ] **Step 3: Models**

```python
class ConfigField(BaseModel):
    """One field an App declares, as much of it as a form needs.

    `type` is `string`, `path`, `integer`, `secret` or `other`, read from the
    projected schema's `type` and `format`. A string because an output model
    round-trips through JSON and the set is the Hub's to publish.
    """

    name: str
    type: str
    required: bool


class ConfigDescription(BaseModel):
    """What one App declares and what the Hub holds for it, in one answer.

    The read half of `configure_app`: `values` carries no secret and
    `secrets_set` names the secrets that have one, so the answer is safe to show
    and safe to send back.
    """

    app_name: str
    fields: list[ConfigField] = []
    values: dict[str, object] = {}
    secrets_set: list[str] = []
    diagnostic: Diagnostic | None = None
```

- [ ] **Step 4: `internals/configuration.py`**

Extend `_SchemaField` with `type: str | None = None` and add:

```python
def config_fields(schema: Mapping[str, object], /) -> tuple[ConfigField, ...]:
    """Return every declared field with the type a form renders it as.

    Pydantic projects `SecretStr` as `format: password`, `Path` as `format: path`
    and `int` as `type: integer`; everything else a form treats as text, and
    what it does not recognise it says so rather than guessing.
    """
    try:
        described = _ConfigSchema.model_validate(dict(schema))
    except ValidationError:
        logger.info("unreadable configuration schema")
        return ()
    required = set(described.required)
    return tuple(
        ConfigField(name=name, type=_kind(field), required=name in required)
        for name, field in described.properties.items()
    )


def _kind(field: _SchemaField, /) -> str:
    if field.format == "password":
        return "secret"
    if field.format == "path":
        return "path"
    if field.type == "integer":
        return "integer"
    if field.type == "string":
        return "string"
    return "other"
```

Import `ConfigField` from `vibepy_hub.models`. Export `config_fields` from `internals/__init__.py`.

- [ ] **Step 5: The Tool**

In `tools/configuration.py`:

```python
async def describe_config(ctx: ToolContext[HubDeps], payload: AppName) -> ConfigDescription:
    """What one App declares it needs, and what the Hub holds for it so far."""
    deps = ctx.dependencies
    facts = await installed_facts(deps.root, payload.app_name)
    if facts is None:
        return ConfigDescription(
            app_name=payload.app_name,
            diagnostic=Diagnostic(
                code="hub.not_installed",
                category=ErrorCategory.CALLER,
                message=f"{payload.app_name!r} is not installed",
                details={"app_name": payload.app_name},
            ),
        )
    secrets = secret_fields(facts.config_schema)
    held = (await read_state(deps.root)).config.get(payload.app_name, {})
    return ConfigDescription(
        app_name=payload.app_name,
        fields=list(config_fields(facts.config_schema)),
        values=without_secrets(held, secrets),
        secrets_set=list(held_secrets(held, secrets)),
    )
```

Imports: `AppName`, `ConfigDescription` from models; `config_fields`, `read_state` from internals. Add to `CONFIGURATION_TOOLS`:

```python
    Tool(
        definition=ToolDefinition(
            name="describe_config",
            description="What an App declares it needs, and what is held for it",
            input_model=AppName,
            output_model=ConfigDescription,
        ),
        handler=describe_config,
    ),
```

Export `describe_config` from `tools/__init__.py`.

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest packages/vibepy-hub/tests/test_configuration.py -q` then `make lint typecheck`.
Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add -A packages/vibepy-hub
git commit -m "What an App declares and what is held for it can be read, not only written"
```

---

### Task 7: The mockup's rules as pure functions

**Files:**
- Create: `packages/vibepy-hub/src/vibepy_hub/pages/__init__.py`
- Create: `packages/vibepy-hub/src/vibepy_hub/pages/presentation.py`
- Create: `packages/vibepy-hub/tests/test_presentation.py`

**Interfaces:**
- Produces:

```python
STAGES: tuple[str, str, str, str] = ("Available", "Installed", "Configured", "Running")

@dataclass(frozen=True)
class Mark:            # one rail step
    label: str
    done: bool
    symbol: str        # "✓" | "!" | "↑"

@dataclass(frozen=True)
class Action:
    label: str         # "Install" | "Stop" | "Uninstall" | "Configure" | "Update" | "Start"
    tool: str          # the Tool it invokes
    primary: bool
    enabled: bool = True

@dataclass(frozen=True)
class RowView:
    app_name: str
    title: str
    version: str | None
    """The wheel's version: what installs and what an update changes."""
    marks: tuple[Mark, Mark, Mark, Mark]
    actions: tuple[Action, ...]
    diagnostic: Diagnostic | None

def row_view(row: AppRow, /, *, declares_fields: bool) -> RowView
def summary(rows: Sequence[AppRow], /) -> tuple[int, int, int]      # available, installed, running
def sort_rows(rows: Sequence[AppRow], /) -> list[AppRow]            # running, installed, available; then name
def save_request(fields: Sequence[ConfigField], entered: Mapping[str, str], secrets_set: Sequence[str], /) -> dict[str, object] | list[str]
```

`save_request` returns the `values` mapping for `configure_app`, or the list of missing required field names when the save must not be sent.

- [ ] **Step 1: Write the failing tests**

```python
"""The board's rules, as the mockup states them, with no screen involved."""

from vibepy_core.errors import ErrorCategory
from vibepy_hub.models import AppRow, ConfigField, Diagnostic
from vibepy_hub.pages.presentation import row_view, save_request, sort_rows, summary


def available(name: str = "demo") -> AppRow:
    return AppRow(app_name=name, name=name.title(), distribution_version="1.0.0", state="available")


def installed(name: str = "demo", *, configured: bool = False, available_version: str | None = None) -> AppRow:
    return AppRow(
        app_name=name, name=name.title(), version="0.0.0", distribution_version="1.0.0",
        state="installed", configured=configured, has_pages=True, available_version=available_version,
    )


def running(name: str = "demo") -> AppRow:
    return AppRow(app_name=name, name=name.title(), version="0.0.0", distribution_version="1.0.0", state="running", configured=True, has_pages=True)


def test_an_available_app_offers_install_only() -> None:
    view = row_view(available(), declares_fields=False)
    assert [(a.label, a.tool, a.primary) for a in view.actions] == [("Install", "install_app", True)]
    assert [m.done for m in view.marks] == [True, False, False, False]


def test_a_running_app_offers_stop_only_and_every_stage_is_done() -> None:
    view = row_view(running(), declares_fields=True)
    assert [a.label for a in view.actions] == ["Stop"]
    assert [m.done for m in view.marks] == [True, True, True, True]


def test_an_unconfigured_app_cannot_start_and_is_told_to_configure() -> None:
    view = row_view(installed(configured=False), declares_fields=True)
    by_label = {a.label: a for a in view.actions}
    assert set(by_label) == {"Uninstall", "Configure", "Start"}
    assert by_label["Configure"].primary is True
    assert by_label["Start"].enabled is False
    assert view.marks[2].symbol == "!"
    assert view.marks[2].done is False


def test_a_configured_app_starts_and_configure_is_secondary() -> None:
    view = row_view(installed(configured=True), declares_fields=True)
    by_label = {a.label: a for a in view.actions}
    assert by_label["Start"].primary is True and by_label["Start"].enabled is True
    assert by_label["Configure"].primary is False
    assert [m.done for m in view.marks] == [True, True, True, False]


def test_an_app_declaring_no_fields_offers_no_configure_and_counts_as_configured() -> None:
    view = row_view(installed(configured=True), declares_fields=False)
    assert "Configure" not in [a.label for a in view.actions]
    assert view.marks[2].done is True


def test_a_newer_version_replaces_start_with_update() -> None:
    view = row_view(installed(configured=True, available_version="2.0.0"), declares_fields=False)
    labels = [a.label for a in view.actions]
    assert "Update" in labels and "Start" not in labels
    assert view.marks[1].symbol == "↑"
    update = next(a for a in view.actions if a.label == "Update")
    assert update.tool == "update_app" and update.primary is True


def test_a_row_with_a_diagnostic_offers_uninstall_only() -> None:
    broken = installed().model_copy(update={"diagnostic": Diagnostic(
        code="hub.facts_unreadable", category=ErrorCategory.EXECUTION, message="no record")})
    view = row_view(broken, declares_fields=False)
    assert [a.label for a in view.actions] == ["Uninstall"]
    assert view.diagnostic is not None and view.diagnostic.code == "hub.facts_unreadable"


def test_a_row_shows_the_wheels_version_not_the_apps_declared_one() -> None:
    view = row_view(installed(), declares_fields=False)
    assert view.version == "1.0.0"


def test_rows_sort_running_first_then_by_name() -> None:
    rows = [available("zeta"), installed("beta"), running("alpha"), available("gamma")]
    assert [r.app_name for r in sort_rows(rows)] == ["alpha", "beta", "gamma", "zeta"]


def test_summary_counts_each_state() -> None:
    assert summary([available(), available("b"), installed("c"), running("d")]) == (2, 1, 1)


FIELDS = [
    ConfigField(name="api_base_url", type="string", required=True),
    ConfigField(name="api_token", type="secret", required=True),
    ConfigField(name="limit", type="integer", required=False),
]


def test_a_save_omits_an_empty_secret_that_is_already_held() -> None:
    sent = save_request(FIELDS, {"api_base_url": "https://x", "api_token": "", "limit": ""}, ["api_token"])
    assert sent == {"api_base_url": "https://x", "limit": ""}


def test_a_save_sends_a_typed_secret() -> None:
    sent = save_request(FIELDS, {"api_base_url": "https://x", "api_token": "new", "limit": "3"}, [])
    assert sent == {"api_base_url": "https://x", "api_token": "new", "limit": "3"}


def test_a_save_missing_a_required_value_names_every_missing_field() -> None:
    assert save_request(FIELDS, {"api_base_url": "", "api_token": "", "limit": ""}, []) == [
        "api_base_url",
        "api_token",
    ]


def test_a_held_secret_satisfies_its_requirement() -> None:
    assert save_request(FIELDS, {"api_base_url": "https://x", "api_token": ""}, ["api_token"]) == {
        "api_base_url": "https://x"
    }
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/vibepy-hub/tests/test_presentation.py -q 2>&1 | tail -3`
Expected: FAIL — `ModuleNotFoundError: vibepy_hub.pages`.

- [ ] **Step 3: Implement**

`pages/__init__.py`:

```python
"""The Hub's Web channel: one board over the Hub's own Tools."""
```

`pages/presentation.py`:

```python
"""The board's rules, stated once and away from the screen.

Everything here is a function of Tool output. It imports no Web technology, so
the rules the mockup states — which actions a state gets, when Start is
disabled, what a save sends — are checked without rendering anything.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vibepy_hub.models import AppRow, ConfigField, Diagnostic

STAGES: tuple[str, str, str, str] = ("Available", "Installed", "Configured", "Running")
_ORDER = {"running": 0, "installed": 1, "available": 2}


@dataclass(frozen=True)
class Mark:
    """One step of a row's rail."""

    label: str
    done: bool
    symbol: str


@dataclass(frozen=True)
class Action:
    """One button, and the Tool it invokes."""

    label: str
    tool: str
    primary: bool
    enabled: bool = True


@dataclass(frozen=True)
class RowView:
    """One App as the board shows it."""

    app_name: str
    title: str
    version: str | None
    marks: tuple[Mark, Mark, Mark, Mark]
    actions: tuple[Action, ...]
    diagnostic: Diagnostic | None


def _stage(row: AppRow, /, *, configured: bool) -> int:
    if row.state == "available":
        return 0
    if row.state == "running":
        return 3
    return 2 if configured else 1


def row_view(row: AppRow, /, *, declares_fields: bool) -> RowView:
    """Describe one row: its rail, its actions, its diagnostic.

    An App declaring no fields is configured the moment it is installed; the Tool
    already says so in `configured`, and `declares_fields` only decides whether a
    Configure button has anything to open.
    """
    configured = row.configured or not declares_fields
    needs_configuration = row.state == "installed" and row.diagnostic is None and not configured
    stage = _stage(row, configured=configured)
    marks = tuple(
        Mark(
            label=label,
            done=index <= stage,
            symbol="!" if index == 2 and needs_configuration
            else "↑" if index == 1 and row.available_version is not None
            else "✓",
        )
        for index, label in enumerate(STAGES)
    )
    return RowView(
        app_name=row.app_name,
        title=row.name or row.app_name,
        version=row.distribution_version,
        marks=(marks[0], marks[1], marks[2], marks[3]),
        actions=_actions(row, configured=configured, declares_fields=declares_fields),
        diagnostic=row.diagnostic,
    )


def _actions(row: AppRow, /, *, configured: bool, declares_fields: bool) -> tuple[Action, ...]:
    if row.state == "available":
        return (Action("Install", "install_app", primary=True),)
    if row.state == "running":
        return (Action("Stop", "stop_app", primary=False),)
    if row.diagnostic is not None:
        return (Action("Uninstall", "remove_app", primary=False),)
    actions = [Action("Uninstall", "remove_app", primary=False)]
    if declares_fields:
        actions.append(Action("Configure", "describe_config", primary=not configured))
    if row.available_version is not None:
        actions.append(Action("Update", "update_app", primary=configured))
    else:
        # A window validates configuration before it acquires anything, so
        # starting an unconfigured App would only fail. Say so up front.
        actions.append(Action("Start", "start_app", primary=configured, enabled=configured))
    return tuple(actions)


def sort_rows(rows: Sequence[AppRow], /) -> list[AppRow]:
    """Running first, then installed, then available; by title within a state."""
    return sorted(rows, key=lambda row: (_ORDER.get(row.state, 3), (row.name or row.app_name).casefold()))


def summary(rows: Sequence[AppRow], /) -> tuple[int, int, int]:
    """How many Apps are available, installed and running."""
    states = [row.state for row in rows]
    return states.count("available"), states.count("installed"), states.count("running")


def save_request(
    fields: Sequence[ConfigField],
    entered: Mapping[str, str],
    secrets_set: Sequence[str],
    /,
) -> dict[str, object] | list[str]:
    """What a Save sends to `configure_app`, or the required fields it still lacks.

    An empty secret is omitted, which the Hub reads as "keep what is held": a
    screen must not be able to blank a stored secret. A required field with no
    value and no held secret is named, and every such field is named at once.
    """
    values: dict[str, object] = {}
    for field in fields:
        typed = entered.get(field.name, "").strip()
        if field.type == "secret":
            if typed:
                values[field.name] = typed
            continue
        values[field.name] = typed
    missing = [
        field.name
        for field in fields
        if field.required and not entered.get(field.name, "").strip() and field.name not in secrets_set
    ]
    return missing if missing else values
```

Note the `Configure` action's `tool` is `describe_config`: pressing it opens the panel by reading the description; Save is what calls `configure_app`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/vibepy-hub/tests/test_presentation.py -q` then `make lint typecheck`.
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add packages/vibepy-hub/src/vibepy_hub/pages packages/vibepy-hub/tests/test_presentation.py
git commit -m "The board's rules are functions of Tool output, and say so without a screen"
```

---

### Task 8: The board Page

**Files:**
- Create: `packages/vibepy-hub/src/vibepy_hub/pages/board.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/entry.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/__init__.py` (docstring)
- Create: `packages/vibepy-hub/tests/test_board.py`

**Interfaces:**
- Consumes: Tools `list_apps`, `register_package_source`, `remove_package_source`, `install_app`, `remove_app`, `update_app`, `describe_config`, `configure_app`, `start_app`, `stop_app`; `presentation.row_view/sort_rows/summary/save_request`.
- Produces: `BOARD: Page` with `PageDefinition(name="board", route="/", title="Hub")`; `async def board(ctx: PageContext) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
"""The board shows Hub Core's state and acts on it through the Hub's Tools."""

from pathlib import Path

import pytest
from nicegui.testing import User

from tests_support import hub, write_wheel
from vibepy_core.adapters.nicegui import register_pages
from vibepy_core.app import page_runtime_for
from vibepy_hub.entry import APP, HUB_APP
from vibepy_hub.models import ConfigDescription


def hub_pages(root: Path):
    return page_runtime_for(HUB_APP, APP.lifespan, config={"root": str(root), "proxy_port": 8080})


async def test_the_board_shows_what_list_apps_answers(user: User, tmp_path: Path) -> None:
    source = tmp_path / "wheels"
    write_wheel(source, name="demo-app", version="1.2.3", declares=True)

    async with hub_pages(tmp_path / "hub") as pages:
        register_pages(HUB_APP, pages)
        await user.open("/")
        await user.should_see("No folder registered")

        user.find("package folder").type(str(source))
        user.find("Register").click()
        await user.should_see("demo-app")
        await user.should_see("v1.2.3")
        await user.should_see("Install")


@pytest.mark.apps("vibepy-notes")
@pytest.mark.integration
async def test_install_moves_a_row_to_installed_and_opens_its_configuration(
    user: User, installed: Path, wheelhouse: Path
) -> None:
    async with hub_pages(installed) as pages:
        register_pages(HUB_APP, pages)
        await user.open("/")
        await user.should_see("Notes")
        user.find("Configure").click()
        await user.should_see("api_base_url")
        await user.should_see("api_token")

        user.find("Save").click()
        await user.should_see("Missing required fields: api_base_url, api_token")


@pytest.mark.apps("vibepy-notes")
@pytest.mark.integration
async def test_a_saved_configuration_reaches_the_hub(
    user: User, installed: Path
) -> None:
    async with hub_pages(installed) as pages:
        register_pages(HUB_APP, pages)
        await user.open("/")
        user.find("Configure").click()
        await user.should_see("api_base_url")
        user.find("api_base_url").type("https://notes.internal")
        user.find("api_token").type("k")
        user.find("Save").click()
        await user.should_see("Notes configured")

    async with hub(installed) as tools:
        described = await tools.invoke("describe_config", {"app_name": "vibepy-notes"})

    assert isinstance(described, ConfigDescription)
    assert described.values == {"api_base_url": "https://notes.internal"}
    assert described.secrets_set == ["api_token"]
```

Notes for the implementer: `user.find(text)` matches element text, labels and placeholders (NiceGUI's `User.find` docs). Give the path input the label `"package folder"`, each config input the field name as its label, and the buttons exactly the labels above. The read-back opens a second window over the same root with `tests_support.hub`, which reads the same state file; `PageRuntime` exposes no invoker.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/vibepy-hub/tests/test_board.py -q -x 2>&1 | tail -5`
Expected: FAIL — `PageNotFoundError`/`should_see` timeout: `HUB_APP.pages` is empty, `/` is not registered.

- [ ] **Step 3: Write `board.py`**

The file's shape, which the implementer completes:

```python
"""The board: every App the Hub knows of, and what can be done to each.

A Page over Tools. It reads `list_apps` and draws; every button invokes one Tool
and redraws; a timer redraws on its own so a child that died or an action taken
elsewhere reaches the screen. The rules of what to draw are `presentation.py`'s.
"""

import logging

from nicegui import ui

from vibepy_core import Page, PageContext, PageDefinition
from vibepy_hub.models import AppListing, ConfigDescription, Diagnostic, SourceListing
from vibepy_hub.pages.presentation import Action, RowView, row_view, save_request, sort_rows, summary

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 3.0


async def board(ctx: PageContext) -> None:
    """Draw the board and keep it current."""
    open_config: dict[str, ConfigDescription] = {}
    """The one row whose configuration panel is open, keyed by app name."""
    missing: dict[str, list[str]] = {}

    async def call(name: str, payload: dict[str, object]) -> object:
        """Invoke one Tool and tell the user what it said; return the answer."""
        answer = await ctx.tools.invoke(name, payload)
        diagnostic = getattr(answer, "diagnostic", None)
        if isinstance(diagnostic, Diagnostic):
            ui.notify(f"{diagnostic.code}: {diagnostic.message}", type="warning")
        return answer

    @ui.refreshable
    async def content() -> None:
        listed = AppListing.model_validate(await ctx.tools.invoke("list_apps", {}))
        draw_summary(listed)
        draw_source(listed)
        rows = sort_rows(listed.apps)
        if not rows:
            ui.label("No apps found" if listed.source is not None else "No folder registered")
            return
        for row in rows:
            await draw_app(row_view(row, declares_fields=...), row)

    ...  # draw_summary, draw_source, draw_app, draw_config, the action handlers

    await content()
    ui.timer(REFRESH_SECONDS, content.refresh)


BOARD = Page(
    definition=PageDefinition(name="board", route="/", title="Hub"),
    handler=board,
)
```

Requirements the whole file meets, each named by a test or the spec:

1. **Source card.** Drawn from `AppListing.source`. When `None`: a `ui.input(label="package folder")` and a `Register` button; `Register` sends `{"path": input.value}` to `register_package_source`, and on success `ui.notify(f"{len(answer.candidates)} apps available from {answer.source}.")`. When set: the path as a label and an `Unregister` button that confirms through `ui.dialog` ("Unregister this package folder? The folder, installed apps, and app data will not be deleted.") and then calls `remove_package_source` with `{}`. Either way `content.refresh()` after.
2. **Rows.** For each `RowView`: title, `v{version}`; the four marks as `ui.label(f"{symbol} {label}")` with class `text-positive` when done; a `ui.button(action.label, on_click=...)` per action, `.props("flat")` unless `primary`, `.disable()` when not `enabled`; the diagnostic's code and message below when present.
3. **Actions.** `Install` → `install_app`; `Stop` → `stop_app`; `Start` → `start_app` with `{"app_name": ..., "secrets": {}}`; `Update` → `update_app`; `Uninstall` → `ui.dialog` with the text `f"Uninstall {title}? App data will be retained."` and `Cancel`/`Uninstall` buttons, then `remove_app`; `Configure` → toggles the panel: on open, `describe_config` and store in `open_config[app_name]`. Every Tool call goes through `call`, which notifies a diagnostic; on success `ui.notify(f"{title} installed."|"… is running."|"… stopped."|f"… updated to v{version}."|"… uninstalled.")`; then `content.refresh()`.
4. **Configuration panel** for the open row: for each `ConfigField` a `ui.input(label=field.name, password=field.type == "secret", placeholder="•••••••• (set)" if held else "", value=str(values.get(name, "")) if not secret else "")`; a hint line `f"{type} · required|optional"`; `Cancel` closes; `Save` builds `save_request(fields, {name: input.value}, secrets_set)`; a `list` result is shown as `f"Missing required fields: {', '.join(missing)}"` (singular `field` when one) and nothing is sent; a `dict` result is sent to `configure_app`, then `ui.notify(f"{title} configured.")`, panel closes, refresh.
5. **`declares_fields`.** `AppRow` does not carry the field list, and the board must not call
   `describe_config` for every row on every redraw. Pass `declares_fields=True` for every installed
   row: an App declaring no fields is `configured` the moment it is installed, so its Configure
   button opens a panel that says "Nothing to configure" and offers only Cancel. Start is
   enabled for it because `configured` is true. This is the one place the board departs from
   the mockup, and it departs by showing one harmless button rather than by reading N Tools.
6. **Timer.** `ui.timer(REFRESH_SECONDS, content.refresh)` once, after the first `await content()`.
7. **No business rule in this file.** Anything deciding *which* buttons or *what* a save sends lives in `presentation.py`.

Then in `entry.py`:

```python
from vibepy_hub.pages.board import BOARD
...
    pages=[BOARD],
```


`vibepy_hub/__init__.py` docstring becomes `"""The control plane for installed Vibepy Apps: Tools, and a board over them."""`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/vibepy-hub/tests/test_board.py -q` then `uv run pytest -q 2>&1 | tail -5` (the whole suite: the user plugin is now declared in two conftests, and the whole run proves that is accepted), then `make lint typecheck`.
Expected: pass. If pytest reports the plugin registered twice, remove the `pytest_plugins` line from `packages/vibepy-hub/tests/conftest.py` and instead add `"-p", "nicegui.testing.user_plugin"` to `addopts` in the root `pyproject.toml`, removing the line from `tests/conftest.py` too.

- [ ] **Step 5: See it in a browser once**

Run: `uv run python -c "import json,sys; print(json.dumps({'root': '/tmp/hub-demo', 'proxy_port': 8080}))" | uv run python -m vibepy_core.serve hub --port 8765`
Open `http://127.0.0.1:8765/` (or use the Browser pane), register the session wheelhouse path printed by `uv run pytest packages/vibepy-hub/tests/test_wheels.py -q -s` — or any folder of wheels — and click through Install → Configure → Save → Start → Stop → Uninstall once. Stop the server. This is the UI check `CLAUDE.md` asks for on UI work; nothing is committed from it.

- [ ] **Step 6: Commit**

```bash
git add -A packages/vibepy-hub
git commit -m "The Hub has a board: every App, its stage, and what can be done to it"
```

---

### Task 9: Documentation, docstring pass, gate

**Files:**
- Modify: `docs/architecture/lifecycle.md:85-97`
- Modify: `packages/vibepy-hub/src/vibepy_hub/models.py` (docstring check)
- Modify: `packages/vibepy-hub/pyproject.toml` (`description`)

- [ ] **Step 1: `lifecycle.md`**

Replace "Eight exist, as the Hub declares them." with "Ten exist, as the Hub declares them." and the table with:

```markdown
| Tools | What they act on |
| --- | --- |
| `register_package_source`, `remove_package_source` | the one folder of wheels the Hub installs from |
| `list_apps` | what is offered, what is installed, what is running, and what is newer |
| `install_app`, `update_app`, `remove_app` | an environment of its own per App: created, remade at a newer version, destroyed |
| `describe_config`, `configure_app` | the values an App runs with, read and written |
| `start_app`, `stop_app` | the Web channel window of an installed App |
```

After the table add one paragraph:

```markdown
An update keeps what the Hub holds for an App — its configuration values, its port, its route —
and remakes only the environment. A running App is refused rather than restarted.

The Hub's Web channel is one Page, `board` at `/`, over these Tools and nothing else: it reads
`list_apps` and redraws on a timer, so what it shows is Hub Core's state rather than the last thing
that tab did.
```

- [ ] **Step 2: `pyproject.toml` description**

`description = "Control plane for installed Vibepy Apps, with a board over it"`.

- [ ] **Step 3: Docstring pass**

Read every file touched in Tasks 2–8 once, top to bottom. Each module docstring says what the module is and, where not obvious, why it is shaped so; each public function's says what it returns and the one thing a caller would get wrong. Remove any comment that restates the code. Do not touch files this milestone did not change.

- [ ] **Step 4: Gate**

Run: `make lint typecheck test`
Expected: clean. Paste the last lines of the test summary into the commit message body if anything is notable (durations that grew, for instance).

- [ ] **Step 5: Commit**

```bash
git add docs/architecture/lifecycle.md packages/vibepy-hub
git commit -m "Lifecycle names the Hub's ten Tools and its board"
```

---

### Task 10: Review rounds and merge

- [ ] **Step 1: Review round one** — `superpowers:requesting-code-review` over `git diff main...m11-hub-ui`, against `docs/milestones/M11/spec.md`. Fix findings in place, commit each as its own sentence.
- [ ] **Step 2: Review round two** — cross-check the branch against what the milestone was *for*: the three acceptance bullets in `docs/roadmap.md` M11 and the mockup. For each bullet, name the test that proves it. Any bullet without one gets a test.
- [ ] **Step 3: Integrate** — `superpowers:finishing-a-development-branch`: `git checkout main && git merge --no-ff m11-hub-ui -m "Merge: the Hub has a board, and Hub Core what a board needs"`, delete the branch, then promote what is still true out of `docs/milestones/M11/` (the lifecycle paragraph already carries it) and delete the folder, mockup included, in one commit: "Retire the M11 milestone folder: its record is the suite and the merge".
- [ ] **Step 4: Push and read CI** — `git push`, then watch the run on macOS and Windows with `gh run watch`. The push is not done until both are green. The owner's `docs/roadmap.md` edit and the AGENTS.md commits on main ride along.
