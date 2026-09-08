# M7 Structured Error Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every framework failure a stable machine-readable code and a channel-neutral normalized form, so a channel reports framework error semantics without the framework knowing which channel is asking.

**Architecture:** Each existing exception gains a `code` class constant and a `details()` method returning the values its message interpolates. A `to_error_info` function in `vibepy/errors.py` turns any exception into a frozen `ErrorInfo(code, category, message, details)`; the category mapping lives with that function, not on the exceptions. The MCP adapter stops formatting `str(error)` and sends the normalized payload on both of its paths: as JSON-RPC `data` for a protocol error, as a JSON text content block for a result. No exception is renamed, no control flow changes, and nothing new is raised.

**Tech Stack:** Python 3.12+, `enum.StrEnum`, frozen dataclass, pydantic 2, the official `mcp` SDK, pytest with `asyncio_mode = "auto"`, pyright strict, ruff.

**Spec:** `docs/milestones/M7/spec.md`. Read it before starting. It carries the reasoning, the provenance of every contract, and the five questions the owner decided.

## Global Constraints

- `make lint typecheck test` must pass. That is the definition of done for every task.
- `docs/roadmap.md` is never edited.
- `Any` and `cast` are not acceptable in the public API. Use `Protocol`, `TypedDict`, dataclass, or `TypeVar`.
- Optional and configuration parameters are keyword-only.
- Framework exceptions derive from `VibepyError`. Exception types are the contract, not message strings.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- Tests verify public contracts, not internals.
- ruff: `line-length = 100`, rules `E, F, I, UP, B, ASYNC, RUF`.
- pyright: `typeCheckingMode = "strict"`, `pythonVersion = "3.12"`.
- MCP SDK types must not appear in `src/vibepy/errors.py` or anywhere outside `src/vibepy/adapters/`.
- Errors stay untranslated. Nothing catches an exception to wrap it, and the NiceGUI adapter is not touched.
- Do not build ahead: no invocation id on errors, no error domain, no diagnostics type, no permission errors, no config errors, no timeouts.

---

### Task 1: Codes, categories, and the normalized form

The whole core change lands together. A code without a category cannot be normalized, and normalization without codes has nothing to read, so there is no smaller change that leaves the suite green.

**Files:**
- Modify: `src/vibepy/errors.py`
- Modify: `src/vibepy/__init__.py`
- Create: `tests/test_errors.py`
- Modify: `tests/test_package.py:4-27`

**Interfaces:**
- Consumes: `vibepy.lifecycle.AppRuntimeState`, already imported by `errors.py`.
- Produces: `vibepy.errors.ErrorCategory` (`StrEnum` with `CALLER`, `EXECUTION`, `LIFECYCLE`, `DECLARATION`); `vibepy.errors.ErrorInfo` (frozen dataclass with `code: str`, `category: ErrorCategory`, `message: str`, `details: Mapping[str, str]`); `vibepy.errors.to_error_info(error: Exception, /) -> ErrorInfo`; `VibepyError.code: ClassVar[str]` and `VibepyError.details() -> Mapping[str, str]` on every framework exception; the constant `vibepy.errors.UNHANDLED_CODE = "app.unhandled"`.

- [ ] **Step 1: Write the failing catalogue and normalization tests**

Create `tests/test_errors.py`:

```python
"""The error model contract from docs/architecture/errors.md.

The catalogue tests walk every framework exception rather than naming them one by
one: a code that is missing, duplicated, or unmapped is a defect in the model, and
a milestone that adds an error must not be able to skip the rule by not editing
this file.
"""

from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError

import pytest

from vibepy.errors import (
    UNHANDLED_CODE,
    AppRuntimeNotRunningError,
    AppRuntimeTransitionError,
    ErrorCategory,
    ErrorInfo,
    PageNotFoundError,
    PageRouteConflictError,
    PageRouteInvalidError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    VibepyError,
    to_error_info,
)
from vibepy.lifecycle import AppRuntimeState


def _descendants(cls: type[VibepyError]) -> Iterator[type[VibepyError]]:
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _descendants(subclass)


def _framework_errors() -> list[type[VibepyError]]:
    return sorted(_descendants(VibepyError), key=lambda error: error.__name__)


# One constructed instance per framework exception, with the details its message
# interpolates. Adding an exception without adding a row fails
# test_every_framework_error_is_covered_here.
CASES: list[tuple[VibepyError, str, ErrorCategory, Mapping[str, str]]] = [
    (
        ToolNotFoundError("create_todo"),
        "tool.not_found",
        ErrorCategory.CALLER,
        {"tool_name": "create_todo"},
    ),
    (
        ToolInputValidationError("create_todo"),
        "tool.input_invalid",
        ErrorCategory.CALLER,
        {"tool_name": "create_todo"},
    ),
    (
        ToolOutputValidationError("create_todo"),
        "tool.output_invalid",
        ErrorCategory.EXECUTION,
        {"tool_name": "create_todo"},
    ),
    (
        PageNotFoundError("todos"),
        "page.not_found",
        ErrorCategory.CALLER,
        {"page_name": "todos"},
    ),
    (
        PageRouteInvalidError("todos", "todos"),
        "page.route_invalid",
        ErrorCategory.DECLARATION,
        {"page_name": "todos", "route": "todos"},
    ),
    (
        PageRouteConflictError("/todos", "todos", "other"),
        "page.route_conflict",
        ErrorCategory.DECLARATION,
        {"route": "/todos", "page_name": "todos", "conflicting_page_name": "other"},
    ),
    (
        AppRuntimeTransitionError("todo", AppRuntimeState.RUNNING, "start"),
        "lifecycle.transition_forbidden",
        ErrorCategory.LIFECYCLE,
        {"app_id": "todo", "state": "running", "transition": "start"},
    ),
    (
        AppRuntimeNotRunningError("todo", AppRuntimeState.CREATED),
        "lifecycle.not_running",
        ErrorCategory.LIFECYCLE,
        {"app_id": "todo", "state": "created"},
    ),
]


def test_every_framework_error_is_covered_here() -> None:
    covered = {type(error) for error, _, _, _ in CASES}
    assert covered == set(_framework_errors())


@pytest.mark.parametrize("error", [case[0] for case in CASES], ids=lambda e: type(e).__name__)
def test_a_code_is_namespaced_and_not_empty(error: VibepyError) -> None:
    namespace, separator, name = error.code.partition(".")
    assert namespace
    assert separator == "."
    assert name


def test_no_two_errors_share_a_code() -> None:
    codes = [error.code for error in _framework_errors()]
    assert len(codes) == len(set(codes))


def test_no_framework_error_uses_the_unhandled_code() -> None:
    assert UNHANDLED_CODE not in {error.code for error in _framework_errors()}


@pytest.mark.parametrize(
    ("error", "code", "category", "details"), CASES, ids=lambda v: str(v)[:40]
)
def test_normalization_reports_the_declared_code(
    error: VibepyError, code: str, category: ErrorCategory, details: Mapping[str, str]
) -> None:
    info = to_error_info(error)

    assert info.code == code
    assert info.category is category
    assert info.details == details
    assert info.message == str(error)


@pytest.mark.parametrize("error", [case[0] for case in CASES], ids=lambda e: type(e).__name__)
def test_every_value_the_message_interpolates_is_in_details(error: VibepyError) -> None:
    """AIP-193: information contributing to the message belongs in the metadata.

    An agent must never have to parse the sentence to learn which Tool failed.
    """
    message = str(error)
    for value in to_error_info(error).details.values():
        assert value in message


def test_an_exception_the_framework_did_not_define_is_execution() -> None:
    info = to_error_info(RuntimeError("the handler failed"))

    assert info.code == UNHANDLED_CODE
    assert info.category is ErrorCategory.EXECUTION
    assert info.message == "the handler failed"
    assert info.details == {}


def test_error_info_is_frozen() -> None:
    info = to_error_info(ToolNotFoundError("create_todo"))

    with pytest.raises(FrozenInstanceError):
        info.code = "tool.input_invalid"


def test_a_category_reads_as_its_own_value() -> None:
    """The value crosses a channel boundary as a string."""
    assert ErrorCategory.CALLER == "caller"
    assert ErrorInfo("tool.not_found", ErrorCategory.CALLER, "m", {}).category == "caller"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_errors.py -q`
Expected: collection error, `ImportError: cannot import name 'UNHANDLED_CODE' from 'vibepy.errors'`.

- [ ] **Step 3: Rewrite `src/vibepy/errors.py`**

Replace the file with:

```python
"""Framework exceptions and the channel-neutral form a channel reports them in.

Exception types are the contract inside Python. A code is the projection of a type
across a boundary a Python type cannot cross, which is why every exception carries
one and why a code, once published, keeps its meaning for good.

Categories are mapped here rather than declared on each exception: a category is a
property of the code, and one table is easier to keep exhaustive than eight
scattered declarations.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from vibepy.lifecycle import AppRuntimeState

UNHANDLED_CODE = "app.unhandled"
"""The code for a failure the framework did not define. It belongs to no exception."""


class ErrorCategory(StrEnum):
    """What kind of failure this is, independently of which one it is.

    A caller reads it to learn whether a different call could succeed. A future
    REST adapter reads it to choose between 4xx and 5xx.
    """

    CALLER = "caller"
    EXECUTION = "execution"
    LIFECYCLE = "lifecycle"
    DECLARATION = "declaration"


class VibepyError(Exception):
    """Base class for every exception raised by the framework."""

    code: ClassVar[str]

    def details(self) -> Mapping[str, str]:
        """The values this error's message interpolates.

        An agent reads these rather than parsing the sentence, so a message may be
        reworded without breaking anyone.
        """
        return {}


class ToolNotFoundError(VibepyError):
    """No Tool is registered under the requested name."""

    code = "tool.not_found"

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"No Tool is registered under the name {tool_name!r}")
        self.tool_name = tool_name

    def details(self) -> Mapping[str, str]:
        return {"tool_name": self.tool_name}


class ToolInputValidationError(VibepyError):
    """Raw input did not satisfy the Tool's input model."""

    code = "tool.input_invalid"

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Input for Tool {tool_name!r} failed validation")
        self.tool_name = tool_name

    def details(self) -> Mapping[str, str]:
        return {"tool_name": self.tool_name}


class ToolOutputValidationError(VibepyError):
    """A handler result did not satisfy the Tool's output model."""

    code = "tool.output_invalid"

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Output of Tool {tool_name!r} failed validation")
        self.tool_name = tool_name

    def details(self) -> Mapping[str, str]:
        return {"tool_name": self.tool_name}


class PageNotFoundError(VibepyError):
    """No Page is registered under the requested name."""

    code = "page.not_found"

    def __init__(self, page_name: str) -> None:
        super().__init__(f"No Page is registered under the name {page_name!r}")
        self.page_name = page_name

    def details(self) -> Mapping[str, str]:
        return {"page_name": self.page_name}


class PageRouteInvalidError(VibepyError):
    """A Page declared a route the Web channel cannot register."""

    code = "page.route_invalid"

    def __init__(self, page_name: str, route: str) -> None:
        super().__init__(f"Page {page_name!r} declared the invalid route {route!r}")
        self.page_name = page_name
        self.route = route

    def details(self) -> Mapping[str, str]:
        return {"page_name": self.page_name, "route": self.route}


class PageRouteConflictError(VibepyError):
    """Two Pages declared the same route."""

    code = "page.route_conflict"

    def __init__(self, route: str, page_name: str, conflicting_page_name: str) -> None:
        super().__init__(
            f"Pages {page_name!r} and {conflicting_page_name!r} both declare the route {route!r}"
        )
        self.route = route
        self.page_name = page_name
        self.conflicting_page_name = conflicting_page_name

    def details(self) -> Mapping[str, str]:
        return {
            "route": self.route,
            "page_name": self.page_name,
            "conflicting_page_name": self.conflicting_page_name,
        }


class AppRuntimeTransitionError(VibepyError):
    """A lifecycle transition the runtime's current state forbids."""

    code = "lifecycle.transition_forbidden"

    def __init__(self, app_id: str, state: AppRuntimeState, transition: str) -> None:
        super().__init__(f"App {app_id!r} cannot {transition} while {state.value}")
        self.app_id = app_id
        self.state = state
        self.transition = transition

    def details(self) -> Mapping[str, str]:
        return {"app_id": self.app_id, "state": self.state.value, "transition": self.transition}


class AppRuntimeNotRunningError(VibepyError):
    """A runtime that exists only while RUNNING was reached outside that window."""

    code = "lifecycle.not_running"

    def __init__(self, app_id: str, state: AppRuntimeState) -> None:
        super().__init__(f"App {app_id!r} is {state.value}, not running")
        self.app_id = app_id
        self.state = state

    def details(self) -> Mapping[str, str]:
        return {"app_id": self.app_id, "state": self.state.value}


_CATEGORIES: Mapping[str, ErrorCategory] = {
    ToolNotFoundError.code: ErrorCategory.CALLER,
    ToolInputValidationError.code: ErrorCategory.CALLER,
    ToolOutputValidationError.code: ErrorCategory.EXECUTION,
    PageNotFoundError.code: ErrorCategory.CALLER,
    PageRouteInvalidError.code: ErrorCategory.DECLARATION,
    PageRouteConflictError.code: ErrorCategory.DECLARATION,
    AppRuntimeTransitionError.code: ErrorCategory.LIFECYCLE,
    AppRuntimeNotRunningError.code: ErrorCategory.LIFECYCLE,
}


@dataclass(frozen=True)
class ErrorInfo:
    """One failure, in the form every channel reports.

    Carries no channel type and no channel vocabulary, so the Web channel, the
    Agent channel and any future one describe the same failure the same way.
    """

    code: str
    category: ErrorCategory
    message: str
    details: Mapping[str, str]


def to_error_info(error: Exception, /) -> ErrorInfo:
    """Describe any exception in the channel-neutral form.

    Normalizing is not wrapping. The exception itself still propagates untouched;
    this is called only where a channel must render an answer.
    """
    if isinstance(error, VibepyError):
        return ErrorInfo(
            code=error.code,
            category=_CATEGORIES[error.code],
            message=str(error),
            details=error.details(),
        )
    return ErrorInfo(
        code=UNHANDLED_CODE,
        category=ErrorCategory.EXECUTION,
        message=str(error),
        details={},
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_errors.py -q`
Expected: PASS, every test.

- [ ] **Step 5: Export the new names and the two route errors**

In `src/vibepy/__init__.py`, extend the `vibepy.errors` import and `__all__`. The import becomes:

```python
from vibepy.errors import (
    AppRuntimeNotRunningError,
    AppRuntimeTransitionError,
    ErrorCategory,
    ErrorInfo,
    PageNotFoundError,
    PageRouteConflictError,
    PageRouteInvalidError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    VibepyError,
    to_error_info,
)
```

Add `"ErrorCategory"`, `"ErrorInfo"`, `"PageRouteConflictError"`, `"PageRouteInvalidError"` and `"to_error_info"` to `__all__`, keeping it sorted the way it already is: uppercase names sort before lowercase, so `"to_error_info"` goes last.

`UNHANDLED_CODE` is not exported. It is read by the framework and by tests, and an agent receives it in a payload rather than importing it.

- [ ] **Step 6: Update the package export assertion**

In `tests/test_package.py`, the asserted list becomes:

```python
    assert vibepy.__all__ == [
        "AppDefinition",
        "AppRuntime",
        "AppRuntimeNotRunningError",
        "AppRuntimeState",
        "AppRuntimeTransitionError",
        "ErrorCategory",
        "ErrorInfo",
        "Page",
        "PageContext",
        "PageDefinition",
        "PageHandler",
        "PageNotFoundError",
        "PageRegistry",
        "PageRouteConflictError",
        "PageRouteInvalidError",
        "PageRuntime",
        "Tool",
        "ToolContext",
        "ToolDefinition",
        "ToolHandler",
        "ToolInputValidationError",
        "ToolInvoker",
        "ToolNotFoundError",
        "ToolOutputValidationError",
        "ToolRegistry",
        "ToolRuntime",
        "VibepyError",
        "to_error_info",
    ]
```

- [ ] **Step 7: Run the whole suite and the checks**

Run: `make lint typecheck test`
Expected: all green. The MCP adapter still sends `str(error)`; nothing it does has changed yet.

- [ ] **Step 8: Commit**

```bash
git add src/vibepy/errors.py src/vibepy/__init__.py tests/test_errors.py tests/test_package.py
git commit -m "Give every framework error a code and a normalized form"
```

---

### Task 2: The MCP adapter sends the normalized payload

**Files:**
- Modify: `src/vibepy/adapters/mcp/server.py:41-46,66-88`
- Modify: `tests/test_mcp_adapter.py:226-258`

**Interfaces:**
- Consumes: `vibepy.errors.to_error_info(error: Exception, /) -> ErrorInfo` and `ErrorInfo` from Task 1.
- Produces: an MCP failure payload with the members `code`, `category`, `message` and `details`, carried as JSON-RPC `data` on a protocol error and as a JSON text content block on a result.

- [ ] **Step 1: Write the failing adapter tests**

In `tests/test_mcp_adapter.py`, add `json` to the imports at the top of the file, add `UNHANDLED_CODE` and `ErrorCategory` to the `vibepy.errors` imports, and replace the three existing failure tests (`test_an_unknown_tool_name_is_a_protocol_error`, `test_invalid_input_is_reported_inside_the_result`, `test_a_raising_handler_is_reported_inside_the_result`) and `test_invalid_output_is_reported_inside_the_result` with:

```python
def _payload(result: types.CallToolResult) -> dict[str, object]:
    """The error an agent reads out of a failed result."""
    content = result.content[0]
    assert isinstance(content, types.TextContent)
    parsed = json.loads(content.text)
    assert isinstance(parsed, dict)
    return parsed


async def test_an_unknown_tool_name_is_a_protocol_error() -> None:
    fixture = TodoFixture()

    async with server_for(fixture.tools()) as server, Client(server) as client:
        with pytest.raises(MCPError) as raised:
            await client.call_tool("no_such_tool", {})

    assert raised.value.code == INVALID_PARAMS
    assert raised.value.data == {
        "code": "tool.not_found",
        "category": ErrorCategory.CALLER.value,
        "message": raised.value.message,
        "details": {"tool_name": "no_such_tool"},
    }


async def test_invalid_input_is_reported_inside_the_result() -> None:
    fixture = TodoFixture()

    async with server_for(fixture.tools()) as server, Client(server) as client:
        result = await client.call_tool("create_todo", {})

    assert result.is_error is True
    assert result.structured_content is None
    payload = _payload(result)
    assert payload["code"] == "tool.input_invalid"
    assert payload["category"] == ErrorCategory.CALLER.value
    assert payload["details"] == {"tool_name": "create_todo"}


async def test_a_raising_handler_is_reported_inside_the_result() -> None:
    async with server_for(BrokenFixture().tools()) as server, Client(server) as client:
        result = await client.call_tool("explode", {})

    assert result.is_error is True
    payload = _payload(result)
    assert payload["code"] == UNHANDLED_CODE
    assert payload["category"] == ErrorCategory.EXECUTION.value
    assert payload["details"] == {}


async def test_invalid_output_is_reported_inside_the_result() -> None:
    async with server_for(BrokenFixture().tools()) as server, Client(server) as client:
        result = await client.call_tool("lie", {})

    assert result.is_error is True
    payload = _payload(result)
    assert payload["code"] == "tool.output_invalid"
    assert payload["category"] == ErrorCategory.EXECUTION.value
    assert payload["details"] == {"tool_name": "lie"}


async def test_a_failure_never_carries_a_structured_result() -> None:
    """A declared output schema binds structuredContent, so an error may not use it.

    https://modelcontextprotocol.io/specification/2025-06-18/server/tools
    """
    async with server_for(BrokenFixture().tools()) as server, Client(server) as client:
        explode = await client.call_tool("explode", {})
        lie = await client.call_tool("lie", {})

    assert explode.structured_content is None
    assert lie.structured_content is None
```

If `types` is not already imported in this file, add `from mcp import types`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_mcp_adapter.py -q`
Expected: FAIL. `raised.value.data` is `None`, and `json.loads` raises `JSONDecodeError` on the English sentence.

- [ ] **Step 3: Rewrite the adapter's failure path**

In `src/vibepy/adapters/mcp/server.py`, replace the `to_error_info` import block and `_failure`:

```python
from vibepy.errors import (
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    to_error_info,
)
```

```python
def _payload(error: Exception) -> dict[str, object]:
    """The framework's own description of a failure, in the form an agent reads.

    Both MCP failure paths carry it, so the Agent channel reports one failure one
    way whether the protocol answers with an error or with a result.
    """
    info = to_error_info(error)
    return {
        "code": info.code,
        "category": info.category.value,
        "message": info.message,
        "details": dict(info.details),
    }


def _failure(error: Exception) -> types.CallToolResult:
    """A failure the agent can read and act on, rather than a protocol error.

    The payload travels as text rather than as structured content: a Tool declares
    an output schema, and the specification requires structured results to conform
    to it.
    """
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(_payload(error)))],
        is_error=True,
    )
```

Then replace the body of `call_tool`'s `try` block:

```python
        try:
            result = await runtime.invoke(params.name, params.arguments or {})
        except ToolNotFoundError as error:
            raise MCPError(types.INVALID_PARAMS, str(error), _payload(error)) from error
        except ToolInputValidationError as error:
            return _failure(error)
        except ToolOutputValidationError as error:
            logger.error("Tool %r returned output its own model rejected", params.name)
            return _failure(error)
        # Broad on purpose: an app defect must not surface as a protocol error.
        except Exception as error:
            logger.exception("Tool %r raised", params.name)
            return _failure(error)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_mcp_adapter.py -q`
Expected: PASS, every test.

- [ ] **Step 5: Confirm the Web channel is untouched**

Run: `uv run pytest tests/test_nicegui_adapter.py tests/test_dual_channel.py -q`
Expected: PASS with no edits. The NiceGUI adapter translates nothing, and that is the contract `docs/architecture/adapters.md` states.

- [ ] **Step 6: Run the whole suite and the checks**

Run: `make lint typecheck test`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/vibepy/adapters/mcp/server.py tests/test_mcp_adapter.py
git commit -m "Send the normalized error on both MCP failure paths"
```

---

### Task 3: The error document, the ADR, and the de-duplication

The catalogue must live in exactly one document. Four documents currently state their own errors in prose; each keeps its behavioural statement and points at the catalogue instead of repeating it.

**Files:**
- Create: `docs/architecture/errors.md`
- Create: `docs/decisions/ADR-019-framework-errors-carry-stable-codes.md`
- Modify: `docs/architecture.md:96` (the Documents list)
- Modify: `docs/architecture/tool-model.md:114-118`
- Modify: `docs/architecture/page-model.md:109-111`
- Modify: `docs/architecture/adapters.md:61-65`
- Modify: `docs/architecture/lifecycle.md:23-27`

**Interfaces:**
- Consumes: the names Task 1 produced. Every symbol the documents mention must exist.
- Produces: nothing executable.

- [ ] **Step 1: Write `docs/architecture/errors.md`**

```markdown
# Error Model

## Principle

A framework failure is an exception. Inside Python the exception type is the contract; a
channel adapter catches a type and decides what its protocol does with it.

A Python type cannot cross a channel boundary. Every framework exception therefore also
carries a code, which is that type projected into something an agent can read, and a
message, which is for a human and is not a contract.

## Codes

A code is stable. The same code always means the same failure, two different failures never
share one, and a retired code is never reused. A milestone that adds an exception declares its
code on the class and maps its category in `vibepy/errors.py`.

| Code | Category | Exception |
| --- | --- | --- |
| `tool.not_found` | caller | `ToolNotFoundError` |
| `tool.input_invalid` | caller | `ToolInputValidationError` |
| `tool.output_invalid` | execution | `ToolOutputValidationError` |
| `page.not_found` | caller | `PageNotFoundError` |
| `page.route_invalid` | declaration | `PageRouteInvalidError` |
| `page.route_conflict` | declaration | `PageRouteConflictError` |
| `lifecycle.transition_forbidden` | lifecycle | `AppRuntimeTransitionError` |
| `lifecycle.not_running` | lifecycle | `AppRuntimeNotRunningError` |

`app.unhandled` is the code for a failure the framework did not define. It belongs to no
exception class: an exception raised by an App's own code is described, not classified.

## Categories

A category says what kind of failure this is, independently of which one it is. A caller reads
it to learn whether a different call could succeed.

| Category | Meaning |
| --- | --- |
| `caller` | the call itself was wrong; a different call may succeed |
| `execution` | the call was well formed and running it failed; the same call fails again |
| `lifecycle` | the App is not in a state that permits the call |
| `declaration` | the App declared something the framework rejects, raised at registration |

The set is closed and is an enum, so a branch over it ends with `assert_never` and a category
added later cannot be silently unhandled.

## ErrorInfo

`ErrorInfo` is one failure in the form every channel reports: `code`, `category`, `message`
and `details`. `to_error_info(error)` builds one from any exception.

`details` carries every value the message interpolates, so an agent that needs to know which
Tool failed reads a mapping rather than parsing a sentence. This is what allows a message to
be reworded without breaking a client.

Classifying a failure is knowledge about the framework's own errors, so the framework owns it.
Were each adapter to classify, the channels could disagree about the same failure.

## What the framework does not do

Nothing is translated. An exception propagates to the caller as raised, and a handler's own
exception propagates unchanged. Normalization is not wrapping: `to_error_info` is called where
a channel must render an answer, and nowhere else.

## What each channel does

The Web channel translates nothing. A framework error or a handler exception raised during a
render reaches NiceGUI, which renders it. `docs/architecture/adapters.md` gives the reason.

The Agent channel answers every call, so it reports the normalized payload on both of its
paths: as JSON-RPC `data` for a protocol error, and as a JSON text content block for a result
marked `isError`. It does not use `structuredContent`, because a Tool declares an output schema
and the MCP specification requires structured results to conform to it
(<https://modelcontextprotocol.io/specification/2025-06-18/server/tools>).

A client ignores payload members it does not recognize, so a later milestone may add one.

## Related

- `docs/decisions/ADR-019-framework-errors-carry-stable-codes.md`
```

- [ ] **Step 2: Write ADR-019**

Create `docs/decisions/ADR-019-framework-errors-carry-stable-codes.md`:

```markdown
# ADR-019: Framework errors carry stable codes and adapters read a normalized form

Status: Accepted

## Context

Eight exceptions accumulated across M1, M2, M4 and M6, each added by the milestone that needed
it. `AGENTS.md` states that exception types are the contract and message strings are not, but a
Python type cannot cross a channel boundary. The MCP adapter therefore sent `str(error)`, which
made an English sentence the only thing an agent could act on, and classified failures itself
with one `except` clause per type, knowledge a second adapter would have to repeat.

Google AIP-193 requires a structured error precisely so a client never parses a message, and
notes that a message may change over time only once one exists (<https://google.aip.dev/193>).
RFC 9457 states that consumers must use the stable identifier rather than the human-readable
members (<https://www.rfc-editor.org/rfc/rfc9457.html>). gRPC keeps a closed canonical set
alongside the specific error so a caller can tell whether retrying can change the outcome
(<https://grpc.io/docs/guides/status-codes/>).

## Decision

Every framework exception carries a stable `code` and reports the values its message
interpolates through `details()`. A closed `ErrorCategory` accompanies the code. `ErrorInfo` and
`to_error_info` in the core describe any exception in a channel-neutral form, and adapters read
that form instead of classifying exceptions themselves.

Errors are still not translated. Normalization happens only where a channel must render an
answer.

## Consequences

- an agent reads `code` and `category` rather than a sentence, so a message may be reworded
- the text of an MCP failure changes from an English sentence to a JSON object; an agent that
  parsed the prose breaks, which is accepted because the prose was never a contract
- a milestone that adds an exception must declare a code and map a category, and a test that
  walks every subclass enforces both
- one classification exists for all channels, so the Web, Agent and any future adapter cannot
  disagree about the same failure
- a code is permanent: it is never reused for a different failure and never redefined
```

- [ ] **Step 3: Point the four documents at the catalogue**

In `docs/architecture/tool-model.md`, replace the paragraph beginning "Framework errors are `ToolNotFoundError`":

```markdown
Framework errors are `ToolNotFoundError`, raised by the registry when no Tool answers to the
name, and `ToolInputValidationError` and `ToolOutputValidationError`, raised by the Tool.
Nothing translates them: they reach the caller as raised, as does an exception from a
handler. A channel adapter decides what its protocol does with them, and
`docs/architecture/errors.md` carries their codes.
```

In `docs/architecture/page-model.md`, replace the paragraph beginning "Tool errors are not translated":

```markdown
Tool errors are not translated. `ToolNotFoundError`, `ToolInputValidationError` and
`ToolOutputValidationError` reach the caller of the Page unchanged, as does an exception
raised by a PageHandler. `docs/architecture/errors.md` carries their codes.
```

In `docs/architecture/adapters.md`, replace the paragraph beginning "Errors are not translated":

```markdown
Errors are not translated. A Tool error or a handler exception propagates into NiceGUI,
which renders it. The MCP adapter wraps failures in a result because the MCP protocol
demands an answer to every call; the Web channel makes no such demand.
`docs/architecture/errors.md` describes what the MCP adapter sends.
```

In `docs/architecture/lifecycle.md`, replace the paragraph beginning "Framework errors are `AppRuntimeTransitionError`":

```markdown
Framework errors are `AppRuntimeTransitionError`, raised when the current state forbids the
transition, and `AppRuntimeNotRunningError`, raised when a runtime that exists only while
RUNNING is reached outside that window. They are distinct because they are distinct failures:
one is a caller driving the lifecycle wrongly, the other is a caller using the App outside its
running window. `docs/architecture/errors.md` carries their codes.
```

- [ ] **Step 4: Add the document to the overview**

In `docs/architecture.md`, add `- docs/architecture/errors.md` to the Documents list, after `docs/architecture/lifecycle.md`.

- [ ] **Step 5: Check that no fact is now stated twice**

Run: `rg -n 'tool\.not_found|lifecycle\.not_running|ErrorCategory|app\.unhandled' docs/`
Expected: every code and the category set appear in `docs/architecture/errors.md`, in ADR-019's decision paragraph without the table, and in `docs/milestones/M7/`. No code appears in `tool-model.md`, `page-model.md`, `adapters.md` or `lifecycle.md`.

- [ ] **Step 6: Run the checks**

Run: `make lint typecheck test`
Expected: all green. No source changed in this task; this confirms the tree is still clean.

- [ ] **Step 7: Commit**

```bash
git add docs/architecture/errors.md docs/decisions/ADR-019-framework-errors-carry-stable-codes.md docs/architecture.md docs/architecture/tool-model.md docs/architecture/page-model.md docs/architecture/adapters.md docs/architecture/lifecycle.md
git commit -m "Document the error model and record the decision"
```

---

## Integration

- [ ] Confirm the three acceptance criteria in `docs/roadmap.md` are met: codes are stable and machine-readable (`tests/test_errors.py`), Tool, Page, lifecycle and adapter failures are distinguishable (the code namespaces and the category set), and the adapter preserves framework error semantics (`tests/test_mcp_adapter.py`, both failure paths carrying one payload).
- [ ] `make lint typecheck test` passes on the branch tip.
- [ ] Promote what is still true out of `docs/milestones/M7/` and delete the folder, per `AGENTS.md`.
- [ ] Merge `m7-structured-error-model` into `main` with `--no-ff`, delete the branch, then push.
