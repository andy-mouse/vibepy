# L1 Workspace Layout and Channel Extras Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the repository to the workspace layout uv documents, rename the core distribution
to `vibepy-core`, and make each channel's SDK an extra of it, changing no behaviour.

**Architecture:** The workspace root stays the core distribution, as uv's documented layout has
it, and gains `packages/vibepy-hub` and `examples/{todo,notes}` as members. The core's
dependencies shrink to `pydantic`, with `[web]` and `[agent]` extras that each consumer declares
according to the channels it offers. The checks are named once, in the Makefile, and CI invokes
it.

**Tech Stack:** Python 3.12, uv workspaces, hatchling, ruff, pyright (strict), pytest.

**Read first:** `docs/milestones/L1/spec.md`. Its Sources table is where every contract below
comes from; this plan does not restate the reasoning.

## Global Constraints

- the suite is 152 tests before and after, with the same results. A changed count is a failure of
  this stage, not a discovery
- no file under `src/` changes except its imports and the paths in its docstrings, with one
  exception: `serve.py`'s `argparse` `prog` becomes `vibepy_core.serve`
- the entry-point group stays `vibepy.apps`, in code, in tests and in documents
- `APP_GROUP = "vibepy.apps"` in `src/vibepy_core/app/package.py` and
  `packages/vibepy-hub/src/vibepy_hub/internals/projects.py` keeps its value
- no compatibility shim for the `vibepy` import package. It was never published
- `vibepy-builder` is not created
- `Any` and `cast` stay out; paths stay `pathlib.Path`; `logging` only
- a task is done when `make lint typecheck test` passes, and each task ends in a commit
- do not edit `docs/roadmap.md`, `docs/milestones/code-review-roadmap.md`, or
  `docs/milestones/code-review/`

---

### Task 1: Rename the core distribution and its import package

`vibepy` becomes `vibepy_core` and `vibepy-framework` becomes `vibepy-core`, everywhere at once.
Nothing imports successfully in between, so this is one commit.

**Files:**
- Move: `src/vibepy/` → `src/vibepy_core/`
- Modify: `pyproject.toml` (`[project] name`, `[tool.hatch.build.targets.wheel] packages`,
  `[dependency-groups] dev`, `[tool.uv.sources]`)
- Modify: `hub/pyproject.toml`, `samples/todo/pyproject.toml`, `samples/notes/pyproject.toml`
  (dependency name and source key)
- Modify: every `.py` under `src/`, `tests/`, `hub/`, `samples/` that names `vibepy`
- Modify: `src/vibepy_core/serve.py:85` (`prog`), `src/vibepy_core/app/package.py:66` (docstring
  path)
- Modify: `hub/src/vibepy_hub/internals/processes.py:159`,
  `hub/src/vibepy_hub/internals/installer.py:101`, `:105` (command strings)
- Modify: `tests/test_mcp_adapter.py:313`, `tests/test_nicegui_adapter.py:150` (guard paths)
- Modify: `tests/test_serve_command.py:52`, `:69`, `:87`, `tests/test_describe_command.py:20`
  (command strings)

**Interfaces:**
- Consumes: nothing.
- Produces: import package `vibepy_core`; distribution `vibepy-core`; commands
  `python -m vibepy_core.serve` and `python -m vibepy_core.describe`. Tasks 2 to 5 use these
  names.

- [ ] **Step 1: Move the package**

```bash
git mv src/vibepy src/vibepy_core
```

- [ ] **Step 2: Rewrite every reference to the import package**

`vibepy_hub` must not be caught by a substitution on `vibepy`, so the module-name boundary is
part of each pattern. Run from the repository root:

```bash
python3 - <<'PY'
import re
from pathlib import Path

roots = [Path("src"), Path("tests"), Path("hub"), Path("samples")]
files = [p for root in roots for p in root.rglob("*.py") if "__pycache__" not in p.parts]
patterns = [
    (re.compile(r"\bfrom vibepy(?=[. ])"), "from vibepy_core"),
    (re.compile(r"\bimport vibepy(?=[. \n])"), "import vibepy_core"),
    (re.compile(r"\bvibepy\.(serve|describe)\b"), r"vibepy_core.\1"),
    (re.compile(r"src/vibepy\b"), "src/vibepy_core"),
    (re.compile(r'"src", "vibepy"'), '"src", "vibepy_core"'),
]
for path in files:
    text = original = path.read_text(encoding="utf-8")
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        print(path)
PY
```

- [ ] **Step 3: Check that the entry-point group survived**

`"vibepy.apps"` is a value, not a module path, and the third pattern above only matches `serve`
and `describe`. Prove it:

```bash
grep -rn '"vibepy\.apps"' --include='*.py' src tests hub samples
```

Expected: three lines — `src/vibepy_core/app/package.py`,
`hub/src/vibepy_hub/internals/projects.py`, `hub/tests/tests_support.py`. If any reads
`vibepy_core.apps`, revert it.

- [ ] **Step 4: Rename the distribution in the four project files**

In `pyproject.toml`: `name = "vibepy-core"`, `packages = ["src/vibepy_core"]`, and in
`[dependency-groups]`/`[tool.uv.sources]` nothing about the core changes because the core is the
root. In `hub/pyproject.toml`, `samples/todo/pyproject.toml` and `samples/notes/pyproject.toml`:

```toml
dependencies = ["vibepy-core"]

[tool.uv.sources]
vibepy-core = { workspace = true }
```

Task 3 replaces those `dependencies` lines with the extras. Leave them plain here.

- [ ] **Step 5: Fix `prog` and the remaining strings by hand**

```bash
grep -rn 'vibepy\.' --include='*.py' src tests hub samples | grep -v 'vibepy\.apps'
```

Expected: no output. `src/vibepy_core/serve.py:85` must read
`argparse.ArgumentParser(prog="vibepy_core.serve")`.

- [ ] **Step 6: Update the tool configuration that names the package**

`pyproject.toml`'s `[tool.ruff] src` and `[tool.pyright] include` name `src`, not the package, so
they need no change here. Confirm:

```bash
grep -n 'vibepy' pyproject.toml
```

Expected: only `name = "vibepy-core"`, the wheel `packages` line, and the workspace
`vibepy-hub`/`vibepy-todo`/`vibepy-notes` entries.

- [ ] **Step 7: Re-lock and re-sync**

```bash
uv lock && uv sync
```

Expected: the lock updates the root package's name; no dependency version changes.

- [ ] **Step 8: Run the suite**

```bash
make lint typecheck test
```

Expected: 152 passed, ruff and pyright clean.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "Rename the core distribution to vibepy-core"
```

---

### Task 2: Move to the workspace layout uv documents

The root stays `vibepy-core`; the Hub and the examples move under it.

**Files:**
- Move: `hub/` → `packages/vibepy-hub/`
- Move: `samples/todo/` → `examples/todo/`, `samples/notes/` → `examples/notes/`
- Modify: `pyproject.toml` (`[tool.uv.workspace] members`, `[tool.ruff] src`,
  `[tool.pyright] include`, `[tool.pytest.ini_options] testpaths`)
- Modify: `packages/vibepy-hub/tests/tests_support.py:13-14` (`REPO`, `SAMPLES`)
- Modify: `packages/vibepy-hub/tests/test_configuration.py`, `test_installation.py`,
  `test_runtime.py` (the imported constant's name)
- Modify: `Makefile` (the lint and format paths)

**Interfaces:**
- Consumes: the names Task 1 produced.
- Produces: `packages/vibepy-hub/`, `examples/todo/`, `examples/notes/`; the Hub tests' constant
  `EXAMPLES`. Task 3's test reads `examples/notes` by distribution name, not by path.

- [ ] **Step 1: Move the directories**

```bash
mkdir -p packages examples
git mv hub packages/vibepy-hub
git mv samples/todo examples/todo
git mv samples/notes examples/notes
rmdir samples
```

- [ ] **Step 2: Point the workspace and the tools at the new places**

In `pyproject.toml`:

```toml
[tool.uv.workspace]
members = ["packages/*", "examples/*"]

[tool.ruff]
line-length = 100
src = [
    "src",
    "tests",
    "packages/vibepy-hub/src",
    "packages/vibepy-hub/tests",
    "examples/todo/src",
    "examples/notes/src",
]

[tool.pyright]
include = [
    "src",
    "tests",
    "packages/vibepy-hub/src",
    "packages/vibepy-hub/tests",
    "examples/todo/src",
    "examples/notes/src",
]
pythonVersion = "3.12"
typeCheckingMode = "strict"

[tool.pytest.ini_options]
testpaths = ["tests", "packages/vibepy-hub/tests"]
```

Leave `asyncio_mode` and the `main_file` comment exactly as they are.

- [ ] **Step 3: Fix the Hub tests' repository-relative constants**

`packages/vibepy-hub/tests/tests_support.py` is one directory deeper and the samples have a new
name and place. Replace lines 13-14 with:

```python
REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "examples"
```

Then rename the constant at its three call sites:

```bash
python3 - <<'PY'
import re
from pathlib import Path

for path in Path("packages/vibepy-hub/tests").glob("test_*.py"):
    text = path.read_text(encoding="utf-8")
    replaced = re.sub(r"\bSAMPLES\b", "EXAMPLES", text)
    if replaced != text:
        path.write_text(replaced, encoding="utf-8")
        print(path)
PY
```

Expected: `test_configuration.py`, `test_installation.py`, `test_runtime.py`.

- [ ] **Step 4: Prove the constant resolves before running the suite**

The Hub installs an App from a folder under `EXAMPLES`, so a wrong `parents[]` index fails four
tests with an unhelpful message. Check it directly:

```bash
uv run python -c "
from pathlib import Path
support = Path('packages/vibepy-hub/tests/tests_support.py').resolve()
print(support.parents[3])
print((support.parents[3] / 'examples' / 'todo' / 'pyproject.toml').is_file())
"
```

Expected: the repository root, then `True`.

- [ ] **Step 5: Update the Makefile's paths**

```make
lint:
	uv run ruff check src tests packages examples
	uv run ruff format --check src tests packages examples

format:
	uv run ruff format src tests packages examples
	uv run ruff check --fix src tests packages examples
```

- [ ] **Step 6: Re-lock, re-sync and run the suite**

```bash
uv lock && uv sync && make lint typecheck test
```

Expected: 152 passed. `uv lock` rewrites each member's path; no version changes.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Move to the workspace layout uv documents"
```

---

### Task 3: Split the core's dependencies into channel extras

Test first: the acceptance criterion is about an environment, so the test builds one.

**Files:**
- Create: `tests/test_channel_extras.py`
- Modify: `pyproject.toml` (`[project] dependencies`,
  `[project.optional-dependencies]`, `[dependency-groups] dev`)
- Modify: `packages/vibepy-hub/pyproject.toml`, `examples/todo/pyproject.toml`,
  `examples/notes/pyproject.toml` (the extra each declares)

**Interfaces:**
- Consumes: `examples/notes` as the workspace member `vibepy-notes` (Task 2).
- Produces: extras `vibepy-core[web]` and `vibepy-core[agent]`.

- [ ] **Step 1: Write the failing test**

`tests/test_channel_extras.py`:

```python
"""What an App's environment holds is what the channels it offers require.

The criterion is about an environment rather than a declaration, so this builds
one: `uv sync --package` resolves from `uv.lock`, and `UV_PROJECT_ENVIRONMENT`
sends it somewhere the repository's own environment is not. See
`docs/decisions/ADR-025-the-framework-implements-channel-neutrality-and-delegates-the-rest.md`.
"""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_TECHNOLOGY = ("nicegui", "fastapi", "uvicorn")


def distributions_in(environment: Path, /) -> set[str]:
    """The distribution names installed in one environment.

    Read from the `.dist-info` directories rather than by running a command in
    the environment, because the interpreter's own path differs between macOS
    and Windows and this needs neither.
    """
    return {
        metadata.name.split("-")[0].lower().replace("_", "-")
        for metadata in environment.rglob("*.dist-info")
    }


def sync(package: str, environment: Path, /) -> None:
    """Install one workspace member's own dependencies into one environment."""
    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = str(environment)
    subprocess.run(
        ["uv", "sync", "--package", package, "--no-dev", "--frozen"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_an_agent_only_apps_environment_holds_no_web_technology(tmp_path: Path) -> None:
    environment = tmp_path / "notes-env"
    sync("vibepy-notes", environment)

    installed = distributions_in(environment)

    assert "vibepy-notes" in installed
    assert "mcp" in installed
    assert [held for held in WEB_TECHNOLOGY if held in installed] == []
```

`uv` is invoked from `PATH`, which is what `installer.py:82-83` already does for
`uv venv` and `uv pip install`, so this introduces no new assumption about the host.

- [ ] **Step 2: Run it to watch it fail**

```bash
uv run pytest tests/test_channel_extras.py -v
```

Expected: FAIL on the last assertion, listing `nicegui`, `fastapi` and `uvicorn`, because
`vibepy-core` still depends on all four SDKs.

- [ ] **Step 3: Give the core extras instead of channels**

In `pyproject.toml`:

```toml
dependencies = [
    "pydantic>=2.9",
]

[project.optional-dependencies]
web = [
    "fastapi>=0.115",
    "nicegui>=3.16",
    "uvicorn>=0.34",
]
agent = [
    "mcp>=2.1",
]
```

The three in `[web]` are the three the framework imports itself, in
`src/vibepy_core/adapters/nicegui/` and `src/vibepy_core/serve.py`; `nicegui` requiring two of
them transitively is not a reason to stop declaring what we import.

- [ ] **Step 4: Declare the channels each consumer offers**

`packages/vibepy-hub/pyproject.toml`:

```toml
dependencies = [
    "vibepy-core[web]",
    "pydantic>=2.9",
]
```

`examples/todo/pyproject.toml`:

```toml
dependencies = ["vibepy-core[web,agent]"]
```

`examples/notes/pyproject.toml`:

```toml
dependencies = ["vibepy-core[agent]"]
```

Each file keeps its existing `[tool.uv.sources] vibepy-core = { workspace = true }`.

- [ ] **Step 5: Give the dev group both channels**

In `pyproject.toml`'s `[dependency-groups]`, the suite exercises both channels and the core no
longer carries either:

```toml
dev = [
    "vibepy-core[web,agent]",
    "vibepy-hub",
    "vibepy-todo",
    "vibepy-notes",
    "nicegui[testing]>=3.16",
    "ruff>=0.14",
    "pyright>=1.1.400",
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pre-commit>=4.6.2",
]
```

A dependency group may name the project's own extras; `[tool.uv.sources]` needs no entry for
`vibepy-core`, which is the root.

- [ ] **Step 6: Re-lock, re-sync, and run the new test**

```bash
uv lock && uv sync && uv run pytest tests/test_channel_extras.py -v
```

Expected: PASS. If `uv sync --package` reports a missing cache entry rather than an assertion
failure, run `uv sync` once first so the lock's wheels are cached; the test never resolves, it
only installs.

- [ ] **Step 7: Run the whole suite**

```bash
make lint typecheck test
```

Expected: 153 passed — the 152 unchanged, plus the one this task adds. This is the only place in
L1 where the count moves, and the spec's criterion is about the 152.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Make each channel's SDK an extra of the core"
```

---

### Task 4: Name the checks once

The Makefile becomes the only place the checks are written, and CI invokes it. `.pre-commit-config.yaml`
is the third copy and its `files:` filter stops at `src|tests`, which Task 2 made wrong.

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.pre-commit-config.yaml`

**Interfaces:**
- Consumes: the Makefile targets from Task 2.
- Produces: nothing later tasks read.

- [ ] **Step 1: Have CI run the Makefile**

Replace the four `run` steps in `.github/workflows/ci.yml` with two, keeping everything above
them:

```yaml
      - run: uv sync

      - if: runner.os == 'Windows'
        run: choco install make --no-progress

      - run: make lint typecheck test
```

The Windows runner image carries no GNU make; macOS does.

- [ ] **Step 2: Let pre-commit see the whole workspace**

In `.pre-commit-config.yaml`, drop both `files:` filters so ruff checks what ruff is configured
to check:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.16.6
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: pyright
        name: pyright
        entry: uv run pyright
        language: system
        types: [python]
        pass_filenames: false
```

- [ ] **Step 3: Prove no path list survives in CI**

```bash
grep -n 'run:' .github/workflows/ci.yml
grep -n 'ruff\|pyright\|pytest' .github/workflows/ci.yml
```

Expected: three `run:` lines — `uv sync`, the Windows make install, and
`make lint typecheck test` — and no line naming a check directly.

- [ ] **Step 4: Run pre-commit over everything**

```bash
uv run pre-commit run --all-files
```

Expected: ruff-check, ruff-format and pyright all pass, and the run reports files under
`packages/` and `examples/` rather than skipping them.

- [ ] **Step 5: Run the suite**

```bash
make lint typecheck test
```

Expected: 153 passed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Let CI run what the Makefile runs"
```

---

### Task 5: Correct the documents L1 made false

Only what this stage invalidated: three command lines, one path inside an `Accepted` record, and
the one fact about an App's environment that the extras split introduces.

**Files:**
- Modify: `docs/architecture/adapters.md:80`
- Modify: `docs/architecture/packaging.md:78`, `:92`, `:116`, and one addition after `:106`
- Modify: `docs/architecture/lifecycle.md:64`
- Modify: `docs/decisions/ADR-025-...:50`

**Interfaces:**
- Consumes: the command names from Task 1 and the paths from Task 2.
- Produces: nothing.

- [ ] **Step 1: Rewrite the command names in the architecture documents**

```bash
python3 - <<'PY'
import re
from pathlib import Path

for path in [
    Path("docs/architecture/adapters.md"),
    Path("docs/architecture/packaging.md"),
    Path("docs/architecture/lifecycle.md"),
]:
    text = path.read_text(encoding="utf-8")
    replaced = re.sub(r"\bvibepy\.(serve|describe)\b", r"vibepy_core.\1", text)
    if replaced != text:
        path.write_text(replaced, encoding="utf-8")
        print(path)
PY
```

The entry-point group `vibepy.apps` in `packaging.md:11`, `:14` and `:48` is untouched by this
pattern, which is correct — it did not change.

- [ ] **Step 2: State what an App's environment holds**

`packaging.md` owns the environment story and now omits a published fact. Add this after the
self-description and serve commands section, before `## The isolation invariant`:

```markdown
## What an environment holds

An App's environment holds `vibepy-core`, the extras for the channels that App offers, and the
App. `vibepy-core` itself declares no channel: `vibepy-core[web]` carries the Web technology and
`vibepy-core[agent]` carries MCP, so an App declaring no Pages installs no Web technology. See
`docs/decisions/ADR-025-the-framework-implements-channel-neutrality-and-delegates-the-rest.md`.
```

- [ ] **Step 3: Correct the one broken path in an Accepted record**

In `docs/decisions/ADR-025-the-framework-implements-channel-neutrality-and-delegates-the-rest.md:50`,
`samples/notes` becomes `examples/notes`. Nothing else in that record changes: a broken
reference is one of the two corrections an `Accepted` record takes.

- [ ] **Step 4: Prove no document names a path or command that no longer exists**

```bash
grep -rn 'vibepy\.serve\|vibepy\.describe\|src/vibepy\b\|vibepy/\|hub/src\|samples/' docs/ \
  | grep -v 'docs/milestones/'
```

Expected: only `docs/decisions/ADR-023` and `ADR-026`, which name the old commands in their own
prose and are left alone: an `Accepted` record is an append-only statement as of its date
(Microsoft, *Maintain an architecture decision record*: "The ADR serves as an append-only log.
Don't go back and edit accepted records"), and current truth is read from `docs/architecture/`.
No `.md` filter, because `docs/hub-ui-mockup.html` names a command too, and `vibepy/` in the
pattern because `errors.md` names a module path in that form. `docs/milestones/` is excluded:
`code-review/` records what was found at `05d6027`, and this stage's own folder describes the
move it is making.

- [ ] **Step 5: Run the suite**

```bash
make lint typecheck test
```

Expected: 153 passed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Correct the documents L1 made false"
```

---

## Integration

- [ ] `make lint typecheck test` passes: 153 tests, being the 152 with the same results plus the
  environment test Task 3 added
- [ ] `git log --stat` over the branch shows no file under `src/` changed for any reason other
  than an import, a docstring path, or `serve.py`'s `prog`
- [ ] the branch merges into `main` with `--no-ff`
- [ ] `docs/milestones/L1/` is deleted on integration, after checking that nothing in it is still
  true and unowned elsewhere: the layout is visible in the repository, the extras are in
  ADR-025 and `packaging.md`, and the reasoning about the two readings inside D3 belongs in the
  merge commit message
- [ ] the stage is not pushed until it is merged
