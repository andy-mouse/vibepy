# T1 - What a test may build implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build each fixture App's environment once a session through the real `install_app`, hand
every test that needs one a copy of the whole Hub root, and name the tests that cross into a real
distribution or child.

**Architecture:** `conftest.py` gains one session fixture, `template_root`, which opens a Hub window
over a `tmp_path_factory` directory, registers `fixtures/` and installs `vibepy-notes`,
`vibepy-todo` and `vibepy-timer` like any caller. One function fixture, `installed`, hardlinks that
root into the test's `tmp_path` and rewrites the one absolute path the Hub recorded inside it. The
existing `_build`, `_place`, `notes_template`, `todo_template`, `notes_installed` and
`two_installed` are deleted. Every test that called `install_app` without installing being its
subject takes `installed` instead; the rest keep their install. A registered `integration` marker
names every test that builds an environment or starts a child, and excuses none of them.

**Tech Stack:** pytest 8 with `asyncio_mode = "auto"`, `tmp_path_factory`, `shutil.copytree` with
`os.link`; ruff + pyright strict; the Hub's own Tools through `tests_support.hub`.

## Global Constraints

- The spec is `docs/milestones/T1/spec.md`. Its acceptance criteria are the tests.
- The branch is `t1-what-a-test-may-build`, already cut from `main`. Do not push.
- `make lint typecheck test` passes at the end of every task. 252 tests pass at the start, 252 at
  the end; none skipped, none deselected. Run tests with `uv run pytest`; the Hub's tests live in
  `packages/vibepy-hub/tests/`.
- No test's assertions change. Only how an installed App got there changes. A test that passes
  with its assertion inverted has lost its subject and is restored.
- No timeout raised, no poll widened, no `# noqa`, no per-file-ignore added, no marker used to skip.
- `conftest.py` calls none of `vibepy_hub.internals.installer`'s functions. It may read
  `FACTS_FILE`, the name of the file whose `purelib` it relocates.
- The Hub's public surface and the three fixture Apps do not change. `--durations=15` stays.
- Blocking calls inside `async def` go through `asyncio.to_thread`. Filesystem paths are `Path`.
- Docstrings satisfy PEP 257; the `D` rules are on and `make lint` enforces them.

---

### Task 1: One template root a session, one copy a test

The fixture the rest of the stage stands on. It replaces the per-App templates with one Hub root
built by `install_app`, and migrates the eight tests that used `notes_installed` and
`two_installed` so the old fixtures can go in the same commit.

**Files:**
- Modify: `packages/vibepy-hub/tests/conftest.py` (rewrite; ~120 lines today)
- Modify: `packages/vibepy-hub/tests/test_configuration.py:16-70` (four tests take `installed`)
- Modify: `packages/vibepy-hub/tests/test_installation.py:50-61` and the
  `test_an_environment_that_no_longer_declares_its_app_says_so` test (take `installed`)
- Modify: `packages/vibepy-hub/tests/test_state.py:14` (takes `installed`)

**Interfaces:**
- Consumes: `tests_support.hub(root, *, proxy_port=8080)`, `tests_support.FIXTURES`.
- Produces: fixture `installed: Path` — a Hub root, unique to the test, in which `vibepy-notes`,
  `vibepy-todo` and `vibepy-timer` are installed with ports allocated and routes written, and
  nothing is configured or running. Later tasks depend on exactly that state.

- [ ] **Step 1: Rewrite `conftest.py`**

Replace the whole file with:

```python
"""What the Hub's tests are given, and how often each of it is built.

pytest's guidance is that a resource which is expensive to build belongs to a
broader scope than the test that uses it, and that `tmp_path_factory` is where
a session-scoped one lives
(<https://docs.pytest.org/en/stable/how-to/fixtures.html>,
<https://docs.pytest.org/en/stable/how-to/tmp_path.html>). pip's own suite
applies that guidance to virtual environments: one is built a session and each
test is handed a copy of it, with nothing inside rewritten
(<https://github.com/pypa/pip/blob/main/tests/lib/venv.py>).

Here the expensive resource is a Hub root with the fixture Apps installed. It
is built once, by the same `install_app` a user calls, so what a test is handed
is what installing produces and not a second construction that could drift.
Each test receives a hardlinked copy: the same inodes, so nothing is assessed
or compiled a second time.

Two things in a root name the root's own path. `traefik.yml` is rewritten by
the Hub every time a window opens, so a copy is corrected the moment a test
opens it. Each environment's facts file records `purelib` as an absolute path,
and that one the copy rewrites. An environment's `pyvenv.cfg` records the base
interpreter, which is outside the root and does not move; the Hub reaches an
environment only through its interpreter and `-m`, so no installed script's
shebang is ever read.

A test whose subject *is* installing takes none of this. It drives
`install_app` like any caller, because that is the thing it is testing.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

from tests_support import FIXTURES, hub
from vibepy_hub.internals.installer import FACTS_FILE

APPS = ("vibepy-notes", "vibepy-todo", "vibepy-timer")
"""Every fixture App, installed into the template in this order."""


@pytest.fixture(scope="session")
def template_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a Hub root with every fixture App installed, once for the session.

    Built through the Hub's own Tools rather than the installer's functions, so
    the root holds exactly what a user's install leaves: environments, facts,
    state with a port per App, and a route per App declaring Pages.
    """
    root = tmp_path_factory.mktemp("template") / "hub"

    async def build() -> None:
        async with hub(root) as tools:
            await tools.invoke("register_package_source", {"path": str(FIXTURES)})
            for app_name in APPS:
                installed = await tools.invoke("install_app", {"app_name": app_name})
                diagnostic = getattr(installed, "diagnostic", None)
                assert diagnostic is None, diagnostic

    asyncio.run(build())
    return root


@pytest.fixture
def installed(tmp_path: Path, template_root: Path) -> Path:
    """Give one test its own copy of the template root.

    Hardlinked rather than copied: the bytes are already on the disk and
    already assessed, and a second inode for each would be the cost the
    template exists to avoid. The only thing rewritten is the one path the Hub
    recorded inside the root, each environment's `purelib`.
    """
    root = tmp_path / "hub"
    shutil.copytree(template_root, root, copy_function=os.link)
    for recorded in root.glob(f"envs/*/{FACTS_FILE}"):
        facts = json.loads(recorded.read_text(encoding="utf-8"))
        facts["purelib"] = str(root / Path(facts["purelib"]).relative_to(template_root))
        # Unlinked first: every file here is a hardlink to the template's, and
        # writing through this name would write the template too.
        recorded.unlink()
        recorded.write_text(json.dumps(facts, indent=1), encoding="utf-8")
    return root
```

- [ ] **Step 2: Check the fixture's claims against the Hub before relying on them**

```bash
grep -n "write_install_config" packages/vibepy-hub/src/vibepy_hub/entry.py
grep -n "purelib" packages/vibepy-hub/src/vibepy_hub/internals/installer.py packages/vibepy-hub/src/vibepy_hub/models.py
grep -n "str(root" packages/vibepy-hub/src/vibepy_hub/internals/*.py
```

Expected: `write_install_config` runs inside `hub_lifespan` (so `traefik.yml` is regenerated per
window); `purelib` is recorded as an absolute `Path` in the facts; the only other `str(root …)` is
the routes directory in `traefik.yml`. If a third root-relative absolute path is recorded anywhere,
stop and report it — the copy would have to rewrite it too and the spec does not know about it.

Then the hardlinks' one hazard — a write through a linked name reaches the template too:

```bash
grep -rn "write_whole\|os.replace\|write_text\|\.open(" packages/vibepy-hub/src/vibepy_hub/internals/*.py
```

Expected: state, routes and configuration are written by `write_whole`, which stages and
`os.replace`s — a new inode, so the template is never written through. The one in-place
`write_text` is the facts file during `install`, which only runs into an environment the test
itself creates, and `remove_app`'s `rmtree` unlinks names rather than truncating files.
Directories are real in a `copytree`; only files are links. If any write under a root opens a
linked file for writing in place, stop and report it.

- [ ] **Step 3: Migrate the eight tests off the old fixtures**

In `test_configuration.py`, `test_installation.py` and `test_state.py`, replace the parameter
`notes_installed: Path` or `two_installed: Path` with `installed: Path`, and every use of that name
in the body with `installed`. The Apps those tests reach for — `vibepy-notes`, and for
`test_two_overlapping_configurations_both_survive` also `vibepy-todo` — are in the copy.

One test needs a judgment: `test_an_installed_app_is_listed_apart_from_an_offered_one` asserts
`rows["vibepy-timer"].state == "available"`, and in the copy `vibepy-timer` is installed. Its
subject is that an installed row and an offered row are distinguishable, so it keeps that subject
by removing one first:

```python
async def test_an_installed_app_is_listed_apart_from_an_offered_one(installed: Path) -> None:
    async with hub(installed) as tools:
        await tools.invoke("remove_app", {"app_name": "vibepy-timer"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["vibepy-notes"].state == "installed"
    assert rows["vibepy-timer"].state == "available"
```

`register_package_source` is no longer needed there: the template registered `fixtures/` and the
copy carries that state.

- [ ] **Step 4: Run the migrated files**

```bash
uv run pytest packages/vibepy-hub/tests/test_configuration.py packages/vibepy-hub/tests/test_installation.py packages/vibepy-hub/tests/test_state.py -q
```

Expected: all pass. A failure naming `purelib` or a path under `template` means Step 1's rewrite
missed a facts file; a failure in `test_what_is_held_is_readable_only_by_its_owner` on macOS means
the copy changed a file mode, which hardlinks do not — investigate before touching the test.

- [ ] **Step 5: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests. `conftest.py` no longer imports `describe`, `install`, `purelib` or
`write_facts`; ruff's F401 would report them if any stayed.

- [ ] **Step 6: Commit**

```bash
git add packages/vibepy-hub/tests/conftest.py packages/vibepy-hub/tests/test_configuration.py packages/vibepy-hub/tests/test_installation.py packages/vibepy-hub/tests/test_state.py
git commit -m "Build one Hub root a session, through install_app, and copy it per test"
```

---

### Task 2: The runtime tests take the copy

Seven tests in `test_runtime.py`; five install `vibepy-todo`, one installs `vibepy-notes`, one
installs nothing. Starting is their subject and installing is their arrangement, so all six take
the copy.

**Files:**
- Modify: `packages/vibepy-hub/tests/test_runtime.py`

**Interfaces:**
- Consumes: `installed: Path` from Task 1.
- Produces: nothing.

- [ ] **Step 1: Convert each installing test**

For every test that has `root = tmp_path / "hub"` followed by `register_package_source` and
`install_app`: take `installed: Path` in place of (or in addition to, where `tmp_path` is still used
for a database path) `tmp_path`, open `hub(installed)`, and delete the two invocations. The
configure/start/stop calls and every assertion stay. Example, from:

```python
async def test_starting_a_running_app_says_it_is_already_running(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(FIXTURES)})
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
```

to:

```python
async def test_starting_a_running_app_says_it_is_already_running(
    tmp_path: Path, installed: Path
) -> None:
    async with hub(installed) as tools:
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
            },
        )
        await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        again = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
```

`test_starting_an_app_that_is_not_installed_is_a_diagnostic` installs nothing and stays as it is.
If `FIXTURES` is no longer referenced in the module, drop the import; ruff will say so.

- [ ] **Step 2: Prove each converted test still fails for its own reason**

For each converted test, temporarily invert its decisive assertion — for the example above,
`assert again.diagnostic is None` — and run that test alone:

```bash
uv run pytest packages/vibepy-hub/tests/test_runtime.py::test_starting_a_running_app_says_it_is_already_running -q
```

Expected: FAIL on the inverted assertion. Restore the assertion. A test that passes inverted has
lost its subject: restore its original arrangement (the install) and report it.

- [ ] **Step 3: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests.

- [ ] **Step 4: Commit**

```bash
git add packages/vibepy-hub/tests/test_runtime.py
git commit -m "Start Apps from the copied root rather than installing one per test"
```

---

### Task 3: The address tests are judged one by one

Nine tests in `test_addresses.py`. Here the line between subject and arrangement runs through the
file: an address *arises from* installing, so some of these tests are about installing and keep it.

**Files:**
- Modify: `packages/vibepy-hub/tests/test_addresses.py`

**Interfaces:**
- Consumes: `installed: Path` from Task 1.
- Produces: nothing.

- [ ] **Step 1: Apply the rule to each test**

| Test | Subject | Arrangement |
| --- | --- | --- |
| `test_an_address_names_the_app_and_the_proxy` | the address form | no Hub; unchanged |
| `test_installing_gives_an_app_an_address_before_it_is_started` | installing allocates | keeps `install_app` |
| `test_two_apps_hold_two_ports_and_removing_one_releases_it` | allocation and release | keeps both installs |
| `test_installing_an_installed_app_is_refused` | a second install is refused | keeps the first install; the copy would also serve, but the refusal is about the install path and the test reads clearer driving it |
| `test_installing_writes_a_route_and_removing_deletes_it` | install writes, remove deletes | keeps `install_app` |
| `test_the_window_writes_a_configuration_that_apps_do_not_change` | the window's `traefik.yml` | takes `installed` |
| `test_an_address_outlives_a_run` | the port survives stop | takes `installed` |
| `test_an_app_with_no_pages_gets_no_address` | no Pages, no url | takes `installed`; `vibepy-notes` is in the copy with `url` absent |
| `test_an_installed_app_holding_no_port_is_told_to_install_it_again` | state with no port | takes `installed`, then its existing `write_state(..., ports={})` step |

Convert the four that take the copy as in Task 2. For the last one, the copy already holds a port
for `vibepy-todo`; the test's own `write_state` removes it, which is the state it exists to test.

- [ ] **Step 2: Prove each converted test still fails for its own reason**

Invert the decisive assertion of each of the four converted tests in turn, run it alone, see it
fail, restore it. For `test_an_address_outlives_a_run` the decisive assertion is
`assert second.url == first.url`.

- [ ] **Step 3: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests.

- [ ] **Step 4: Commit**

```bash
git add packages/vibepy-hub/tests/test_addresses.py
git commit -m "Let the address tests install only where installing is what they test"
```

---

### Task 4: Installation, proxy and package-source tests

`test_installation.py` is where installing is the subject and keeps most of its installs.
`test_proxy.py`'s subject is the proxy; its three installs are arrangement. `test_package_sources.py`
installs to prove a refusal, which is the install path.

**Files:**
- Modify: `packages/vibepy-hub/tests/test_installation.py`
- Modify: `packages/vibepy-hub/tests/test_proxy.py`
- Read: `packages/vibepy-hub/tests/test_package_sources.py` (expected unchanged)

**Interfaces:**
- Consumes: `installed: Path` from Task 1.
- Produces: nothing.

- [ ] **Step 1: `test_installation.py`**

Every test whose name says installing, removing, a folder, a spelling or a failed description keeps
its `install_app`. Two do not:

- `test_an_app_is_started_by_the_name_it_declares` — its subject is that the Hub *runs* an App
  under its declared name; installing is arrangement. Takes `installed`.
- `test_removing_an_app_deletes_its_environment_and_leaves_its_data` — removing is the subject, and
  the copy has the App installed. Takes `installed` and calls `remove_app`; keep every assertion
  about what remains.

- [ ] **Step 2: `test_proxy.py`**

Both tests take `installed` and drop their `register_package_source` and `install_app` calls. They
open `hub(installed, proxy_port=proxy_port)` with the port they already choose; the address is
derived from the window's proxy port, not stored, so a copy built at 8080 answers at whatever port
the test opens it with. Verify that claim before relying on it:

```bash
grep -n "proxy_port" packages/vibepy-hub/src/vibepy_hub/internals/routing.py packages/vibepy-hub/src/vibepy_hub/models.py packages/vibepy-hub/src/vibepy_hub/tools/installation.py
```

Expected: the proxy port is read from the window's `HubDeps` when an address is formed, and does
not appear in `state.json` or a route file. If a route file records it, stop and report: the copy
would then carry the template's 8080 into a test that opened a different port.

- [ ] **Step 3: `test_package_sources.py`**

`test_two_sources_offering_one_name_is_refused_rather_than_ordered` installs to prove the refusal;
that is the install path. Unchanged.

- [ ] **Step 4: Prove each converted test still fails for its own reason**

Invert and restore, one test at a time, for the two `test_installation.py` conversions and both
proxy tests. The proxy tests take longest; run each alone.

- [ ] **Step 5: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests. Read the `--durations=15` block: the proxy tests should have dropped by
roughly one install each.

- [ ] **Step 6: Commit**

```bash
git add packages/vibepy-hub/tests/test_installation.py packages/vibepy-hub/tests/test_proxy.py
git commit -m "Install in the installation tests, and nowhere the subject is something else"
```

---

### Task 5: The `integration` marker

Registered, strict, and applied to every test that builds an environment or starts a child. It
selects and never excuses.

**Files:**
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]`)
- Modify: `packages/vibepy-hub/tests/conftest.py` (module-level marking, see Step 2)
- Modify: whichever files under `tests/` Step 3 finds

**Interfaces:**
- Consumes: nothing.
- Produces: the marker later readers select with `-m integration`.

- [ ] **Step 1: Register it**

In `pyproject.toml`, under `[tool.pytest.ini_options]`, add:

```toml
# `integration` names the tests whose subject crosses into a real distribution
# or a real child process -- the ones that build an environment or start an
# App. It selects and never excuses: `make test` runs everything. Strict, so a
# mistyped marker fails rather than marking nothing.
# <https://docs.pytest.org/en/stable/example/markers.html>
markers = [
    "integration: crosses into a real distribution or child process",
]
strict_markers = true
```

Run `uv run pytest --collect-only -q | tail -1` — expected `252 tests collected`, no warning about
an unknown marker (there are none yet).

- [ ] **Step 2: Mark the Hub tests**

Every test that takes `installed`, calls `install_app`, or calls `start_app` crosses the boundary.
That is every test in `test_addresses.py`, `test_configuration.py`, `test_installation.py`,
`test_proxy.py`, `test_runtime.py`, `test_state.py` and `test_package_sources.py` except the ones
that build nothing: `test_an_address_names_the_app_and_the_proxy`,
`test_configuring_an_app_that_is_not_installed_is_a_diagnostic`,
`test_starting_an_app_that_is_not_installed_is_a_diagnostic`,
`test_stopping_an_app_that_is_not_running_is_a_diagnostic`, and whatever else installs nothing —
check each with `grep -n "installed\|install_app\|start_app"` on the test's body rather than by its
name.

Mark per test with `@pytest.mark.integration`, not per module: a module-level `pytestmark` would
mark the tests that build nothing, and the point of the marker is that it is exact.
`test_processes.py` and `test_no_blocking_handlers.py` start no child and build nothing; unmarked.

- [ ] **Step 3: Check the framework's own tests**

```bash
grep -ln "subprocess\|create_subprocess\|uv sync\|uv venv" tests/*.py
```

Expected: `test_channel_extras.py` (runs `uv sync` into a temp environment), `test_describe_command.py`
and `test_serve_command.py` (run a child interpreter), `test_channel_neutrality.py` (check what it
runs). Each test that actually spawns a process or builds an environment gets the marker; a test
that only imports `subprocess` for a type does not.

- [ ] **Step 4: Prove the marker selects and excuses nothing**

```bash
uv run pytest -m "not integration" -q --durations=5
uv run pytest -m integration -q --durations=5 | tail -3
uv run pytest -q | tail -1
```

Expected: the first completes in well under a minute and its slowest test is not a Hub test that
starts anything; the second is where the time is; the third still says `252 passed`. If the first
run shows a test that builds an environment, that test is missing its marker.

- [ ] **Step 5: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml packages/vibepy-hub/tests tests
git commit -m "Name the tests that cross into a real distribution or child"
```

---

### Task 6: Leave nothing behind but the answer

The benchmark did its work and its numbers are in the spec.

**Files:**
- Delete on `bench-hub-cost` only — nothing on this branch holds them. Verify:

```bash
git ls-files scripts/bench_hub.py .github/workflows/bench.yml
```

Expected: no output on `t1-what-a-test-may-build`. If either file is tracked here, `git rm` it and
commit "Remove the benchmark whose numbers the spec now carries".

- [ ] **Step 1: Delete the branch locally**

```bash
git branch -D bench-hub-cost
```

The remote branch `origin/bench-hub-cost` is the owner's to delete; say so in the final report
rather than pushing a deletion.

- [ ] **Step 2: Whole-stage verification**

```bash
make lint typecheck test 2>&1 | tail -20
grep -rn "notes_installed\|two_installed\|_place\|_build\|notes_template\|todo_template" packages/vibepy-hub/tests
grep -rn "install_app" packages/vibepy-hub/tests/*.py | grep -v test_installation.py | grep -v test_addresses.py | grep -v test_package_sources.py | grep -v conftest.py
```

Expected: gate green, 252; the second grep is empty; the third is empty — every remaining
`install_app` outside conftest is in a file whose subject is installing or an address arising from
it.

Then read the `--durations=15` block from that run and record it in the report file: it is the
local before/after, and the Windows number comes only from CI after merge.

---

### Task 7: The copy holds what the test names

Tasks 1-5 gave every copy all three Apps, and the spec's "What the first execution measured"
records what that cost: 3.50s a copy, twenty-one times, and a local gate slower than before the
stage. This task makes the copy hold only the Apps a test names and removes the rest through the
Hub's own `remove_app`, per the spec's decision "The copy holds the Apps the test names".

**Files:**
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]`, `markers`)
- Modify: `packages/vibepy-hub/tests/conftest.py`
- Modify: every test taking `installed` in `packages/vibepy-hub/tests/test_addresses.py`,
  `test_configuration.py`, `test_installation.py`, `test_proxy.py`, `test_runtime.py`,
  `test_state.py`

**Interfaces:**
- Consumes: `installed: Path`, `template_root`, `APPS` from Task 1; `hub` from `tests_support`.
- Produces: the `apps` marker every copy-taking test carries.

- [ ] **Step 1: Register the marker**

In `pyproject.toml`, extend `markers` so it reads:

```toml
markers = [
    "integration: crosses into a real distribution or child process",
    "apps(*names): the fixture Apps a test's copy of the template root holds",
]
```

- [ ] **Step 2: The fixture reads the marker and prunes the copy**

Replace the `installed` fixture in `conftest.py` with this one. The docstring's claims are the
spec's; keep them true.

```python
@pytest.fixture
def installed(request: pytest.FixtureRequest, tmp_path: Path, template_root: Path) -> Path:
    """Give one test its own copy of the template root, holding the Apps it names.

    A test says which Apps it needs with `@pytest.mark.apps("vibepy-todo")`, the
    way pytest's guide has a fixture read a test's data from its marker. Only
    those Apps' environments are linked -- a copy has the same unit of cost as
    an install, entries created, and a test that needs one App must not pay for
    three. The Apps left out are then removed through `remove_app`, so the
    copy's state, ports and routes agree with its `envs/` directory. A test
    that names nothing gets nothing: a copy whose contents nobody chose is
    what the spec measured at 3.5s.

    Hardlinked rather than copied: the bytes are already on the disk and
    already assessed, and a second inode for each would be the cost the
    template exists to avoid. The only thing rewritten is the one path the Hub
    recorded inside the root, each environment's `purelib`.
    """
    marker = request.node.get_closest_marker("apps")
    assert marker is not None, "a test taking `installed` names its Apps with @pytest.mark.apps"
    named = frozenset(marker.args)
    unknown = named - frozenset(APPS)
    assert not unknown, f"not fixture Apps: {sorted(unknown)}"

    def leave_out(directory: str, names: list[str]) -> list[str]:
        if Path(directory) != template_root / "envs":
            return []
        return [name for name in names if name not in named]

    root = tmp_path / "hub"
    shutil.copytree(template_root, root, copy_function=os.link, ignore=leave_out)
    for recorded in root.glob(f"envs/*/{FACTS_FILE}"):
        facts = json.loads(recorded.read_text(encoding="utf-8"))
        facts["purelib"] = str(root / Path(facts["purelib"]).relative_to(template_root))
        # Unlinked first: every file here is a hardlink to the template's, and
        # writing through this name would write the template too.
        recorded.unlink()
        recorded.write_text(json.dumps(facts, indent=1), encoding="utf-8")

    async def prune() -> None:
        async with hub(root) as tools:
            for app_name in APPS:
                if app_name not in named:
                    await tools.invoke("remove_app", {"app_name": app_name})

    asyncio.run(prune())
    return root
```

- [ ] **Step 3: Every copy-taking test names its Apps**

For each test that takes `installed`, read its body and add `@pytest.mark.apps(...)` naming
exactly the Apps it uses -- the ones it starts, configures, asks the address of, removes, or
asserts a fact about. Rules:

- an App the test asserts is *available* or *absent* (`test_an_installed_app_is_listed_apart_from_an_offered_one`
  removes `vibepy-timer` to show it offered) is not named; the test's own `remove_app` call for
  that purpose is then deleted, because the fixture already did it, and the assertion stays
- an App the test asserts `has_pages is False` about (`vibepy-notes`) is named, because the fact
  is read from a row of an installed App
- a test that needs two Apps names two; the proxy test serving two Apps names both
- the marker goes on the test beside `@pytest.mark.integration`

Then convert `test_configuration.py::test_a_secret_is_held_so_a_restart_needs_no_one`, which
Task 1 left installing: its subject is that a held secret survives a window, not installing. It
takes `installed`, names `vibepy-todo`, and both its windows open over `installed`; its assertions
are untouched.

- [ ] **Step 4: Prove the marker is required and exact**

Write no test for this; prove it once by hand and record it in the report: remove the marker from
one test, run that test alone, see the fixture's assertion fail with its message, restore it. Then
misspell one as `@pytest.mark.app(...)`, run, see `strict_markers` fail collection, restore.

- [ ] **Step 5: Prove each converted test still fails for its own reason**

For `test_a_secret_is_held_so_a_restart_needs_no_one` and
`test_an_installed_app_is_listed_apart_from_an_offered_one`, invert the decisive assertion, run
alone, see it fail, restore.

- [ ] **Step 6: Run the gate and read the durations**

Run: `make lint typecheck test`
Expected: pass, 252 tests; in the `--durations=15` block no `setup` line above about 1.7s on
macOS, and the total below the 169s the spec records. Paste the block into the report.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml packages/vibepy-hub/tests
git commit -m "Hand a test a copy of the Apps it names, and no other"
```

---

## Verification at merge

The last acceptance criterion is read from CI, not from a laptop. After the merge to `main` is
pushed, read the run's Windows job: its `make test` total against 400s, and its `--durations=15`
list. Both are reported to the owner against the spec's baseline, per Scope item 5; the merge
commit message states what was changed and why, and cannot carry a number that exists only after it
is pushed.
