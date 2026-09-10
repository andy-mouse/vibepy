# CR3 - Documentation debt implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every surface that describes this framework say what is true today, answer the
three open questions in the documents that own them, and leave PEP 257 enforced by the linter.

**Architecture:** Documents are corrected to match the code, never the reverse (D10). One new
document, `docs/architecture/operation.md`, owns the operation half of an App's lifecycle as
`authoring.md` owns the authoring half; the Hub is described inside it as that role's current
implementation. The docstring work is one pass at the end, resting on PEP 257, PEP 8 and Google
§3.8, and the only enforcement it leaves behind is ruff's `D` rules.

**Tech Stack:** Markdown under `docs/`, ruff (`D` rules, `pep257` convention), pyright strict,
pytest. No runtime dependency changes.

## Global Constraints

- The spec is `docs/milestones/CR3/spec.md`. Its acceptance criteria are the tests.
- The branch is `cr3-documentation-debt`, already cut from `main`. Do not push.
- `make lint typecheck test` must pass at the end of every task. 252 tests pass at the start and
  252 pass at the end. No test is added and none is removed.
- No behaviour changes. If a document and the code disagree, the document is wrong (D10).
- `AGENTS.md` is not edited. `docs/roadmap.md` is not edited.
- No test, hook or script is added to police documentation. The `D` rules are the only
  enforcement introduced.
- One role per document; the same fact is not stated in two places. Cite the owner instead of
  restating it.
- An `Accepted` ADR is not edited. No ADR is written in this stage.
- Run tests with `uv run pytest`. Lint with `make lint`.

---

### Task 1: The operation role gets a document

`docs/architecture/` has nine documents and none owns the operation half of an App's lifecycle,
so `docs/roadmap.md` M11 is specified against "Hub Core state" that no document defines. The
document is named after the role, not after the Hub, and is written in `authoring.md`'s shape so
the two read as a pair.

Read `docs/architecture/authoring.md` first: it is 66 lines, terse, and its section order is the
order used below.

**Files:**
- Create: `docs/architecture/operation.md`
- Read for facts: `packages/vibepy-hub/src/vibepy_hub/models.py:10-30` (the `hub.*` code table),
  `packages/vibepy-hub/src/vibepy_hub/tools/` (the eight Tool names),
  `packages/vibepy-hub/src/vibepy_hub/tools/installation.py:86,106,130` (the three state values)

**Interfaces:**
- Consumes: nothing.
- Produces: the document later tasks cite — `docs/architecture/operation.md`, owning the
  operation role, the three state values and the `hub.*` vocabulary by reference.

- [ ] **Step 1: Write the document**

Create `docs/architecture/operation.md`:

```markdown
# App Operation Architecture

## Goal

An App that exists is not yet an App anyone can use. Operation is the half of an App's lifecycle
that begins where authoring ends: an App is installed into an environment of its own, given an
address, configured, started, stopped and reached.

`docs/architecture/authoring.md` owns the other half. Neither owns the core model, which
`docs/architecture/app-model.md`, `tool-model.md` and `page-model.md` own.

## Framework responsibility

The framework operates nothing. It provides what an operator needs and stops there:

- a declaration a host can read without importing the App
- a command that describes an environment's Apps, and a command that opens an App's Web channel
- a window that reports its own failure rather than leaving a server answering for nothing
- failures that carry a stable code and a category across a process boundary

`docs/architecture/packaging.md` owns the first two, `docs/architecture/errors.md` the last.

## Operation core before any channel

Operation is an App built with this framework, not a capability inside it. See
`docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md`. Its capabilities are therefore
Tools, which makes them reachable from either channel and neutral between them.

The capabilities that exist today, as the Hub declares them:

- `register_package_source`, `remove_package_source` — where the operator looks for Apps
- `list_apps` — what is known, what is installed, what is running
- `install_app`, `remove_app` — an environment of its own per App, created and destroyed
- `configure_app` — the configuration an App's window validates against its own declaration
- `start_app`, `stop_app` — the Web channel window of an installed App

## What an operated App is described by

Three vocabularies, defined in `vibepy_hub/models.py` and not restated here:

- **state** — `available` for an App the operator knows of, `installed` for one whose environment
  exists, `running` for one whose Web channel is serving
- **address** — derived from the App's canonical distribution name and the proxy's port, and
  present from installation rather than from start. See
  `docs/decisions/ADR-028-an-app-is-addressed-by-its-distribution-name.md` and
  `docs/decisions/ADR-031-the-proxy-is-traefik.md`
- **diagnostic** — a `hub.*` code, its category, a message and details, returned as data where a
  failure is one the operator expects. See
  `docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md`

## The current implementation

The Hub, `packages/vibepy-hub`. An environment per App, so no App's dependencies constrain
another's; a proxy in front, so an App is reached by name without knowing it is proxied.

## What operation must not become

- it must not run the business logic of the Apps it operates
- it must not import an App it operates; it reads declarations across a process boundary
- it must not own the proxy, the supervisor or the package installer it delegates to
- it must not offer generic data mutation where a business operation is what an operator means

## North-star test

An operator installs an App from a folder, configures it, starts it, and reaches it at an address
of its own — and nothing in that App's code exists because of how it was served.
```

- [ ] **Step 2: Check every fact against the code**

Run and read:

```bash
grep -rn 'name="' packages/vibepy-hub/src/vibepy_hub/tools/*.py
grep -n 'state="' packages/vibepy-hub/src/vibepy_hub/tools/installation.py
sed -n '10,30p' packages/vibepy-hub/src/vibepy_hub/models.py
```

Expected: the eight Tool names in the document match, the three state values match, and no
`hub.*` code is copied into the document. If a name differs, the code wins.

- [ ] **Step 3: Check the ADR citations resolve and are not superseded**

```bash
ls docs/decisions/ADR-024* docs/decisions/ADR-028* docs/decisions/ADR-029* docs/decisions/ADR-031*
grep -n "^## Status" -A1 docs/decisions/ADR-024* docs/decisions/ADR-028* docs/decisions/ADR-029* docs/decisions/ADR-031*
```

Expected: four files exist and each status is `Accepted`. A superseded record is not cited.

- [ ] **Step 4: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests.

- [ ] **Step 5: Commit**

```bash
git add docs/architecture/operation.md
git commit -m "Give the operation half of a lifecycle a document of its own"
```

---

### Task 2: `authoring.md` says which half it is, and stops naming what it does not own

`authoring.md` lists `app_status`, which was never built, and `start_app`, `stop_app` and
`install_package`, which name capabilities the operation role ships as `start_app`, `stop_app`
and `install_app`. A reader cannot tell which document owns them.

**Files:**
- Modify: `docs/architecture/authoring.md:1-10` (the goal), `:31-48` (the capability list)

**Interfaces:**
- Consumes: `docs/architecture/operation.md` from Task 1.
- Produces: nothing later tasks read.

- [ ] **Step 1: Add the pairing sentence to the goal**

After the first paragraph of `## Goal`, add:

```markdown
Authoring is one half of an App's lifecycle. `docs/architecture/operation.md` owns the other: how
an App that exists is installed, addressed, started and reached.
```

- [ ] **Step 2: Cut the capabilities the operation role owns**

In `## Authoring core before Authoring MCP`, remove `start_app`, `stop_app`, `app_status` and
`install_package` from the list, and remove the paragraph beginning "`start_app`, `stop_app` and
`app_status` describe the Web channel window the Hub owns." Replace that paragraph with:

```markdown
Installing, starting and stopping an App are not authoring capabilities. They belong to the
operation role, which declares them as Tools of its own; see `docs/architecture/operation.md`.
```

The list that remains is `inspect_framework`, `inspect_app`, `validate_app`, `validate_package`,
`invoke_tool`, `run_conformance_tests`, `get_app_errors`, `get_runtime_logs`, `package_app`.

- [ ] **Step 3: Verify no name is claimed by both documents**

```bash
grep -n "start_app\|stop_app\|app_status\|install_package\|install_app" docs/architecture/authoring.md docs/architecture/operation.md
```

Expected: every hit is in `operation.md`, except the one sentence in `authoring.md` that points at
it.

- [ ] **Step 4: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests.

- [ ] **Step 5: Commit**

```bash
git add docs/architecture/authoring.md
git commit -m "Let authoring name only what authoring owns"
```

---

### Task 3: Routes do not leave with the window, and three places stop saying they do

`register_pages` calls `ui.page(...)`, which mutates NiceGUI's process-global route table.
Nothing removes an entry. ADR-026 says exactly this in its consequences, so `adapters.md` and the
two docstrings contradict the record they rest on. The fix is the document, not the code: making
routes leave would build what a document promised and no milestone asked for.

**Files:**
- Modify: `docs/architecture/adapters.md:76-79`
- Modify: `src/vibepy_core/adapters/nicegui/application.py:40-46` (the docstring)
- Modify: `src/vibepy_core/adapters/nicegui/web.py:1-13` (the module docstring)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Read what the record actually says**

```bash
sed -n '50,58p' docs/decisions/ADR-026-the-web-window-is-the-served-applications-lifespan.md
```

Expected: the consequence "the Web channel's routes are registered on the technology's
process-global table inside the window, and this decision does not make them leave with it."
That sentence is the fact the three sites must agree with.

- [ ] **Step 2: Correct `adapters.md`**

Replace the paragraph at `docs/architecture/adapters.md:76-79`:

```markdown
`build_web_app(definition, lifespan, config=…)` returns the ASGI application those routes are
served through, with the running window as that application's own lifespan: a window that refuses
to open fails the application's startup rather than leaving a server answering for nothing. What
the window bounds is the PageRuntime each builder closes over, not the routes themselves — those
are registered on the Web technology's process-global table and stay there, which is why one
process serves one App's Pages. See
`docs/decisions/ADR-026-the-web-window-is-the-served-applications-lifespan.md`.
```

- [ ] **Step 3: Correct the two docstrings**

In `src/vibepy_core/adapters/nicegui/application.py`, the `build_web_app` docstring becomes:

```python
    """Build the Web projection of one App's Pages.

    NiceGUI documents mounting into an application of one's own as
    `ui.run_with(app)`, which is what lets the window be that application's
    lifespan. A builder closes over the PageRuntime the window yielded, so a
    render outside the window is unreachable; the routes themselves are
    registered on the process-global table and are not removed when the window
    closes.
    """
```

In `src/vibepy_core/adapters/nicegui/web.py`, the third sentence of the module docstring —
"Registration therefore happens inside that window, and a builder holds its runtime for exactly
as long as the window lasts." — becomes:

```python
Registration therefore happens inside that window, and a builder can only render
while its runtime lives. Registration itself is not undone: it mutates the Web
technology's process-global route table, which one process holds for one App.
```

- [ ] **Step 4: Verify no site still claims removal**

```bash
grep -rn "left when it closes\|leave with the window\|leaves with it" docs/architecture src/vibepy_core
```

Expected: no hit outside `docs/decisions/` (where ADR-026 states the negative) and the corrected
prose.

- [ ] **Step 5: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests.

- [ ] **Step 6: Commit**

```bash
git add docs/architecture/adapters.md src/vibepy_core/adapters/nicegui/application.py src/vibepy_core/adapters/nicegui/web.py
git commit -m "Say that a window bounds a runtime, not a route table"
```

---

### Task 4: The Agent channel has no command, and the core model has no manifest

Two stale claims, both one edit each. `app-model.md:91` says the Agent channel's entrypoint is "a
command the MCP client launches"; no `[project.scripts]` exists in any of the five project files
and no module opens an Agent channel. `architecture.md:18` lists `Manifest / metadata` in the core
model; ADR-023 and `packaging.md` state the framework defines no manifest format.

**Files:**
- Modify: `docs/architecture/app-model.md:88-93`
- Modify: `docs/architecture.md:14-22`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Verify both claims are still false**

```bash
grep -rn "project.scripts" --include=pyproject.toml .
grep -rn "__main__" src/vibepy_core
```

Expected: no `[project.scripts]` anywhere; `__main__` only in `describe.py` and `serve.py`, both
of which are Web-channel or description commands. If either expectation fails, stop: the finding
is stale and the document may be right.

- [ ] **Step 2: Correct `app-model.md`**

Replace the paragraph at `docs/architecture/app-model.md:91-93`:

```markdown
An installed App has one entrypoint per channel it offers. The Web channel's is what the operator
runs: `python -m vibepy_core.serve`, which `docs/architecture/packaging.md` owns. The Agent
channel has no command today — nothing in this repository declares a console script, and an
Agent-only App is therefore reachable only by a host that opens the channel itself. An App
declaring no Pages has no Web channel.
```

- [ ] **Step 3: Correct the core-model diagram**

In `docs/architecture.md`, delete the line `├─ Manifest / metadata` from the `## Core model`
block. Nothing replaces it: what a distribution says about its App is entry-point metadata, which
`packaging.md` owns.

- [ ] **Step 4: Verify**

```bash
grep -rn "Manifest" docs/architecture.md docs/architecture/
grep -rn "command the MCP client launches" docs/
```

Expected: no hits.

- [ ] **Step 5: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests.

- [ ] **Step 6: Commit**

```bash
git add docs/architecture.md docs/architecture/app-model.md
git commit -m "Stop promising a command and a manifest that do not exist"
```

---

### Task 5: Q2 — a Tool name is not validated, and the document says so

Nothing checks a Tool name's format. The window refuses a declaration carrying one name twice,
and the MCP projection passes whatever name it is given through. `tool-model.md` requires nothing,
which leaves a reader unable to tell whether that is a gap or a decision. It is a decision.

**Files:**
- Modify: `docs/architecture/tool-model.md:93-105` (the `### ToolRegistry` section)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Verify nothing validates a name**

```bash
grep -rn "name" src/vibepy_core/tool/model.py src/vibepy_core/tool/registry.py | grep -i "valid\|pattern\|match\|Field("
```

Expected: no hit. `ToolDefinition.name` is a bare `str`.

- [ ] **Step 2: State it in the document**

After the paragraph beginning "Registering a name twice replaces the earlier Tool" in
`docs/architecture/tool-model.md`, add:

```markdown
A name's *format* is not validated anywhere. `ToolDefinition.name` is a `str`, and the projection
a channel publishes carries it through unchanged. This is a decision rather than a gap: any
grammar a name must satisfy belongs to the protocol a channel speaks, and a framework that
enforced one channel's grammar in the core model would be implementing that channel's rule on its
behalf. What the framework guarantees about a name is uniqueness within one App.
```

- [ ] **Step 3: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture/tool-model.md
git commit -m "Say that a Tool name is unique and otherwise unexamined"
```

---

### Task 6: Q3 — the package root is the import surface, and consumers use it

`tests/test_package.py` asserts the exact contents of `vibepy_core.__all__`, so the root is a
guarded public surface. Nothing outside the tests uses it: `fixtures/*` and `vibepy_hub` import
from `vibepy_core.tool`, `.app`, `.page` and `.errors` in 20 places. The root becomes what the
documents state and what consumers use; the subpackage paths keep working and are simply not what
is documented.

**Files:**
- Modify: `docs/architecture/app-model.md` (a new short section at the end of `## Definition`)
- Modify: every file the grep in Step 1 reports under `fixtures/` and
  `packages/vibepy-hub/src/`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. No symbol moves; only import statements change.

- [ ] **Step 1: List every import to move**

```bash
grep -rn "^from vibepy_core\." --include="*.py" fixtures packages/vibepy-hub/src
```

Expected: 20 lines. Every name they import is in `vibepy_core.__all__` — confirm with:

```bash
python3 -c "import vibepy_core, sys; print(sorted(vibepy_core.__all__))"
```

If a name is imported that the root does not export, stop and report it: that is a gap in the
public surface, and widening `__all__` is a public-API change this task does not decide.

- [ ] **Step 2: Move them**

Rewrite each reported import as one `from vibepy_core import ...` per file, merged and
alphabetised by ruff's isort rules. Example, `fixtures/todo-app/src/todo_app/tools.py`:

```python
from vibepy_core import Tool, ToolContext, ToolDefinition
```

`from vibepy_core.app.package import AppRef, discover_apps` becomes
`from vibepy_core import AppRef, discover_apps` — both names are exported from the root.

- [ ] **Step 3: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests. `ruff check` also proves import order. A failure here is a name the
root does not export — go back to Step 1.

- [ ] **Step 4: State the surface in the document**

At the end of `## Definition` in `docs/architecture/app-model.md`, add:

```markdown
## The import surface

An App author imports from `vibepy_core` and from nothing below it. The package root is the
public surface: `tests/test_package.py` holds its exact contents, so a name that is not exported
there is not public. The subpackages beneath it — `vibepy_core.tool`, `.page`, `.app`, `.errors` —
are how the framework is organised, and they keep working for anything already written against
them.
```

- [ ] **Step 5: Commit**

```bash
git add docs/architecture/app-model.md fixtures packages/vibepy-hub/src
git commit -m "Reach the framework through one surface, the one a test already guards"
```

---

### Task 7: Q4 — the mockup goes where what-is-next lives

`docs/hub-ui-mockup.html` says what M11 will render, not what is true, and the role table in
`AGENTS.md` has no row for a design artifact. The milestone folder is that row: it holds what is
next, and integration deletes it.

**Files:**
- Move: `docs/hub-ui-mockup.html` → `docs/milestones/M11/hub-ui-mockup.html`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Confirm nothing references the path**

```bash
grep -rn "hub-ui-mockup" --exclude-dir=.git . | grep -v "docs/milestones/CR3"
```

Expected: only the file itself. If a reference exists, update it in this task.

- [ ] **Step 2: Move it**

```bash
mkdir -p docs/milestones/M11
git mv docs/hub-ui-mockup.html docs/milestones/M11/hub-ui-mockup.html
```

- [ ] **Step 3: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests.

- [ ] **Step 4: Commit**

```bash
git add -A docs
git commit -m "Keep a mockup where what-is-next is kept"
```

---

### Task 8: The docstring pass

One pass, at the end, on its own commit. Two halves: switch the standard on, then bring the
docstrings to it. 81 violations stand under the `pep257` convention, and 28 references to ADRs
and `docs/` paths stand across 16 modules — the wheel ships only `src/vibepy_core`, so a reader
of the installed package cannot resolve any of them.

What belongs where is decided by the published conventions, not by preference:

- a docstring documents behaviour, arguments, return value, side effects, exceptions and
  restrictions, summary line in the imperative — PEP 257
- implementation detail belongs in a docstring only when it is "relevant to how the function is
  to be used" — Google §3.8
- what explains *why* the code is shaped as it is belongs in a comment at the site it explains —
  Google §3.8, with PEP 8's requirement that a comment not contradict the code

Apply that test to each of the 28 references individually. A fact an architecture document owns is
deleted rather than moved, because `AGENTS.md` forbids the same fact in two places.

**Files:**
- Modify: `pyproject.toml:68-88` (`[tool.ruff.lint]` and a new `[tool.ruff.lint.pydocstyle]`)
- Modify: the modules the greps in Step 2 and Step 5 report, under `src/vibepy_core/` and
  `packages/vibepy-hub/src/`

**Interfaces:**
- Consumes: nothing.
- Produces: `make lint` enforcing `D` for every later stage.

- [ ] **Step 1: Switch the rules on for source trees only**

In `pyproject.toml`, extend the selection and set the convention:

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC", "RUF", "TID", "D"]

# PEP 257 is a standard, so it is enforced by the linter rather than restated as
# a rule of our own. ruff implements it as the `D` rules and `convention`
# selects which of them a style disables.
# <https://docs.astral.sh/ruff/settings/#lint_pydocstyle_convention>
[tool.ruff.lint.pydocstyle]
convention = "pep257"
```

Add to `[tool.ruff.lint.per-file-ignores]`:

```toml
# Docstrings are documentation of a public surface. A test module and a fixture
# App are neither: their module docstrings state what the file covers, and
# PEP 8 asks for docstrings on public API, which these are not.
"tests/**" = ["D"]
"packages/*/tests/**" = ["D"]
"fixtures/**" = ["D"]
```

- [ ] **Step 2: See the full list before changing any docstring**

```bash
uv run ruff check --statistics src packages/*/src
uv run ruff check --output-format=concise src packages/*/src | grep " D[0-9]"
```

Expected: 81 `D` violations — 30 `D401`, 22 `D107`, 21 `D102`, 8 `D101`. Keep the concise output;
it is the work list.

- [ ] **Step 3: Fix `D401` — the summary line prescribes as a command**

30 sites. A summary reading "Maps a Tool name to the Tool registered under it." becomes "Map a
Tool name to the Tool registered under it." Change the mood and nothing else in this step.

Run: `uv run ruff check --select D401 src packages/*/src`
Expected: no violations.

- [ ] **Step 4: Fix `D101`, `D102`, `D107` — document the public surface**

51 sites. Write the missing docstring; do not silence the rule. For `__init__`, PEP 257 asks what
the constructor does with its arguments, one line:

```python
    def __init__(self) -> None:
        """Start with no Tool registered."""
```

For a public method, the summary plus what a caller must know — the exception it raises is part of
the contract:

```python
    def resolve(self, name: str) -> Tool[DepsT]:
        """Return the Tool registered under `name`.

        Raises:
            ToolNotFoundError: no Tool is registered under that name.
        """
```

Where a class's purpose is already stated by the module docstring, the class docstring still says
what the class is; a cross-reference is not a docstring.

Run: `uv run ruff check --select D src packages/*/src`
Expected: no violations.

- [ ] **Step 5: Judge the 28 repository references one at a time**

```bash
grep -rn "ADR-\|docs/" --include="*.py" src/vibepy_core packages/vibepy-hub/src
```

For each hit, decide by the criterion at the top of this task:

- **a caller needs it** — keep it, phrased as the contract rather than as a citation. Rare.
- **it explains the implementation to a maintainer** — move it to a comment at the line it
  explains, and drop the record's filename: `# The window owns the runtime, so a builder cannot
  outlive it.`
- **an architecture document already owns the fact** — delete it.

Two known cases to handle while you are there: `packages/vibepy-hub/src/vibepy_hub/entry.py`
cites ADR-018, which ADR-020 superseded, and `src/vibepy_core/adapters/nicegui/web.py` and
`application.py` were already corrected in Task 3 — do not re-litigate their prose here, only
their citations.

Verify:

```bash
grep -rn "ADR-\|docs/" --include="*.py" src/vibepy_core packages/vibepy-hub/src
```

Expected: no hit inside a docstring. A comment may remain only where it explains the code beside
it.

- [ ] **Step 6: Run the gate**

Run: `make lint typecheck test`
Expected: pass, 252 tests. `ruff format --check` must also pass; reflow anything the rewrite made
too long.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src packages
git commit -m "Let the published docstring conventions be the convention"
```

---

### Task 9: The stage's own bookkeeping

`code-review-roadmap.md` still says CR3 is next and does not record that R1 merged.

**Files:**
- Modify: `docs/milestones/code-review-roadmap.md` (the `## R1` section and `## Order`)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Mark R1 merged**

Add `Merged.` beneath R1's acceptance list, in the form the earlier stages use.

- [ ] **Step 2: Update `## Order`**

Replace `CR3 — next.` with `CR3 — in progress.`

- [ ] **Step 3: Verify the file's own instruction is not carried out yet**

The file says to delete it when CR3 merges. That happens at integration, not here. Confirm the
sentence is still present and untouched:

```bash
grep -n "Delete this file when CR3 merges" docs/milestones/code-review-roadmap.md
```

Expected: one hit.

- [ ] **Step 4: Commit**

```bash
git add docs/milestones/code-review-roadmap.md
git commit -m "Record that R1 merged and CR3 is under way"
```

---

## Verification of the whole stage

Run once every task is done:

```bash
make lint typecheck test
grep -rn "Manifest" docs/architecture.md docs/architecture/
grep -rn "left when it closes\|command the MCP client launches" docs/
grep -rn "ADR-\|docs/" --include="*.py" src/vibepy_core packages/vibepy-hub/src
grep -rn "^from vibepy_core\." --include="*.py" fixtures packages/vibepy-hub/src
ls docs/architecture/
```

Expected: the gate passes with 252 tests; the first three greps are empty except for comments that
explain adjacent code; the fourth is empty; `docs/architecture/` holds ten documents, `authoring.md`
and `operation.md` among them.

Then read, rather than grep: `operation.md` against `vibepy_hub/models.py` and the eight Tools,
and `adapters.md` against `register_pages`. The acceptance criterion is that no document claims a
guarantee the code does not provide, and only reading proves that.
