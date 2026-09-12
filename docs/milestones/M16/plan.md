# M16 App Conformance Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An invalid App declaration cannot be constructed; a Page declares and is held to the Tools it invokes; Studio's `validate_app` reports every declaration violation and every pyright diagnostic of a source project as one list.

**Architecture:** Rules move into the declaring dataclasses' `__post_init__` — a value rule on `ToolDefinition`, the cross-declaration rules on `AppDefinition`, which collects every violation and raises one `AppDefinitionInvalidError`. Windows and the NiceGUI adapter stop checking. `report` writes an aggregate as one line per member. Studio adds `validate_app`, which runs `describe` and pyright in the project's environment and wraps each finding in a `Diagnostic` carrying a severity.

**Tech Stack:** Python 3.12+ dataclasses, pydantic 2, pyright (`pyright[nodejs]` via `uv run --with`), pytest (asyncio mode, `integration` marker), NiceGUI testing `User`.

Spec: `docs/milestones/M16/spec.md`. Read it before starting.

## Global Constraints

- `pyproject.toml` is the only project config; no `Any`, no `cast` in the public API; optional parameters keyword-only; `else: assert_never(value)` on exhaustive branches; blocking calls in async code go through `asyncio.to_thread`; `logging.getLogger(__name__)`, no `print`.
- Declarations that hold types or callables are frozen dataclasses; a value that crosses a process boundary is one pydantic `BaseModel` owned by `vibepy_core`, dumped by the writer and validated by the reader.
- Exception types are the contract; every framework exception declares `code` and is mapped in `ERROR_CATALOG`; `tests/test_errors.py` walks every `VibepyError` subclass and requires a `CASES` row for each.
- The Page package imports nothing from the Tool package. The rules import nothing from `vibepy_core.adapters`.
- Tests verify public contracts; one test file is one subject; a test that cannot fail is deleted.
- A task is done when `make lint typecheck test` passes. Commit after every task with a message that says what is now true, not what was done, ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Work on branch `m16-app-conformance`, cut from `main` before Task 1. Do not push. `docs/roadmap.md` is never edited.
- Docstrings: write them where a module's convention already has them; the convention pass is Task 12, not earlier.

---

## File structure

| Path | Responsibility after M16 |
| --- | --- |
| `src/vibepy_core/errors.py` | four new exceptions, their codes and categories, `report` writing an aggregate's members |
| `src/vibepy_core/tool/model.py` | `ToolDefinition.__post_init__` refuses empty `channels` |
| `src/vibepy_core/page/model.py` | `PageDefinition.tools` |
| `src/vibepy_core/app/model.py` | `AppDefinition.__post_init__` runs the cross-declaration rules |
| `src/vibepy_core/app/composition.py` | registries are filled, not checked |
| `src/vibepy_core/adapters/nicegui/web.py` | routes are registered, not checked |
| `src/vibepy_core/page/runtime.py` | the bound invoker holds the declared names |
| `src/vibepy_core/app/entrypoint.py` | `PageDescription.tools` |
| `packages/vibepy-studio/src/vibepy_studio/internals/processes.py` | `reports` (all lines) beside `reported` (the first) |
| `packages/vibepy-studio/src/vibepy_studio/internals/describing.py` | `DescribeFailed.reports` |
| `packages/vibepy-studio/src/vibepy_studio/authoring/models.py` | `Severity`, `Diagnostic`, `ValidateRequest`, `AppValidation`, `type_error`, `AppInspection.diagnostics` |
| `packages/vibepy-studio/src/vibepy_studio/authoring/internals/typechecking.py` | running pyright in a project and reading its JSON |
| `packages/vibepy-studio/src/vibepy_studio/authoring/tools/validation.py` | `validate_app` |
| `tests/test_app_conformance.py` | what an `AppDefinition` may be |
| `packages/vibepy-studio/tests/test_validate_app.py` | `validate_app` |
| `docs/decisions/ADR-037-an-app-declaration-validates-itself-at-construction.md` | why |

---

### Task 0: Branch

- [ ] **Step 1: Cut the branch**

```bash
cd /Users/andy.warhol/my-projects/vibepy
git status --short          # must be empty
git checkout -b m16-app-conformance
```

---

### Task 1: Four exceptions and a report that writes an aggregate's members

**Files:**
- Modify: `src/vibepy_core/errors.py`
- Modify: `src/vibepy_core/__init__.py` (exports)
- Test: `tests/test_errors.py`, `tests/test_package.py`

**Interfaces:**
- Produces:
  - `class ToolChannelsEmptyError(VibepyError)`, `code = "tool.channels_empty"`, `__init__(self, tool_name: str)`, `details() -> {"tool_name"}`
  - `class PageToolUnresolvedError(VibepyError)`, `code = "page.tool_unresolved"`, `__init__(self, page_name: str, tool_name: str, *, reason: str)` where `reason` is `"missing"` or `"not_exposed"`, `details() -> {"page_name", "tool_name", "reason"}`
  - `class PageToolUndeclaredError(VibepyError)`, `code = "page.tool_undeclared"`, `__init__(self, page_name: str, tool_name: str)`, `details() -> {"page_name", "tool_name"}`
  - `class AppDefinitionInvalidError(VibepyError)`, `code = "app.declaration_invalid"`, `__init__(self, app_id: str, errors: Sequence[VibepyError])`, attributes `app_id`, `errors: tuple[VibepyError, ...]`, `details() -> {"app_id", "count", "codes"}` where `codes` is the member codes joined by `", "`
  - `report(error)` writes the aggregate's line followed by one line per member, in order

- [ ] **Step 1: Add the CASES rows and the report test**

In `tests/test_errors.py`, extend the import from `vibepy_core.errors` with `AppDefinitionInvalidError, PageToolUndeclaredError, PageToolUnresolvedError, ToolChannelsEmptyError, report`. Append to `CASES`:

```python
    (
        ToolChannelsEmptyError("create_todo"),
        "tool.channels_empty",
        ErrorCategory.DECLARATION,
        {"tool_name": "create_todo"},
    ),
    (
        PageToolUnresolvedError("todos", "list_todos", reason="missing"),
        "page.tool_unresolved",
        ErrorCategory.DECLARATION,
        {"page_name": "todos", "tool_name": "list_todos", "reason": "missing"},
    ),
    (
        PageToolUndeclaredError("todos", "remove_todo"),
        "page.tool_undeclared",
        ErrorCategory.CALLER,
        {"page_name": "todos", "tool_name": "remove_todo"},
    ),
    (
        AppDefinitionInvalidError(
            "todo-app", [ToolNameConflictError("read"), PageRouteInvalidError("todos", "todos")]
        ),
        "app.declaration_invalid",
        ErrorCategory.DECLARATION,
        {"app_id": "todo-app", "count": "2", "codes": "tool.name_conflict, page.route_invalid"},
    ),
```

Add at the end of the file:

```python
def test_an_aggregate_is_reported_as_its_own_line_then_one_line_per_member(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A declaration that fails several ways is several lines a reader takes one by one."""
    report(
        AppDefinitionInvalidError(
            "todo-app", [ToolNameConflictError("read"), PageRouteInvalidError("todos", "todos")]
        )
    )

    lines = [read_report_line(line) for line in capsys.readouterr().err.splitlines()]
    assert [info.code for info in lines if info is not None] == [
        "app.declaration_invalid",
        "tool.name_conflict",
        "page.route_invalid",
    ]
    assert lines[0] is not None and lines[0].details["count"] == "2"


def test_a_single_failure_is_reported_as_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    report(ToolNotFoundError("create_todo"))

    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    assert read_report_line(lines[0]) is not None
```

In `tests/test_package.py`, add `"AppDefinitionInvalidError"`, `"PageToolUndeclaredError"`, `"PageToolUnresolvedError"`, `"ToolChannelsEmptyError"` to the expected root exports, keeping the list sorted as it is.

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_errors.py tests/test_package.py -q
```
Expected: ImportError on the new names.

- [ ] **Step 3: Implement**

In `src/vibepy_core/errors.py`, after `PageNameConflictError`:

```python
class ToolChannelsEmptyError(VibepyError):
    """A Tool declared no channel to be exposed through."""

    code = "tool.channels_empty"

    def __init__(self, tool_name: str) -> None:
        """Record `tool_name` for the message and for `details()`."""
        super().__init__(f"Tool {tool_name!r} is exposed through no channel")
        self.tool_name = tool_name

    def details(self) -> Mapping[str, str]:
        """Return `tool_name`."""
        return {"tool_name": self.tool_name}


class PageToolUnresolvedError(VibepyError):
    """A Page declared a Tool the App does not declare, or does not expose to the Web channel."""

    code = "page.tool_unresolved"

    def __init__(self, page_name: str, tool_name: str, *, reason: str) -> None:
        """Record `page_name`, `tool_name` and `reason` — `missing` or `not_exposed`."""
        super().__init__(
            f"Page {page_name!r} declares the Tool {tool_name!r}, which is {reason}"
        )
        self.page_name = page_name
        self.tool_name = tool_name
        self.reason = reason

    def details(self) -> Mapping[str, str]:
        """Return `page_name`, `tool_name` and `reason`."""
        return {"page_name": self.page_name, "tool_name": self.tool_name, "reason": self.reason}


class PageToolUndeclaredError(VibepyError):
    """A Page invoked a Tool it did not declare."""

    code = "page.tool_undeclared"

    def __init__(self, page_name: str, tool_name: str) -> None:
        """Record `page_name` and `tool_name` for the message and for `details()`."""
        super().__init__(f"Page {page_name!r} invoked the undeclared Tool {tool_name!r}")
        self.page_name = page_name
        self.tool_name = tool_name

    def details(self) -> Mapping[str, str]:
        """Return `page_name` and `tool_name`."""
        return {"page_name": self.page_name, "tool_name": self.tool_name}


class AppDefinitionInvalidError(VibepyError):
    """An App's declaration broke one or more rules; `errors` holds every one found."""

    code = "app.declaration_invalid"

    def __init__(self, app_id: str, errors: Sequence[VibepyError]) -> None:
        """Record `app_id` and the member `errors`, in the order they were found."""
        self.app_id = app_id
        self.errors = tuple(errors)
        codes = ", ".join(error.code for error in self.errors)
        super().__init__(
            f"App {app_id!r} declaration is invalid: {len(self.errors)} violation(s): {codes}"
        )

    def details(self) -> Mapping[str, str]:
        """Return `app_id`, the `count` of members and their `codes`, joined."""
        return {
            "app_id": self.app_id,
            "count": str(len(self.errors)),
            "codes": ", ".join(error.code for error in self.errors),
        }
```

Add to `ERROR_CATALOG` (before `CANCELLED_CODE`):

```python
    ToolChannelsEmptyError.code: ErrorCategory.DECLARATION,
    PageToolUnresolvedError.code: ErrorCategory.DECLARATION,
    PageToolUndeclaredError.code: ErrorCategory.CALLER,
    AppDefinitionInvalidError.code: ErrorCategory.DECLARATION,
```

Replace `report`:

```python
def report(error: Exception, /) -> None:
    """Write one failure where whatever started this process can read it.

    A declaration that failed several ways is written as its aggregate line
    followed by one line per member, so a reader that takes every line that
    validates gets each violation as its own report.
    """
    sys.stderr.write(report_line(to_error_info(error)))
    if isinstance(error, AppDefinitionInvalidError):
        for member in error.errors:
            sys.stderr.write(report_line(to_error_info(member)))
```

In `src/vibepy_core/__init__.py`, import and export the four names in sorted position.

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_errors.py tests/test_package.py -q
```
Expected: all pass. `test_every_value_the_message_interpolates_is_in_details` passes because `count` ("2") and `codes` appear in the message verbatim.

- [ ] **Step 5: Gate and commit**

```bash
make lint typecheck test
git add -A && git commit -m "Four codes exist for what a declaration may break, and a report of an invalid declaration is one line per violation

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: A Tool exposed through no channel cannot be declared

**Files:**
- Modify: `src/vibepy_core/tool/model.py`
- Test: `tests/test_tool_core.py`

**Interfaces:**
- Produces: `ToolDefinition(...)` with `channels=frozenset()` raises `ToolChannelsEmptyError` at construction.

- [ ] **Step 1: Write the failing test**

In `tests/test_tool_core.py`, add `ToolChannelsEmptyError` to the `vibepy_core.errors` import, and add after the model classes:

```python
def test_a_tool_exposed_through_no_channel_cannot_be_declared() -> None:
    """`channels` is where a Tool is reachable; empty has no meaning, unlike empty roles."""
    with pytest.raises(ToolChannelsEmptyError) as error:
        ToolDefinition(
            name="create_todo",
            description="Create a todo",
            input_model=CreateTodoInput,
            output_model=Todo,
            read_only=False,
            channels=frozenset(),
        )

    assert error.value.tool_name == "create_todo"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tool_core.py::test_a_tool_exposed_through_no_channel_cannot_be_declared -q
```
Expected: FAIL, "DID NOT RAISE".

- [ ] **Step 3: Implement**

In `src/vibepy_core/tool/model.py`, import `from vibepy_core.errors import ToolChannelsEmptyError` and add to `ToolDefinition`, after the fields and before `input_schema`:

```python
    def __post_init__(self) -> None:
        """Refuse a declaration exposed through no channel.

        Raises:
            ToolChannelsEmptyError: `channels` is empty.
        """
        if not self.channels:
            raise ToolChannelsEmptyError(self.name)
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_tool_core.py -q
```

- [ ] **Step 5: Gate and commit**

```bash
make lint typecheck test
git add -A && git commit -m "A Tool declares at least one channel, or it is not a declaration

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: A Page declares the Tools it invokes

**Files:**
- Modify: `src/vibepy_core/page/model.py`
- Modify: `src/vibepy_core/app/entrypoint.py`
- Modify every `PageDefinition(` construction: `fixtures/todo-app/src/todo_app/entry.py`, `fixtures/timer-app/src/timer_app/entry.py`, `packages/vibepy-studio/src/vibepy_studio/operating/pages/board.py`, `tests/test_page_core.py`, `tests/test_nicegui_adapter.py`, `tests/test_execution_semantics.py`, `tests/test_app_composition.py`, `tests/test_app_entrypoint.py` (if it constructs one)
- Test: `tests/test_page_core.py`, `tests/test_app_entrypoint.py`

**Interfaces:**
- Produces: `PageDefinition(name, route, title, tools: frozenset[str])`, required, keyword-only like its siblings. `PageDescription.tools: list[str]`, sorted.

- [ ] **Step 1: Write the failing tests**

`tests/test_page_core.py`: change `todos_definition()` to

```python
def todos_definition() -> PageDefinition:
    return PageDefinition(
        name="todos", route="/todos", title="Todos", tools=frozenset({"list_todos", "create_todo"})
    )
```

and extend `test_page_definition_declares_its_metadata` with

```python
    assert definition.tools == frozenset({"list_todos", "create_todo"})
```

Add:

```python
def test_a_page_definition_requires_its_tools() -> None:
    """A Page that invokes nothing says so; the framework does not guess."""
    with pytest.raises(TypeError):
        PageDefinition(name="todos", route="/todos", title="Todos")  # pyright: ignore[reportCallIssue]
```

`tests/test_app_entrypoint.py`: in `test_a_description_carries_every_page_route`, extend the asserted tuples to include `sorted(tools)`; expected `tools` for each page is what the test's definition declares (read the test's definition and write the literal). Add the `tools=` argument to every `PageDefinition(` the file constructs.

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_page_core.py tests/test_app_entrypoint.py -q
```
Expected: TypeError "unexpected keyword argument 'tools'".

- [ ] **Step 3: Implement**

`src/vibepy_core/page/model.py`, `PageDefinition`:

```python
@dataclass(frozen=True, kw_only=True)
class PageDefinition:
    """Static declaration of a Page.

    ``name`` is the identifier the framework addresses the Page by, and it survives a
    route change. ``route`` and ``title`` are consumed by the Web channel adapter.
    ``tools`` names every Tool the handler may invoke: what the body uses is stated
    here, so a reader knows the Page↔Tool relationship without reading the body, and
    the runtime holds the body to it. A Page that invokes nothing declares an empty
    set; there is no default.
    """

    name: str
    route: str
    title: str
    tools: frozenset[str]
```

`src/vibepy_core/app/entrypoint.py`: add `tools: list[str]` to `PageDescription` and `tools=sorted(page.definition.tools)` in `describe()`.

Then every construction site:

| File | `tools=` |
| --- | --- |
| `fixtures/todo-app/.../entry.py` `todos` | `frozenset({"list_todos", "create_todo"})` |
| `fixtures/timer-app/.../entry.py` `home` | `frozenset({"elapsed"})` |
| `board.py` `BOARD` | `frozenset({"list_apps", "install_app", "update_app", "remove_app", "start_app", "stop_app", "describe_config", "configure_app", "register_package_source", "remove_package_source"})` — every Hub Tool; the board calls them through `call(name, …)` |
| `tests/test_execution_semantics.py` `meeting`, `meeting_button` | `frozenset({"meet"})` each (both handlers invoke `meet`) |
| `tests/test_app_composition.py` `journal` | `frozenset({"read"})`; the two `todos` in the name-conflict test: `frozenset()` |
| `tests/test_nicegui_adapter.py` `page()` helper | add a keyword-only parameter `tools: frozenset[str] = frozenset()` and pass it through; the TODO_APP-based test needs nothing |
| `tests/test_page_core.py` other constructions | `frozenset()` unless the handler invokes; the recorder test's page invokes `list_todos` → `todos_definition()` already declares it |

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_page_core.py tests/test_app_entrypoint.py -q
make typecheck
```
pyright will list every remaining `PageDefinition(` without `tools`; fix each.

- [ ] **Step 5: Gate and commit**

```bash
make lint typecheck test
git add -A && git commit -m "A Page declares the Tools its handler invokes, and a description carries them

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: An AppDefinition validates itself at construction

**Files:**
- Modify: `src/vibepy_core/app/model.py`
- Modify: `src/vibepy_core/app/composition.py` (remove checks)
- Modify: `src/vibepy_core/adapters/nicegui/web.py` (remove checks)
- Create: `tests/test_app_conformance.py`
- Modify: `tests/test_app_composition.py` (delete the two conflict tests), `tests/test_nicegui_adapter.py` (delete the three route-refusal tests)

**Interfaces:**
- Produces: `AppDefinition(...)` raises `AppDefinitionInvalidError(app_id, errors)` when any rule breaks; `errors` in declaration order: Tool name conflicts (tool order), then Page name conflicts, route invalid, route conflict, Tool unresolved (page order, and within a page: name, route, then each declared tool sorted).
- `tool_registry_for`, `page_registry_for` and `register_pages` no longer raise declaration errors.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_conformance.py`:

```python
"""What an AppDefinition may be: the rules a declaration is held to as it is constructed.

An invalid declaration cannot exist. Every violation is collected and raised once,
so an author learns them all from one construction, and nothing downstream checks
again. `docs/milestones/M16/spec.md`; ADR-037.
"""

import importlib
import pkgutil
import sys

import pytest
from pydantic import BaseModel

import vibepy_core.app
from lifecycle import no_dependencies
from vibepy_core import Channel
from vibepy_core.app import AppDefinition, AppEntrypoint, NoConfig
from vibepy_core.errors import (
    AppDefinitionInvalidError,
    PageNameConflictError,
    PageRouteConflictError,
    PageRouteInvalidError,
    PageToolUnresolvedError,
    ToolNameConflictError,
)
from vibepy_core.page import Page, PageContext, PageDefinition
from vibepy_core.tool import Tool, ToolContext, ToolDefinition


class Empty(BaseModel):
    pass


async def noop_tool(_ctx: ToolContext[None], _payload: Empty) -> Empty:
    return Empty()


async def noop_page(_ctx: PageContext) -> None:
    return None


def tool(name: str, *, channels: frozenset[Channel] = frozenset(Channel)) -> Tool[None]:
    return Tool(
        definition=ToolDefinition(
            name=name,
            description=name,
            input_model=Empty,
            output_model=Empty,
            read_only=True,
            channels=channels,
        ),
        handler=noop_tool,
    )


def page(name: str, route: str, tools: frozenset[str] = frozenset()) -> Page:
    return Page(
        definition=PageDefinition(name=name, route=route, title=name, tools=tools),
        handler=noop_page,
    )


def definition(tools: list[Tool[None]], pages: list[Page]) -> AppDefinition[None, NoConfig]:
    return AppDefinition(
        app_id="conformance",
        name="Conformance",
        version="0.0.0",
        config=NoConfig,
        tools=tools,
        pages=pages,
    )


def test_a_conforming_declaration_constructs_and_describes_the_same_twice() -> None:
    declared = definition([tool("read"), tool("write")], [page("home", "/", frozenset({"read"}))])

    first = AppEntrypoint(definition=declared, lifespan=no_dependencies).describe()
    second = AppEntrypoint(definition=declared, lifespan=no_dependencies).describe()

    assert first == second
    assert first.pages[0].tools == ["read"]


def test_every_violation_is_collected_and_raised_once() -> None:
    with pytest.raises(AppDefinitionInvalidError) as raised:
        definition(
            [tool("read"), tool("read"), tool("hidden", channels=frozenset({Channel.AGENT}))],
            [
                page("home", "/", frozenset({"read"})),
                page("home", "no-slash", frozenset({"absent", "hidden"})),
                page("list", "/", frozenset()),
            ],
        )

    error = raised.value
    assert error.app_id == "conformance"
    assert [type(member) for member in error.errors] == [
        ToolNameConflictError,
        PageNameConflictError,
        PageRouteInvalidError,
        PageToolUnresolvedError,
        PageToolUnresolvedError,
        PageRouteConflictError,
    ]
    conflict, name, route, absent, hidden, claimed = error.errors
    assert isinstance(conflict, ToolNameConflictError) and conflict.tool_name == "read"
    assert isinstance(name, PageNameConflictError) and name.page_name == "home"
    assert isinstance(route, PageRouteInvalidError) and route.route == "no-slash"
    assert isinstance(absent, PageToolUnresolvedError)
    assert (absent.tool_name, absent.reason) == ("absent", "missing")
    assert isinstance(hidden, PageToolUnresolvedError)
    assert (hidden.tool_name, hidden.reason) == ("hidden", "not_exposed")
    assert isinstance(claimed, PageRouteConflictError)
    assert claimed.route == "/" and {claimed.page_name, claimed.conflicting_page_name} == {
        "home",
        "list",
    }


def test_one_violation_is_raised_in_the_same_shape() -> None:
    with pytest.raises(AppDefinitionInvalidError) as raised:
        definition([tool("read")], [page("home", "home")])

    assert len(raised.value.errors) == 1
    assert isinstance(raised.value.errors[0], PageRouteInvalidError)


def test_a_page_may_invoke_a_tool_exposed_to_the_web_channel_only() -> None:
    declared = definition(
        [tool("read", channels=frozenset({Channel.WEB}))], [page("home", "/", frozenset({"read"}))]
    )

    assert declared.pages[0].definition.tools == frozenset({"read"})


def test_the_rules_import_no_channel_adapter() -> None:
    """The third acceptance criterion: conformance knows no channel implementation."""
    for found in pkgutil.walk_packages(vibepy_core.app.__path__, f"{vibepy_core.app.__name__}."):
        importlib.import_module(found.name)

    assert not any(name.startswith("vibepy_core.adapters") for name in sys.modules)
```

Note on the last test: it holds only if nothing else in the process imported the adapters first; pytest imports test modules in file order and `test_app_conformance.py` sorts before `test_mcp_adapter.py` and `test_nicegui_adapter.py` but after `test_app_composition.py` (which imports no adapter). If the assertion is polluted by an earlier import in a full run, replace the body with a subprocess check:

```python
    result = subprocess.run(
        [sys.executable, "-c", "import vibepy_core.app, sys; "
         "sys.exit(any(n.startswith('vibepy_core.adapters') for n in sys.modules))"],
        check=False,
    )
    assert result.returncode == 0
```

Delete from `tests/test_app_composition.py`: `test_two_pages_declaring_one_name_do_not_open_a_window`, `test_two_tools_declaring_one_name_do_not_open_a_window`, and the now-unused imports (`PageNameConflictError`, `ToolNameConflictError`, and anything else ruff flags). Delete from `tests/test_nicegui_adapter.py`: `test_a_route_that_is_not_a_path_is_rejected`, `test_two_pages_may_not_claim_one_route`, `test_a_rejected_registry_registers_nothing`, and the `PageRouteConflictError`, `PageRouteInvalidError` imports.

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_app_conformance.py -q
```
Expected: `test_every_violation_is_collected_and_raised_once` and `test_one_violation_is_raised_in_the_same_shape` fail with DID NOT RAISE.

- [ ] **Step 3: Implement the rules**

`src/vibepy_core/app/model.py`:

```python
"""Declaration of an App. A value: it holds no resource and no runtime state.

A declaration validates itself as it is constructed, so an invalid one cannot
exist and nothing downstream checks again. The rules that need the whole App --
uniqueness across Tools and Pages, a Page's reference to a Tool -- run here,
because this is the one object that holds every Tool and Page. ADR-037.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from vibepy_core.app.config import AppConfig, NoConfig
from vibepy_core.channel import Channel
from vibepy_core.errors import (
    AppDefinitionInvalidError,
    PageNameConflictError,
    PageRouteConflictError,
    PageRouteInvalidError,
    PageToolUnresolvedError,
    ToolNameConflictError,
    VibepyError,
)
from vibepy_core.page.model import Page
from vibepy_core.tool.policy import ToolPolicy
from vibepy_core.tool.runtime import Tool

__all__ = ["AppConfig", "AppDefinition", "NoConfig"]


@dataclass(frozen=True, kw_only=True)
class AppDefinition[DepsT, ConfigT: AppConfig]:
    """Everything a channel needs to know about an App without running it.

    (keep the existing docstring body, then add:)

    Constructing one runs every cross-declaration rule and raises
    `AppDefinitionInvalidError` carrying each violation found, in declaration
    order. A definition that exists therefore conforms.
    """

    app_id: str
    name: str
    version: str
    config: type[ConfigT]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
    policy: ToolPolicy | None = None

    def __post_init__(self) -> None:
        """Hold the declaration to its rules; collect every violation, raise once.

        Raises:
            AppDefinitionInvalidError: at least one rule is broken; `errors` holds all.
        """
        found = [*_tool_violations(self.tools), *_page_violations(self.tools, self.pages)]
        if found:
            raise AppDefinitionInvalidError(self.app_id, found)


def _tool_violations[DepsT](tools: Sequence[Tool[DepsT]], /) -> list[VibepyError]:
    """Two Tools may not share a name: a channel would publish two and answer both with one."""
    seen: set[str] = set()
    found: list[VibepyError] = []
    for tool in tools:
        name = tool.definition.name
        if name in seen:
            found.append(ToolNameConflictError(name))
        seen.add(name)
    return found


def _page_violations[DepsT](tools: Sequence[Tool[DepsT]], pages: Sequence[Page], /) -> list[VibepyError]:
    """Names and routes unique, routes rooted, and every declared Tool present and on the Web."""
    web_tools = {t.definition.name for t in tools if Channel.WEB in t.definition.channels}
    all_tools = {t.definition.name for t in tools}
    names: dict[str, str] = {}
    routes: dict[str, str] = {}
    found: list[VibepyError] = []
    for page in pages:
        declared = page.definition
        owner_route = names.get(declared.name)
        if owner_route is not None:
            found.append(PageNameConflictError(declared.name, owner_route, declared.route))
        else:
            names[declared.name] = declared.route
        if not declared.route.startswith("/"):
            found.append(PageRouteInvalidError(declared.name, declared.route))
        else:
            owner_name = routes.get(declared.route)
            if owner_name is not None:
                found.append(PageRouteConflictError(declared.route, owner_name, declared.name))
            else:
                routes[declared.route] = declared.name
        for tool_name in sorted(declared.tools):
            if tool_name not in all_tools:
                found.append(PageToolUnresolvedError(declared.name, tool_name, reason="missing"))
            elif tool_name not in web_tools:
                found.append(
                    PageToolUnresolvedError(declared.name, tool_name, reason="not_exposed")
                )
    return found
```

Check the order this produces against the test: page "home"/"/" → nothing; page "home"/"no-slash" → name conflict, route invalid, `absent` missing, `hidden` not_exposed; page "list"/"/" → route conflict. Tool conflicts first. Matches the assertion.

Circular import check: `vibepy_core.app.model` already imports `vibepy_core.tool.runtime`; `vibepy_core.channel` and `vibepy_core.errors` import nothing from `app`. Fine.

- [ ] **Step 4: Remove the downstream checks**

`src/vibepy_core/app/composition.py`:

```python
def tool_registry_for[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT], /
) -> ToolRegistry[DepsT]:
    """Fill a ToolRegistry from declarations. Reads no resource.

    Names are unique: the definition refused any other declaration as it was
    constructed, so this registers and checks nothing.
    """
    registry: ToolRegistry[DepsT] = ToolRegistry()
    for tool in definition.tools:
        registry.register(tool)
    return registry


def page_registry_for[DepsT, ConfigT: AppConfig](
    definition: AppDefinition[DepsT, ConfigT], /
) -> PageRegistry:
    """Fill a PageRegistry from declarations. Reads no resource; the definition already conforms."""
    registry = PageRegistry()
    for page in definition.pages:
        registry.register(page)
    return registry
```

Remove the `PageNameConflictError, ToolNameConflictError` imports.

`src/vibepy_core/adapters/nicegui/web.py`: delete the validation loop and the two error imports; `register_pages` keeps only the registering loop. Rewrite the module docstring's first paragraph to: "The builders close over the PageRuntime the caller's window yielded. Registration therefore happens inside that window, and a builder can only render while its runtime lives. A declaration reaching here already conforms — the definition refused any other as it was constructed — so nothing is validated before registration."

- [ ] **Step 5: Run to verify pass**

```bash
uv run pytest tests/test_app_conformance.py tests/test_app_composition.py tests/test_nicegui_adapter.py -q
```

- [ ] **Step 6: Gate and commit**

```bash
make lint typecheck test
git add -A && git commit -m "An AppDefinition holds itself to every cross-declaration rule as it is constructed, so a window and the Web adapter register what they are handed

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: A Page can invoke only the Tools it declared

**Files:**
- Modify: `src/vibepy_core/page/runtime.py`
- Test: `tests/test_page_core.py`

**Interfaces:**
- Produces: `PageRuntime.render` binds `page.definition.tools` into the invoker; `invoke(name)` with `name` outside them raises `PageToolUndeclaredError(page_name, name)` without reaching the underlying invoker.

- [ ] **Step 1: Write the failing test**

In `tests/test_page_core.py`, add `PageToolUndeclaredError` to the errors import and, after `test_render_binds_the_principal_into_the_pages_invoker`:

```python
async def test_a_page_may_not_invoke_a_tool_it_did_not_declare() -> None:
    """The declaration is an allow-list: what the body did not declare, it cannot reach."""
    recorder = RecordingInvoker()
    seen: list[PageToolUndeclaredError] = []

    async def handler(ctx: PageContext) -> None:
        try:
            await ctx.tools.invoke("remove_todo", {})
        except PageToolUndeclaredError as error:
            seen.append(error)

    registry = PageRegistry()
    registry.register(Page(definition=todos_definition(), handler=handler))
    runtime = PageRuntime(registry=registry, tools=recorder)

    await runtime.render("todos", principal=Principal(id="alice"))

    assert recorder.calls == []
    assert [(e.page_name, e.tool_name) for e in seen] == [("todos", "remove_todo")]
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_page_core.py::test_a_page_may_not_invoke_a_tool_it_did_not_declare -q
```
Expected: FAIL — the recorder is reached (AssertionError from the fixture), `seen` empty.

- [ ] **Step 3: Implement**

`src/vibepy_core/page/runtime.py`:

```python
from vibepy_core.errors import PageToolUndeclaredError
...

class _BoundInvoker:
    """A ToolInvoker bound to one principal and one Page's declared Tools. Built per render."""

    def __init__(
        self, tools: PrincipalToolInvoker, principal: Principal, *, page: str, declared: frozenset[str]
    ) -> None:
        """Hold the invoker to reach, the `principal` every call carries, and what `page` declared."""
        self._tools = tools
        self._principal = principal
        self._page = page
        self._declared = declared

    def invoke(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]:
        """Invoke `name` as the bound principal, if the Page declared it.

        Raises:
            PageToolUndeclaredError: `name` is not among the Page's declared Tools.
        """
        if name not in self._declared:
            raise PageToolUndeclaredError(self._page, name)
        return self._tools.invoke(name, raw_input, principal=self._principal)
```

and in `render`:

```python
        page = self._registry.resolve(name)
        bound: ToolInvoker = _BoundInvoker(
            self._tools, principal, page=name, declared=page.definition.tools
        )
```

`invoke` raises synchronously before returning an awaitable; a Page awaits the call expression, so the exception surfaces at the `await` site as the test expects. Update the module docstring's last paragraph: "…binds it into the invoker the Page receives, together with the Tools the Page declared, so a Page cannot choose whom it invokes as nor reach what it did not declare."

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_page_core.py -q
```

- [ ] **Step 5: Gate and commit**

```bash
make lint typecheck test
git add -A && git commit -m "A Page reaches only the Tools it declared; an undeclared name is refused before ToolRuntime

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: describe writes one line per violation

**Files:**
- Test: `tests/test_describe_command.py`
- (No source change expected; `describe` already calls `report`. This task proves the boundary.)

- [ ] **Step 1: Write the test**

Append to `tests/test_describe_command.py`:

```python
BROKEN_ENTRY = '''
from pydantic import BaseModel

from vibepy_core import (
    AppDefinition, AppEntrypoint, NoConfig, Page, PageContext, PageDefinition,
    Tool, ToolContext, ToolDefinition,
)


class Empty(BaseModel):
    pass


async def read(_ctx: ToolContext[None], _payload: Empty) -> Empty:
    return Empty()


async def home(_ctx: PageContext) -> None:
    return None


def tool(name: str) -> Tool[None]:
    return Tool(
        definition=ToolDefinition(
            name=name, description=name, input_model=Empty, output_model=Empty, read_only=True
        ),
        handler=read,
    )


def app_definition():
    return AppDefinition(
        app_id="broken-app",
        name="Broken",
        version="0.0.0",
        config=NoConfig,
        tools=[tool("read"), tool("read")],
        pages=[
            Page(
                definition=PageDefinition(
                    name="home", route="home", title="Home", tools=frozenset({"absent"})
                ),
                handler=home,
            )
        ],
    )


async def lifespan(_config: NoConfig):
    yield None


APP = AppEntrypoint(definition=app_definition(), lifespan=lifespan)
'''


@pytest.mark.integration
def test_an_invalid_declaration_is_every_violation_as_its_own_line(tmp_path: Path) -> None:
    """`validate_app` reads these lines; each is one violation an author can act on."""
    write_distribution(
        tmp_path,
        distribution="broken-app",
        version="0.1.0",
        entries=[("broken", "broken_app.entry:APP")],
    )
    package = tmp_path / "broken_app"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entry.py").write_text(BROKEN_ENTRY, encoding="utf-8")

    result = run_describe(tmp_path)

    assert result.returncode == 1
    reported = [json.loads(line) for line in result.stderr.splitlines() if line.startswith("{")]
    assert [entry["code"] for entry in reported] == [
        "app.declaration_invalid",
        "tool.name_conflict",
        "page.route_invalid",
        "page.tool_unresolved",
    ]
    assert reported[0]["details"]["count"] == "3"
    assert reported[3]["details"] == {"page_name": "home", "tool_name": "absent", "reason": "missing"}
```

`lifespan` above is an async generator, not an `asynccontextmanager`; `describe` never enters it, and the module is a test artefact read by a subprocess, not by pyright (it is a string).

- [ ] **Step 2: Run**

```bash
uv run pytest tests/test_describe_command.py -q -m integration
```
Expected: PASS. If `AppDefinitionInvalidError` propagates out of the import as a bare traceback rather than a report, `describe.main` is catching `VibepyError` — it is one, so it is reported. If stderr carries a leading traceback from the import, the JSON filter above skips it.

- [ ] **Step 3: Commit**

```bash
make lint typecheck test
git add -A && git commit -m "describe reports an invalid declaration as one line per violation, which a host reads one by one

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Studio reads every report line

**Files:**
- Modify: `packages/vibepy-studio/src/vibepy_studio/internals/processes.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/internals/describing.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/internals/__init__.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/authoring/tools/inspection.py` (adapt to `reports`)
- Test: `packages/vibepy-studio/tests/test_processes.py`, `packages/vibepy-studio/tests/test_describing.py`

**Interfaces:**
- Produces: `reports(text: str, /) -> tuple[ErrorInfo, ...]` — every report line, in order. `reported(text) -> ErrorInfo | None` — the first of them, or `None`. `DescribeFailed.reports: tuple[ErrorInfo, ...]` replaces `.reported`; `DescribeFailed.reported` property returns the first or `None` for the two callers that show one.

- [ ] **Step 1: Write the failing tests**

`packages/vibepy-studio/tests/test_processes.py`: import `reports` beside `reported`; add

```python
def test_reports_reads_every_report_line_in_order() -> None:
    text = (
        '{"code": "app.declaration_invalid", "category": "declaration", "message": "m",'
        ' "details": {"count": "1"}}\n'
        '{"code": "tool.name_conflict", "category": "declaration", "message": "m",'
        ' "details": {}}\nTraceback\n'
    )
    found = reports(text)
    assert [info.code for info in found] == ["app.declaration_invalid", "tool.name_conflict"]
    assert reported(text) is not None and reported(text).code == "app.declaration_invalid"
    assert reports("nothing here") == ()
```

Rename `test_reported_reads_the_last_report_among_other_lines` to `test_reported_reads_the_report_among_other_lines` (its body stands).

`packages/vibepy-studio/tests/test_describing.py`: in `test_a_command_that_exits_without_a_report_fails_to_describe`, assert `failed.value.reports == ()` in addition to `failed.value.reported is None`.

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest packages/vibepy-studio/tests/test_processes.py packages/vibepy-studio/tests/test_describing.py -q
```

- [ ] **Step 3: Implement**

`processes.py`:

```python
def reports(text: str, /) -> tuple[ErrorInfo, ...]:
    """Return every failure a child described in `text`, in the order it wrote them.

    A report is one line among whatever else the child wrote; a declaration that
    failed several ways is several lines. Parsing rather than position finds them,
    and what does not validate -- a traceback, the Web technology's lines -- is
    skipped.
    """
    return tuple(found for line in text.splitlines() if (found := read_report_line(line)))


def reported(text: str, /) -> ErrorInfo | None:
    """Return the first failure a child described in `text`, or nothing.

    The first is the whole story when a child failed once, and the aggregate when
    it failed several ways; a caller that shows one line shows this one.
    """
    found = reports(text)
    return found[0] if found else None
```

`describing.py`:

```python
class DescribeFailed(Exception):
    """The command did not describe. Carries what it wrote and every report among it."""

    def __init__(self, output: str, *, reports: tuple[ErrorInfo, ...]) -> None:
        """Record `output` for the message and the child's `reports`, in order."""
        super().__init__(output)
        self.output = output
        self.reports = reports

    @property
    def reported(self) -> ErrorInfo | None:
        """The first report, for a caller that shows one failure."""
        return self.reports[0] if self.reports else None
```

and in `describe`: `reports=reports(completed.stderr)` / `reports=()`. Export `reports` from `internals/__init__.py`. `inspection.py` keeps using `failed.reported` for now (Task 8 changes it).

- [ ] **Step 4: Run to verify pass, gate, commit**

```bash
make lint typecheck test
git add -A && git commit -m "Studio reads every report line a child writes, and a caller that shows one shows the first

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: The authoring vocabulary: Severity, Diagnostic, AppValidation; inspect_app carries a list

**Files:**
- Modify: `packages/vibepy-studio/src/vibepy_studio/authoring/models.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/authoring/tools/inspection.py`
- Test: `packages/vibepy-studio/tests/test_inspect_app.py`, `packages/vibepy-studio/tests/test_authoring_over_mcp.py`

**Interfaces:**
- Produces, in `authoring/models.py`:

```python
class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"

class Diagnostic(BaseModel):
    severity: Severity
    error: ErrorInfo

class ValidateRequest(BaseModel):
    project: PurePath

class AppValidation(BaseModel):
    conforms: bool
    diagnostics: list[Diagnostic]

class AppInspection(BaseModel):
    apps: list[DescribedApp]
    diagnostics: list[ErrorInfo] = []

def type_error(project: PurePath, *, file: str, line: int, rule: str | None, message: str) -> ErrorInfo
    # code "authoring.type_error", category DECLARATION, details {"project", "file", "line", "rule"} (rule omitted when None)

def validation(diagnostics: Sequence[Diagnostic], /) -> AppValidation
    # conforms = not any(d.severity is Severity.ERROR ...)
```

- [ ] **Step 1: Write the failing tests**

`test_inspect_app.py`: replace every `inspected.diagnostic` with the list form:

```python
    assert inspected.diagnostics == [], inspected.diagnostics
```
```python
    assert [d.code for d in inspected.diagnostics] == ["authoring.project_not_found"]
    assert inspected.diagnostics[0].category == ErrorCategory.CALLER
```
```python
    assert [d.code for d in inspected.diagnostics] == ["authoring.environment_failed"]
    assert inspected.diagnostics[0].category == ErrorCategory.EXECUTION
    assert "vibepy_core" in inspected.diagnostics[0].message
```

Add to `test_inspect_app.py`:

```python
@pytest.mark.integration
async def test_an_invalid_declaration_is_inspected_as_every_violation(tmp_path: Path) -> None:
    project = broken_project(tmp_path / "broken")
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        inspected = await tools.invoke("inspect_app", {"project": str(project)}, principal=AGENT)
    assert isinstance(inspected, AppInspection)
    assert inspected.apps == []
    assert [d.code for d in inspected.diagnostics] == [
        "app.declaration_invalid",
        "tool.name_conflict",
        "page.route_invalid",
        "page.tool_unresolved",
    ]
```

`broken_project` goes in `tests_support.py`, because Task 9's tests use it too:

```python
BROKEN_ENTRY = '''
from pydantic import BaseModel

from vibepy_core import (
    AppDefinition, AppEntrypoint, NoConfig, Page, PageContext, PageDefinition,
    Tool, ToolContext, ToolDefinition,
)


class Empty(BaseModel):
    pass


def read(_ctx: ToolContext[None], _payload: Empty) -> Empty:  # not async: pyright's one error
    return Empty()


async def home(_ctx: PageContext) -> None:
    return None


def tool(name: str) -> Tool[None]:
    return Tool(
        definition=ToolDefinition(
            name=name, description=name, input_model=Empty, output_model=Empty, read_only=True
        ),
        handler=read,
    )


def app_definition():
    return AppDefinition(
        app_id="broken-app",
        name="Broken",
        version="0.0.0",
        config=NoConfig,
        tools=[tool("read"), tool("read")],
        pages=[
            Page(
                definition=PageDefinition(
                    name="home", route="home", title="Home", tools=frozenset({"absent"})
                ),
                handler=home,
            )
        ],
    )


async def lifespan(_config: NoConfig):
    yield None


APP = AppEntrypoint(definition=app_definition(), lifespan=lifespan)
'''


def broken_project(root: Path, /) -> Path:
    """A source project whose declaration breaks three rules and whose handler is not async.

    It depends on this repository's `vibepy-core` by path, so `uv run --project`
    resolves it without the workspace.
    """
    (root / "src" / "broken_app").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "broken-app"\nversion = "0.0.0"\nrequires-python = ">=3.12"\n'
        'dependencies = ["vibepy-core"]\n'
        '[project.entry-points."vibepy.apps"]\nbroken-app = "broken_app.entry:APP"\n'
        '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
        '[tool.hatch.build.targets.wheel]\npackages = ["src/broken_app"]\n'
        f'[tool.uv.sources]\nvibepy-core = {{ path = "{REPO.as_posix()}", editable = true }}\n',
        encoding="utf-8",
    )
    (root / "src" / "broken_app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "broken_app" / "entry.py").write_text(BROKEN_ENTRY, encoding="utf-8")
    return root
```

The literal differs from Task 6's only in `read` lacking `async`. They are test data in two files testing two subjects, not a shared module.

`test_authoring_over_mcp.py`: in `test_an_expected_failure_arrives_as_structured_data`, the structured content now has `diagnostics` as a list — adapt the assertion to `structured["diagnostics"][0]["code"] == "authoring.project_not_found"` (read the current assertion and mirror it).

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest packages/vibepy-studio/tests/test_inspect_app.py -q
```

- [ ] **Step 3: Implement**

`authoring/models.py`: extend the module docstring table with

```
| `authoring.type_error` | declaration | pyright reported this, at its own severity; `file`, |
|  |  | `line` (1-based) and `rule` say where and which |
```

Add imports `from collections.abc import Sequence`, `from enum import StrEnum`. Add the classes and functions from the Interfaces block above. `type_error`:

```python
def type_error(
    project: PurePath, *, file: str, line: int, rule: str | None, message: str
) -> ErrorInfo:
    """Carry one pyright diagnostic as the framework's shape; pyright's sentence is the message."""
    details = {"project": str(project), "file": file, "line": str(line)}
    if rule is not None:
        details["rule"] = rule
    return ErrorInfo(
        code="authoring.type_error", category=ErrorCategory.DECLARATION, message=message, details=details
    )


def validation(diagnostics: Sequence[Diagnostic], /) -> AppValidation:
    """Say whether the project conforms: no diagnostic of severity `error`."""
    return AppValidation(
        conforms=not any(d.severity is Severity.ERROR for d in diagnostics),
        diagnostics=list(diagnostics),
    )
```

`AppInspection.diagnostic: ErrorInfo | None = None` → `diagnostics: list[ErrorInfo] = []`.

`inspection.py`, `inspect_app`: each `AppInspection(apps=[], diagnostic=X)` becomes `AppInspection(apps=[], diagnostics=[X])`, except the `DescribeFailed` arm:

```python
    except DescribeFailed as failed:
        if failed.reports:
            return AppInspection(
                apps=[],
                diagnostics=[diagnostic_of(info, project=str(project)) for info in failed.reports],
            )
        return AppInspection(apps=[], diagnostics=[environment_failed(project, failed.output)])
```

`from_report` in `models.py` is then unused by `inspection.py`; `invocation.py` still uses it — leave it.

- [ ] **Step 4: Run to verify pass, gate, commit**

```bash
make lint typecheck test
git add -A && git commit -m "inspect_app says every reason a declaration did not load, and the authoring vocabulary has a Diagnostic with a severity

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: validate_app

**Files:**
- Create: `packages/vibepy-studio/src/vibepy_studio/authoring/internals/typechecking.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/authoring/internals/__init__.py`
- Create: `packages/vibepy-studio/src/vibepy_studio/authoring/tools/validation.py`
- Modify: `packages/vibepy-studio/src/vibepy_studio/authoring/tools/__init__.py`
- Create: `packages/vibepy-studio/tests/test_validate_app.py`
- Modify: `packages/vibepy-studio/tests/test_authoring_over_mcp.py`

**Interfaces:**
- Consumes: `describe`, `DescribeFailed.reports`, `NotRunnable`, `run`, `python(project)`, `locate`, `declared_name`, and Task 8's models.
- Produces:
  - `typechecking.py`: `class TypecheckFailed(Exception)` with `output: str`; `async def typecheck(project: PurePath, /) -> tuple[PyrightDiagnostic, ...]` where `PyrightDiagnostic` is a pydantic model of the fields read: `file: str`, `severity: Severity`, `message: str`, `range: PyrightRange` (`start: PyrightPosition` with `line: int`), `rule: str | None = None`. The command is `["uv", "run", "--project", str(project), "--with", "pyright[nodejs]", "pyright", "--outputjson", "-p", str(project)]`. Exit 0 and 1 → parse stdout; anything else → `TypecheckFailed(stdout + stderr)`.
  - `validation.py`: `async def validate_app(_ctx: ToolContext[object], payload: ValidateRequest) -> AppValidation`; `VALIDATION_TOOLS: Sequence[Tool[object]]` with one Tool `validate_app`, `read_only=True`, `channels=frozenset({Channel.AGENT})`, description "Hold a source project to the framework's declaration rules and its typed contracts, in the project's own environment".

- [ ] **Step 1: Write the failing tests**

`packages/vibepy-studio/tests/test_validate_app.py`:

```python
"""What does not conform in a source project, read in the project's own environment."""

from pathlib import Path

import pytest

from tests_support import AGENT, FIXTURES, broken_project, studio
from vibepy_core import Channel, ErrorCategory
from vibepy_studio.authoring.models import AppValidation, Severity


@pytest.mark.integration
async def test_a_conforming_project_conforms(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        validated = await tools.invoke(
            "validate_app", {"project": str(FIXTURES / "todo-app")}, principal=AGENT
        )
    assert isinstance(validated, AppValidation)
    assert validated.conforms, validated.diagnostics
    assert [d for d in validated.diagnostics if d.severity is Severity.ERROR] == []


@pytest.mark.integration
async def test_every_violation_and_every_type_error_is_one_diagnostic(tmp_path: Path) -> None:
    project = broken_project(tmp_path / "broken")
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        validated = await tools.invoke("validate_app", {"project": str(project)}, principal=AGENT)
    assert isinstance(validated, AppValidation)
    assert not validated.conforms
    codes = [d.error.code for d in validated.diagnostics]
    assert codes[:3] == ["tool.name_conflict", "page.route_invalid", "page.tool_unresolved"]
    assert "app.declaration_invalid" not in codes
    typed = [d for d in validated.diagnostics if d.error.code == "authoring.type_error"]
    assert typed, codes
    assert all(d.severity is Severity.ERROR for d in validated.diagnostics[:3])
    first = typed[0].error
    assert first.category is ErrorCategory.DECLARATION
    assert first.details["file"].endswith("entry.py")
    assert first.details["line"].isdigit()
    assert first.details.get("rule") == "reportArgumentType"


async def test_a_directory_without_a_pyproject_is_not_a_project(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        validated = await tools.invoke(
            "validate_app", {"project": str(tmp_path / "nowhere")}, principal=AGENT
        )
    assert isinstance(validated, AppValidation)
    assert not validated.conforms
    assert [d.error.code for d in validated.diagnostics] == ["authoring.project_not_found"]
```

`test_authoring_over_mcp.py`: add `"validate_app"` to the discoverable names (sorted position) and `"validate_app": True` to the read-only hints.

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest packages/vibepy-studio/tests/test_validate_app.py -q
```
Expected: `ToolNotFoundError` for `validate_app`.

- [ ] **Step 3: Implement typechecking**

`authoring/internals/typechecking.py`:

```python
"""Running the type checker over a source project, in that project's environment.

The framework's contracts for a handler, a configuration and a lifespan are
types, and PEP 484 places their checking in an offline type checker. pyright is
that authority here, as it is for this repository. `uv run --with` lays it over
the project's own environment for one invocation, so the project's
`pyproject.toml`, lock and environment are untouched and the project's own
`[tool.pyright]`, or pyright's default `standard` mode, applies.

pyright's `--outputjson` is read as the shape it documents; nothing is dropped.
"""

import logging
from collections.abc import Sequence
from pathlib import PurePath

from pydantic import BaseModel, ValidationError

from vibepy_studio.authoring.models import Severity
from vibepy_studio.internals import run

logger = logging.getLogger(__name__)

PYRIGHT = "pyright[nodejs]"
"""The distribution `uv run --with` injects: pyright with Node bundled as wheels."""


class PyrightPosition(BaseModel):
    """A zero-based line, as pyright writes it."""

    line: int


class PyrightRange(BaseModel):
    """Where a diagnostic starts; the end is not read."""

    start: PyrightPosition


class PyrightDiagnostic(BaseModel):
    """One entry of `generalDiagnostics`, the fields read."""

    file: str
    severity: Severity
    message: str
    range: PyrightRange
    rule: str | None = None


class PyrightOutput(BaseModel):
    """What `--outputjson` writes, the part read."""

    generalDiagnostics: list[PyrightDiagnostic]  # noqa: N815 - pyright's own field name


class TypecheckFailed(Exception):
    """pyright did not answer: it exited with a code that is not a verdict."""

    def __init__(self, output: str) -> None:
        """Record what pyright wrote."""
        super().__init__(output)
        self.output = output


def command(project: PurePath, /) -> list[str]:
    """The command that type-checks `project` inside its environment. Pure."""
    return [
        "uv", "run", "--project", str(project), "--with", PYRIGHT,
        "pyright", "--outputjson", "-p", str(project),
    ]


async def typecheck(project: PurePath, /) -> Sequence[PyrightDiagnostic]:
    """Return every diagnostic pyright reports for `project`, at pyright's own severity.

    Raises:
        NotRunnable: uv is not runnable.
        TypecheckFailed: pyright exited 2, 3 or 4, or wrote something that is not its JSON.
    """
    completed = await run(command(project))
    if completed.returncode not in (0, 1):
        raise TypecheckFailed((completed.stdout + completed.stderr).strip())
    try:
        return PyrightOutput.model_validate_json(completed.stdout).generalDiagnostics
    except ValidationError as invalid:
        logger.debug("pyright wrote something other than its JSON", exc_info=invalid)
        raise TypecheckFailed(completed.stdout.strip()) from invalid
```

Export `TypecheckFailed`, `typecheck` from `authoring/internals/__init__.py`.

- [ ] **Step 4: Implement the Tool**

`authoring/tools/validation.py`:

```python
"""Holding a source project to what the framework requires of an App."""

import logging
from collections.abc import Sequence

from vibepy_core.channel import Channel
from vibepy_core.errors import ErrorInfo
from vibepy_core.tool import Tool, ToolContext, ToolDefinition
from vibepy_studio.authoring.internals import (
    TypecheckFailed,
    declared_name,
    locate,
    python,
    typecheck,
)
from vibepy_studio.authoring.models import (
    AppValidation,
    Diagnostic,
    Severity,
    ValidateRequest,
    environment_failed,
    project_not_found,
    type_error,
    uv_unavailable,
    validation,
)
from vibepy_studio.internals import DescribeFailed, NotRunnable, describe
from vibepy_studio.models import diagnostic_of

logger = logging.getLogger(__name__)


def _error(info: ErrorInfo, /) -> Diagnostic:
    return Diagnostic(severity=Severity.ERROR, error=info)


async def validate_app(_ctx: ToolContext[object], payload: ValidateRequest) -> AppValidation:
    """Report every declaration violation and every type diagnostic of a source project.

    Two authorities, run independently in the project's environment: the
    framework's own `describe`, whose failure path is the declaration rules, and
    pyright, whose diagnostics are the typed contracts. Each finding is one
    `Diagnostic`; the project conforms when none is an error.
    """
    project = await locate(payload.project)
    if project is None:
        return validation([_error(project_not_found(payload.project, "holds no pyproject.toml"))])
    if await declared_name(project) is None:
        return validation([_error(project_not_found(project, "declares no [project] name"))])

    found: list[Diagnostic] = []
    try:
        await describe(python(project))
    except NotRunnable:
        return validation([_error(uv_unavailable(project))])
    except DescribeFailed as failed:
        members = [info for info in failed.reports if info.code != "app.declaration_invalid"]
        if members:
            found.extend(_error(diagnostic_of(info, project=str(project))) for info in members)
        else:
            found.append(_error(environment_failed(project, failed.output)))

    try:
        for entry in await typecheck(project):
            found.append(
                Diagnostic(
                    severity=entry.severity,
                    error=type_error(
                        project,
                        file=entry.file,
                        line=entry.range.start.line + 1,
                        rule=entry.rule,
                        message=entry.message,
                    ),
                )
            )
    except NotRunnable:
        found.append(_error(uv_unavailable(project)))
    except TypecheckFailed as failed:
        found.append(_error(environment_failed(project, failed.output)))
    return validation(found)


VALIDATION_TOOLS: Sequence[Tool[object]] = [
    Tool(
        definition=ToolDefinition(
            name="validate_app",
            description=(
                "Hold a source project to the framework's declaration rules and its typed "
                "contracts, in the project's own environment"
            ),
            input_model=ValidateRequest,
            output_model=AppValidation,
            read_only=True,
            channels=frozenset({Channel.AGENT}),
        ),
        handler=validate_app,
    ),
]
```

`authoring/tools/__init__.py`: import `VALIDATION_TOOLS, validate_app` and extend `AUTHORING_TOOLS = [*INSPECTION_TOOLS, *INVOCATION_TOOLS, *VALIDATION_TOOLS]` and `__all__`.

- [ ] **Step 5: Run to verify pass**

```bash
uv run pytest packages/vibepy-studio/tests/test_validate_app.py packages/vibepy-studio/tests/test_authoring_over_mcp.py -q
```
The first run downloads pyright and Node into uv's cache; allow minutes. If `typecheck` of `todo-app` reports errors under `standard`, read them: they are real findings in the fixture and are fixed in the fixture, not silenced.

- [ ] **Step 6: Gate and commit**

```bash
make lint typecheck test
git add -A && git commit -m "validate_app holds a source project to the declaration rules and to pyright, each finding one Diagnostic at its own severity

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: ADR-037

**Files:**
- Create: `docs/decisions/ADR-037-an-app-declaration-validates-itself-at-construction.md`
- Modify: `docs/decisions/ADR-012-nicegui-adapter-registers-routes.md` (status line only)

- [ ] **Step 1: Write the record**

Nygard format, `Status: Accepted`, dated 2026-09-12. Context: the table from the spec's Problem section (where each rule was enforced, first-violation-only, one Web-only); the authoring loop learning one problem per run; `authoring.md` deferring `validate_app`. Conventions consulted: Python `dataclasses` post-init, attrs validators, pydantic `ValidationError` collecting all, PEP 484 non-goals, Django system checks, Angular `imports`, Relay data masking, Next.js running the project's type checker, uv `--with`. Decision: the three-row table from the spec's Principle (value rule → declaring dataclass; cross-declaration → `AppDefinition`; typed contract → pyright run by `validate_app`); `PageDefinition.tools` as an allow-list held at render; one aggregate exception; no fifth command; `Diagnostic` distinct from `ErrorInfo`. Consequences: an invalid declaration cannot exist; windows and adapters trust; route validation is channel-neutral; every App declaring a Page adds `tools=`; `validate_app` downloads pyright once per machine; handlers admit only what the type checker admits; a framework warning one day moves `Diagnostic` to core. Supersedes: "ADR-012's statement that the adapter validates route format and uniqueness."

- [ ] **Step 2: Mark ADR-012**

Under its `Status: Accepted` line append: `Amended by ADR-037: route validation is the declaration's, not the adapter's; registration stands as recorded.`

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "ADR-037 records why an App declaration validates itself at construction, and why the type checker is run by the authoring Tool

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: Architecture documents

**Files:** `docs/architecture/errors.md`, `page-model.md`, `tool-model.md`, `app-model.md`, `adapters.md`, `packaging.md`, `authoring.md`.

- [ ] **Step 1: errors.md** — add four rows to the Codes table (`tool.channels_empty` declaration `ToolChannelsEmptyError`; `page.tool_unresolved` declaration `PageToolUnresolvedError`; `page.tool_undeclared` caller `PageToolUndeclaredError`; `app.declaration_invalid` declaration `AppDefinitionInvalidError`). After the table: one paragraph — `app.declaration_invalid` carries its members; `report` writes it as one line then one per member. Note `authoring.type_error` is Studio's vocabulary, defined in `vibepy_studio/authoring/models.py`, not here.

- [ ] **Step 2: page-model.md** — PageDefinition: add `tools` to the metadata list; replace "route format and route uniqueness are both validated where routes are registered, not in the core Page model" with "route format, route uniqueness, and that each declared Tool exists and is exposed to the Web channel are validated as the `AppDefinition` holding the Page is constructed (`docs/architecture/app-model.md`)". ToolInvoker: add "A Page reaches only the Tools its declaration names; any other name is `page.tool_undeclared`, refused before ToolRuntime. The declaration is an allow-list, and `describe` publishes it." Add `PageToolUndeclaredError` to the errors sentence.

- [ ] **Step 3: tool-model.md** — under `channels`: "non-empty; a declaration exposed through no channel is refused as it is constructed (`tool.channels_empty`)". ToolRegistry: replace "A declaration carrying one name twice never reaches the registry: the window refuses it where it builds one" with "…never reaches the registry: the `AppDefinition` refuses it as it is constructed".

- [ ] **Step 4: app-model.md** — new subsection after AppDefinition, "Construction validates": the principle paragraph and the three-row table from the spec; the aggregate; "a window, `describe` and an adapter check nothing; they trust what exists". Invariants: add "An AppDefinition that exists conforms; no rule is checked twice."

- [ ] **Step 5: adapters.md** — remove "Route format and route uniqueness are validated here, which is where … a rejected registry leaves no half-registered app behind" (lines ~79–81); say instead "A declaration reaching the adapter already conforms; the adapter registers."

- [ ] **Step 6: packaging.md** — "What a command writes to standard error": "a report (`ErrorInfo`, one per failure …; a declaration that fails several ways is its aggregate line followed by one line per violation)". Inspection and loading: `PageDescription` "carries the Page's declared `tools`".

- [ ] **Step 7: authoring.md** — Framework responsibility: "type validation" → "type validation, delegated to pyright and run by `validate_app`". Tool table: add row `validate_app | Agent | every declaration violation and every pyright diagnostic of the project, each a `Diagnostic` at its severity, and whether the project conforms`. Replace "Inspection and validation are one Tool: what the framework validates today is that a declaration loads, and that is the failure path of describing." with "Validation is the failure path of describing, permanently: a declaration validates itself as it is constructed, so what `describe` reports when it cannot describe is the list of violations, and `validate_app` reads it beside pyright's." Capability table: `inspect_framework, inspect_app, invoke_tool | Studio, M12` and new row `validate_app | Studio, M16`; `run_conformance_tests | unassigned`; add `type validation | pyright, run by validate_app (M16)`. "It should not duplicate…" paragraph unchanged.

- [ ] **Step 8: Commit**

```bash
make lint
git add -A && git commit -m "The architecture documents state construction-time validation, the Page allow-list, and validate_app as current truth

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: Convention pass and final gate

- [ ] **Step 1: Docstrings** — every new or changed public function, class and module reads the way its file's neighbours read (imperative first line, `Raises:` where it raises). Check `errors.py`, `app/model.py`, `page/runtime.py`, `typechecking.py`, `validation.py`, `models.py`.

- [ ] **Step 2: Structural audit** — grep for a second copy of a rule (`startswith("/")` outside `app/model.py`; `claimed` dicts in `composition.py` or `web.py`); for `channels=frozenset()` anywhere; for `diagnostic=` (singular) on `AppInspection`; for `.reported` uses that should be `.reports`.

```bash
grep -rn 'startswith("/")' src packages/*/src
grep -rn "claimed" src/vibepy_core/app/composition.py src/vibepy_core/adapters
grep -rn "diagnostic=" packages/vibepy-studio/src/vibepy_studio/authoring
```

- [ ] **Step 3: Full gate**

```bash
make lint typecheck test
```
All green, including `integration`. Commit any convention fixes:

```bash
git add -A && git commit -m "The M16 branch reads by the repository's conventions

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 4: Hand off** — request the two review rounds (`superpowers:requesting-code-review`), then `superpowers:finishing-a-development-branch`: merge `--no-ff` into `main`, promote the spec into the documents (already done in Tasks 10–11; verify nothing in `docs/milestones/M16/` is still the only statement of a truth), delete the folder, push, read CI on both runners.
