# M15 Observability and audit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Tool invocation, on either channel, ends by writing one `InvocationRecord` JSON line from `ToolRuntime`, and the three framework processes share one logging configuration that lets it reach standard error.

**Architecture:** `InvocationRecord` is a frozen pydantic model in `vibepy_core.tool.record`, carrying `ErrorInfo | None` as its outcome. `ToolRuntime.invoke` creates the invocation id before anything can refuse, and writes the record on return, on exception and on cancellation, then re-raises. `to_error_info` learns one new classification, `asyncio.CancelledError` → `tool.cancelled` / `interrupted`. One module `vibepy_core.logs` owns the `dictConfig` the `serve`, `mcp` and `invoke` commands apply.

**Tech Stack:** Python 3.12 stdlib `logging` and `asyncio`, pydantic 2, the existing test harnesses (`caplog`, NiceGUI `User`, MCP `Client`, `subprocess`).

Spec: `docs/milestones/M15/spec.md`. Read it first; every "why" below is there.

## Global Constraints

- `make lint typecheck test` passes at the end of every task (ruff with `D` rules on `src/`, pyright strict).
- No `Any`, no `cast` in the public API. Optional parameters are keyword-only. Paths are `pathlib`.
- Standard `logging` only, `getLogger(__name__)`. The framework adds no handler.
- A boundary value is one pydantic model owned by `vibepy_core`; the writer dumps, the reader validates.
- Exceptions are never translated: record, then `raise`.
- Nothing is recorded about a Tool's arguments or result.
- `docs/roadmap.md` is never edited. Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Commit messages in this repository are one sentence saying what is now true and why (see `git log`), not conventional-commit prefixes.
- Work on branch `m15-observability`, already created.

## File structure

| File | Responsibility |
| --- | --- |
| `src/vibepy_core/errors.py` (modify) | `CANCELLED_CODE`, `ErrorCategory.INTERRUPTED`, `to_error_info` classifies `CancelledError` |
| `src/vibepy_core/tool/record.py` (create) | `InvocationRecord`, `read_invocation_record` — the shape and its reader, nothing else |
| `src/vibepy_core/tool/runtime.py` (modify) | `invoke` writes the record; the only writer |
| `src/vibepy_core/tool/__init__.py`, `src/vibepy_core/__init__.py` (modify) | exports |
| `src/vibepy_core/adapters/mcp/server.py` (modify) | the two log lines and the unused logger go |
| `src/vibepy_core/logs.py` (create) | `LOG_CONFIG`, `configure_logging()` — how a framework process writes standard error |
| `src/vibepy_core/serve.py`, `mcp.py`, `invoke.py` (modify) | apply the shared configuration |
| `tests/test_errors.py` (modify) | the new code and category |
| `tests/test_tool_observability.py` (create) | the record's contract, one subject |
| `tests/test_package.py` (modify) | the root export list |
| `tests/test_invoke_command.py`, `test_mcp_command.py`, `test_serve_command.py` (modify) | one record-reaches-stderr test each |
| `docs/architecture/errors.md`, `runtime.md`, `tool-model.md`, `packaging.md` (modify) | current truth |
| `docs/decisions/ADR-036-an-invocation-is-recorded-as-one-line-by-toolruntime.md` (create) | why |

---

### Task 1: `tool.cancelled` is a code, `interrupted` is a category, and `to_error_info` classifies a cancellation

**Files:**
- Modify: `src/vibepy_core/errors.py`
- Modify: `tests/test_errors.py`
- Modify: `docs/architecture/errors.md`

**Interfaces:**
- Produces: `CANCELLED_CODE: str = "tool.cancelled"`, `ErrorCategory.INTERRUPTED = "interrupted"`, `to_error_info(error: Exception | asyncio.CancelledError, /) -> ErrorInfo`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_errors.py` (add `import asyncio` to the imports, and `CANCELLED_CODE` to the `from vibepy_core.errors import (...)` list):

```python
def test_a_cancellation_is_interrupted_not_unhandled() -> None:
    """Something outside the call ended it: not the caller's fault, not the App's."""
    info = to_error_info(asyncio.CancelledError())

    assert info.code == CANCELLED_CODE == "tool.cancelled"
    assert info.category is ErrorCategory.INTERRUPTED
    assert info.details == {}


def test_the_catalogue_maps_the_cancelled_code() -> None:
    assert ERROR_CATALOG[CANCELLED_CODE] == ErrorCategory.INTERRUPTED


def test_no_framework_error_uses_the_cancelled_code() -> None:
    """`asyncio.CancelledError` is asyncio's; the framework wraps it in nothing."""
    assert CANCELLED_CODE not in {error.code for error in _framework_errors()}


def test_a_category_added_later_is_a_value_a_report_carries() -> None:
    line = '{"code": "tool.cancelled", "category": "interrupted", "message": "", "details": {}}'
    found = read_report_line(line)
    assert found is not None
    assert found.category is ErrorCategory.INTERRUPTED
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_errors.py -q -k "cancell or added_later"`
Expected: FAIL — `ImportError: cannot import name 'CANCELLED_CODE'`.

- [ ] **Step 3: Implement**

In `src/vibepy_core/errors.py`:

1. Add `import asyncio` after `import sys`.
2. Below `UNHANDLED_CODE`, add:

```python
CANCELLED_CODE = "tool.cancelled"
"""The code for an invocation something outside it ended. It belongs to no exception:
`asyncio.CancelledError` is asyncio's, and the framework wraps it in nothing."""
```

3. In `ErrorCategory`, add a member and extend the docstring:

```python
class ErrorCategory(StrEnum):
    """What kind of failure this is, independently of which one it is.

    A caller reads it to learn whether a different call could succeed. A future
    REST adapter reads it to choose between 4xx and 5xx.

    `INTERRUPTED` is gRPC's `CANCELLED` family: the call was well formed and the
    App was not at fault, something outside the call ended it, and the same call
    may succeed.
    """

    CALLER = "caller"
    EXECUTION = "execution"
    DECLARATION = "declaration"
    INTERRUPTED = "interrupted"
```

4. In `ERROR_CATALOG`, add the line `CANCELLED_CODE: ErrorCategory.INTERRUPTED,` directly before `UNHANDLED_CODE: ErrorCategory.EXECUTION,`.

5. Replace `to_error_info`:

```python
def to_error_info(error: Exception | asyncio.CancelledError, /) -> ErrorInfo:
    """Describe any exception in the channel-neutral form.

    Normalizing is not wrapping. The exception itself still propagates untouched;
    this is called only where a channel must render an answer or a record is
    written.

    A cancellation is classified here and nowhere else, so the invocation record
    and any channel that one day reports one agree. The parameter admits exactly
    `CancelledError` beyond `Exception` — not `BaseException` — so a
    `KeyboardInterrupt` cannot be described as `app.unhandled` by falling through.

    A code this table does not map is described rather than classified, whatever
    raised it. `VibepyError` is exported, so an App may subclass it, and its
    `code` is an unassigned ClassVar on the base itself. The catalogue test is
    what guarantees no framework exception takes that path.
    """
    if isinstance(error, asyncio.CancelledError):
        return ErrorInfo(
            code=CANCELLED_CODE,
            category=ErrorCategory.INTERRUPTED,
            message=str(error),
            details={},
        )
    if isinstance(error, VibepyError):
        code: object = getattr(error, "code", None)
        if isinstance(code, str):
            category = ERROR_CATALOG.get(code)
            if category is not None:
                return ErrorInfo(
                    code=code,
                    category=category,
                    message=str(error),
                    details=dict(error.details()),
                )
    return ErrorInfo(
        code=UNHANDLED_CODE,
        category=ErrorCategory.EXECUTION,
        message=str(error),
        details={},
    )
```

- [ ] **Step 4: Run the whole error suite and Studio's catalogue test**

Run: `uv run pytest tests/test_errors.py packages/vibepy-studio/tests/test_inspect_framework.py -q`
Expected: all PASS (Studio's inspection compares against `ERROR_CATALOG` dynamically, so it follows).

- [ ] **Step 5: Document**

In `docs/architecture/errors.md`:

- Code table: add the row `| `tool.cancelled` | interrupted | — |` after the `tool.forbidden` row. Directly below the table, extend the `app.unhandled` paragraph:

```markdown
`app.unhandled` is the code for a failure the framework did not define. It belongs to no
exception class: an exception raised by an App's own code is described, not classified.
`tool.cancelled` likewise belongs to no class of the framework's: it is `asyncio.CancelledError`,
which the framework does not wrap, classified when a record or a report is written.
```

- Category table: add `| `interrupted` | the call was well formed and something outside it ended the execution; the same call may succeed |`. Below the table's "closed set" paragraph, add:

```markdown
`interrupted` is the family gRPC calls `CANCELLED` and `DEADLINE_EXCEEDED`, distinct from a
client's error and a server's. Cancellation is its first code; a timeout, when
`docs/decisions/ADR-005-tool-handlers-async-first.md`'s open question is decided, is its second.
```

- ErrorInfo section: change "`to_error_info(error)` builds one from any exception" to "`to_error_info(error)` builds one from any `Exception`, and from `asyncio.CancelledError`, the one `BaseException` an invocation ends with that is not the process ending".

- [ ] **Step 6: Gate and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add src/vibepy_core/errors.py tests/test_errors.py docs/architecture/errors.md
git commit -m "A cancelled invocation is tool.cancelled in a category of its own, interrupted: the call was right and the App was not at fault, so neither caller nor execution is true of it

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `InvocationRecord` and its reader

**Files:**
- Create: `src/vibepy_core/tool/record.py`
- Modify: `src/vibepy_core/tool/__init__.py`, `src/vibepy_core/__init__.py`
- Modify: `tests/test_package.py`
- Create: `tests/test_tool_observability.py`

**Interfaces:**
- Consumes: `ErrorInfo`, `Channel`, `Principal`.
- Produces:

```python
class InvocationRecord(BaseModel):   # frozen
    invocation_id: str
    app_id: str
    tool: str
    channel: Channel
    principal: Principal
    started_at: datetime
    duration_seconds: float
    error: ErrorInfo | None

def read_invocation_record(line: str, /) -> InvocationRecord | None: ...
```

`InvocationRecord` is exported from `vibepy_core` and `vibepy_core.tool`; `read_invocation_record` from `vibepy_core.tool` only (a reader is a host operation, ADR-035).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tool_observability.py`:

```python
"""The invocation record: one line per Tool call, written by ToolRuntime.

Contract in docs/architecture/runtime.md (the record) and docs/architecture/errors.md
(`tool.cancelled`). One subject: what is written, when, and that it reads back.
"""

from datetime import UTC, datetime

from vibepy_core import Channel, ErrorCategory, ErrorInfo, InvocationRecord, Principal
from vibepy_core.errors import read_report_line, report_line, to_error_info
from vibepy_core.tool import read_invocation_record

TESTER = Principal(id="tester", roles=frozenset({"manager"}))


def a_record(*, error: ErrorInfo | None = None) -> InvocationRecord:
    return InvocationRecord(
        invocation_id="inv-1",
        app_id="todo",
        tool="create_todo",
        channel=Channel.AGENT,
        principal=TESTER,
        started_at=datetime(2026, 9, 12, 10, 0, tzinfo=UTC),
        duration_seconds=0.25,
        error=error,
    )


def test_a_record_line_round_trips_as_the_same_record() -> None:
    record = a_record(error=to_error_info(RuntimeError("boom")))
    assert read_invocation_record(record.model_dump_json()) == record


def test_a_record_carries_its_principal_and_channel_as_values() -> None:
    """The line crosses a process; what is read back is the same principal."""
    read = read_invocation_record(a_record().model_dump_json())
    assert read is not None
    assert read.principal == TESTER
    assert read.channel is Channel.AGENT
    assert read.error is None


def test_a_record_line_is_not_a_report_and_a_report_line_is_not_a_record() -> None:
    """Both share one stream; a reader of either must not take the other."""
    record_line = a_record(error=to_error_info(RuntimeError("boom"))).model_dump_json()
    report = report_line(to_error_info(RuntimeError("boom")))

    assert read_report_line(record_line) is None
    assert read_invocation_record(report) is None


def test_a_line_that_is_not_a_record_reads_as_nothing() -> None:
    assert read_invocation_record("Traceback (most recent call last):") is None
    assert read_invocation_record('{"invocation_id": "x"}') is None


def test_a_record_requires_its_outcome() -> None:
    """`error` is stated, never defaulted: an omitted field is not a success."""
    line = a_record().model_dump_json()
    without = line.replace(',"error":null', "")
    assert read_invocation_record(without) is None


def test_a_record_is_frozen() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        a_record().tool = "other"
```

(Move the two imports in the last test to the module top when writing the file; they are shown inline only so the block is self-contained.)

In `tests/test_package.py`, insert `"InvocationRecord",` directly before `"InvocationRequest",` in the root `__all__` list.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_tool_observability.py tests/test_package.py -q`
Expected: FAIL — `ImportError: cannot import name 'InvocationRecord'`.

- [ ] **Step 3: Implement**

Create `src/vibepy_core/tool/record.py`:

```python
"""One invocation, written down as it ends.

The record crosses a process boundary — a framework process writes it to standard
error, and whatever started the process reads it — so it is one pydantic model:
ToolRuntime dumps it, a reader validates it, and no surface re-declares its fields.
It lives with the Tool vocabulary it is made of, not with the runtime that writes
it, per `docs/decisions/ADR-035-the-package-root-is-the-app-authors-vocabulary.md`.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, ValidationError

from vibepy_core.channel import Channel
from vibepy_core.errors import ErrorInfo
from vibepy_core.principal import Principal


class InvocationRecord(BaseModel):
    """What one Tool invocation was, for whom, from where, and how it ended.

    `error` is the outcome: `None` when the Tool returned, otherwise the same
    `ErrorInfo` a channel would report. There is no separate status field, so the
    same fact is stated once. Arguments and results are not carried; they are the
    App's data.

    `started_at` is the wall clock, for an auditor; `duration_seconds` is measured
    on the monotonic clock, for a measurement. Both are required, `error` included:
    a line that omits its outcome is not a record.
    """

    model_config = ConfigDict(frozen=True)

    invocation_id: str
    app_id: str
    tool: str
    channel: Channel
    principal: Principal
    started_at: datetime
    duration_seconds: float
    error: ErrorInfo | None


def read_invocation_record(line: str, /) -> InvocationRecord | None:
    """Read one line as the record ToolRuntime writes, or `None` if it is not one.

    Reading belongs beside writing, as `read_report_line` does for a report. A
    framework process's standard error carries reports, records and other lines
    on one stream; a reader takes what validates and skips the rest.
    """
    try:
        return InvocationRecord.model_validate_json(line)
    except ValidationError:
        return None
```

In `src/vibepy_core/tool/__init__.py`, add `from vibepy_core.tool.record import InvocationRecord, read_invocation_record` and add `"InvocationRecord",` and `"read_invocation_record",` to `__all__` (keep the list sorted as it is: capitalised names first, alphabetical; `read_invocation_record` goes after `default_policy`).

In `src/vibepy_core/__init__.py`, add `InvocationRecord,` to the `from vibepy_core.tool import (...)` block and `"InvocationRecord",` to `__all__` directly before `"InvocationRequest",`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_tool_observability.py tests/test_package.py -q`
Expected: PASS.

- [ ] **Step 5: Gate and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add src/vibepy_core/tool/record.py src/vibepy_core/tool/__init__.py src/vibepy_core/__init__.py tests/test_tool_observability.py tests/test_package.py
git commit -m "InvocationRecord is the one shape a Tool invocation is written down in, and its reader lives beside it

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: ToolRuntime writes the record on every ending

**Files:**
- Modify: `src/vibepy_core/tool/runtime.py`
- Modify: `tests/test_tool_observability.py`
- Modify: `docs/architecture/runtime.md`, `docs/architecture/tool-model.md`

**Interfaces:**
- Consumes: `InvocationRecord`, `to_error_info`, `ErrorCategory`.
- Produces: log records at INFO on logger `vibepy_core.tool.runtime`, message `InvocationRecord.model_dump_json()`, `exc_info` set exactly when `error.category is ErrorCategory.EXECUTION`. `ToolRuntime.invoke`'s signature is unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tool_observability.py`. Add these imports at the top of the file: `import asyncio`, `import logging`, `import pytest`, `from pydantic import BaseModel`, `from vibepy_core.errors import ToolForbiddenError, ToolInputValidationError, ToolNotFoundError, ToolOutputValidationError` (merge with the existing `vibepy_core.errors` import), `from vibepy_core.tool import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolRuntime`.

```python
RUNTIME_LOGGER = "vibepy_core.tool.runtime"
"""The logger `docs/architecture/runtime.md` documents. A host attaches its handler here."""


class Empty(BaseModel):
    pass


class Strict(BaseModel):
    n: int


class Seen:
    """What a handler saw: the context it was given."""

    def __init__(self) -> None:
        self.contexts: list[ToolContext[object]] = []


async def echo(ctx: ToolContext[Seen], _payload: Empty) -> Empty:
    ctx.dependencies.contexts.append(ctx)
    return Empty()


async def fail(ctx: ToolContext[Seen], _payload: Empty) -> Empty:
    raise RuntimeError("the handler failed")


async def bad_output(ctx: ToolContext[Seen], _payload: Empty) -> Strict:
    return Strict.model_construct(n="not an int")


def tool(name: str, handler: object, *, output: type[BaseModel] = Empty,
         channels: frozenset[Channel] = frozenset(Channel)) -> Tool[Seen]:
    return Tool(
        definition=ToolDefinition(
            name=name, description=name, input_model=Empty, output_model=output,
            read_only=True, channels=channels,
        ),
        handler=handler,  # pyright: ignore[reportArgumentType]
    )


def runtime(*tools: Tool[Seen], channel: Channel = Channel.AGENT) -> tuple[ToolRuntime[Seen], Seen]:
    registry: ToolRegistry[Seen] = ToolRegistry()
    for one in tools:
        registry.register(one)
    seen = Seen()
    return ToolRuntime(app_id="observed", registry=registry, dependencies=seen, channel=channel), seen


def written(caplog: pytest.LogCaptureFixture) -> list[tuple[InvocationRecord, logging.LogRecord]]:
    """Every record the runtime wrote, read back through the framework's reader."""
    found: list[tuple[InvocationRecord, logging.LogRecord]] = []
    for log in caplog.records:
        if log.name != RUNTIME_LOGGER:
            continue
        record = read_invocation_record(log.getMessage())
        assert record is not None, log.getMessage()
        assert log.levelno == logging.INFO
        found.append((record, log))
    return found


@pytest.fixture
def records(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger=RUNTIME_LOGGER)
    return caplog


async def test_a_returned_tool_leaves_one_record_the_handler_can_be_correlated_to(
    records: pytest.LogCaptureFixture,
) -> None:
    run, seen = runtime(tool("echo", echo))

    await run.invoke("echo", {}, principal=TESTER)

    [(record, log)] = written(records)
    [ctx] = seen.contexts
    assert record.invocation_id == ctx.invocation_id
    assert record.app_id == "observed"
    assert record.tool == "echo"
    assert record.channel is Channel.AGENT
    assert record.principal == TESTER
    assert record.started_at.tzinfo is not None
    assert record.duration_seconds >= 0
    assert record.error is None
    assert log.exc_info is None


async def test_two_invocations_have_two_ids(records: pytest.LogCaptureFixture) -> None:
    run, _ = runtime(tool("echo", echo))
    await run.invoke("echo", {}, principal=TESTER)
    await run.invoke("echo", {}, principal=TESTER)
    ids = {record.invocation_id for record, _ in written(records)}
    assert len(ids) == 2


async def test_an_unknown_tool_is_recorded_with_an_id_and_raised(
    records: pytest.LogCaptureFixture,
) -> None:
    run, _ = runtime()

    with pytest.raises(ToolNotFoundError):
        await run.invoke("absent", {}, principal=TESTER)

    [(record, log)] = written(records)
    assert record.tool == "absent"
    assert record.invocation_id
    assert record.error is not None
    assert record.error.code == "tool.not_found"
    assert log.exc_info is None


async def test_a_refusal_is_recorded_and_raised(records: pytest.LogCaptureFixture) -> None:
    """OWASP: an authorization failure is logged. The handler never ran."""
    run, seen = runtime(tool("echo", echo, channels=frozenset({Channel.WEB})))

    with pytest.raises(ToolForbiddenError):
        await run.invoke("echo", {}, principal=TESTER)

    [(record, log)] = written(records)
    assert record.error is not None
    assert record.error.code == "tool.forbidden"
    assert record.error.category is ErrorCategory.CALLER
    assert seen.contexts == []
    assert log.exc_info is None


async def test_invalid_input_is_recorded_and_raised(records: pytest.LogCaptureFixture) -> None:
    run, _ = runtime(tool("echo", echo))

    with pytest.raises(ToolInputValidationError):
        await run.invoke("echo", {"unexpected": 1}, principal=TESTER)

    [(record, log)] = written(records)
    assert record.error is not None
    assert record.error.code == "tool.input_invalid"
    assert log.exc_info is None


async def test_a_handler_exception_is_recorded_with_its_traceback_and_raised(
    records: pytest.LogCaptureFixture,
) -> None:
    run, _ = runtime(tool("fail", fail))

    with pytest.raises(RuntimeError):
        await run.invoke("fail", {}, principal=TESTER)

    [(record, log)] = written(records)
    assert record.error is not None
    assert record.error.code == "app.unhandled"
    assert record.error.category is ErrorCategory.EXECUTION
    assert record.error.message == "the handler failed"
    assert log.exc_info is not None
    assert log.exc_info[0] is RuntimeError


async def test_invalid_output_is_recorded_with_its_traceback(
    records: pytest.LogCaptureFixture,
) -> None:
    run, _ = runtime(tool("bad", bad_output, output=Strict))

    with pytest.raises(ToolOutputValidationError):
        await run.invoke("bad", {}, principal=TESTER)

    [(record, log)] = written(records)
    assert record.error is not None
    assert record.error.code == "tool.output_invalid"
    assert log.exc_info is not None


async def test_a_cancelled_invocation_is_recorded_as_interrupted_and_propagates(
    records: pytest.LogCaptureFixture,
) -> None:
    """asyncio: catch, clean up, re-raise. MCP: log the cancellation."""
    entered = asyncio.Event()
    hold = asyncio.Event()

    async def wait(ctx: ToolContext[Seen], _payload: Empty) -> Empty:
        entered.set()
        await hold.wait()
        return Empty()

    run, _ = runtime(tool("wait", wait))
    task = asyncio.create_task(run.invoke("wait", {}, principal=TESTER))
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    [(record, log)] = written(records)
    assert record.error is not None
    assert record.error.code == "tool.cancelled"
    assert record.error.category is ErrorCategory.INTERRUPTED
    assert log.exc_info is None
```

Note for the implementer: the `# pyright: ignore[reportArgumentType]` on `handler=handler` exists because the helper takes `object`; if pyright reports no error there, remove the comment (ruff `RUF100` will flag an unused ignore). If it is simpler, type the parameter as `ToolHandler[Seen, Empty, BaseModel]` and drop the ignore.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_tool_observability.py -q`
Expected: the new tests FAIL with `ValueError: not enough values to unpack` (nothing written).

- [ ] **Step 3: Implement**

Replace the `ToolRuntime` class in `src/vibepy_core/tool/runtime.py` (leave `Tool` and `BoundTool` as they are). New imports at the top: `import asyncio`, `import logging`, `from datetime import UTC, datetime`, `from time import perf_counter`, `from vibepy_core.errors import ErrorCategory, ErrorInfo, ToolInputValidationError, ToolOutputValidationError, to_error_info`, `from vibepy_core.tool.record import InvocationRecord`. Add `logger = logging.getLogger(__name__)` after the imports.

```python
class ToolRuntime[DepsT]:
    """Resolves a Tool by name, creates its ToolContext, invokes it, and writes it down.

    ``dependencies`` is the application-scoped resource the channel's window
    acquired. The runtime holds it and puts it into every ToolContext it creates,
    so a channel never constructs a context.

    ``channel`` is the window's, fixed when it opened; the principal is the
    call's, given per invocation. Authorization runs from the two and the
    declaration before input is validated, so what a caller may not invoke it
    also may not probe.

    Every invocation ends with one `InvocationRecord` on this module's logger,
    whatever way it ends. The id exists before anything can refuse, so a refusal
    is recorded with one. Nothing is translated: the record is written on the way
    out and the exception propagates as raised. This is the only writer.

    Concurrent invocations are permitted. Nothing here serializes them.
    """

    def __init__(
        self,
        *,
        app_id: str,
        registry: "ToolRegistry[DepsT]",
        dependencies: DepsT,
        channel: Channel,
        policy: ToolPolicy | None = None,
    ) -> None:
        """Hold what every invocation uses, this window's `channel` and `policy` included."""
        self._app_id = app_id
        self._registry = registry
        self._dependencies = dependencies
        self._channel = channel
        self._policy = policy

    async def invoke(
        self, name: str, raw_input: Mapping[str, object], /, *, principal: Principal
    ) -> BaseModel:
        """Authorize `principal` for `name`, invoke it with `raw_input`, record the ending.

        The framework's policy always runs, and the App's runs after it: an App
        may refuse further, never admit what the declaration refuses.

        A cancellation is recorded and re-raised, as asyncio requires of anything
        that catches it. `KeyboardInterrupt` and `SystemExit` are not caught: they
        end the process, and the process reports its own ending.

        Raises:
            ToolNotFoundError: no Tool is registered under `name`.
            ToolForbiddenError: `principal` may not invoke this Tool here.
            ToolInputValidationError: `raw_input` does not satisfy the Tool's
                input model.
            ToolOutputValidationError: the Tool returned what its own output
                model rejects.
        """
        invocation_id = str(uuid4())
        started_at = datetime.now(UTC)
        started = perf_counter()
        try:
            tool = self._registry.resolve(name)
            request = AuthorizationRequest(
                definition=tool.definition, principal=principal, channel=self._channel
            )
            default_policy.authorize(request)
            if self._policy is not None:
                self._policy.authorize(request)
            ctx = ToolContext(
                app_id=self._app_id,
                invocation_id=invocation_id,
                dependencies=self._dependencies,
                principal=principal,
                channel=self._channel,
            )
            result = await tool.bound(ctx, raw_input)
        except (asyncio.CancelledError, Exception) as error:
            self._record(invocation_id, name, principal, started_at, started, error=to_error_info(error))
            raise
        self._record(invocation_id, name, principal, started_at, started, error=None)
        return result

    def _record(
        self,
        invocation_id: str,
        tool: str,
        principal: Principal,
        started_at: datetime,
        started: float,
        /,
        *,
        error: ErrorInfo | None,
    ) -> None:
        """Write the one record of an invocation that has just ended.

        The traceback follows an `execution` failure only: that category alone is
        a defect in code a developer must find. Called inside the `except` for a
        failure, so `exc_info=True` names the exception being handled.
        """
        record = InvocationRecord(
            invocation_id=invocation_id,
            app_id=self._app_id,
            tool=tool,
            channel=self._channel,
            principal=principal,
            started_at=started_at,
            duration_seconds=perf_counter() - started,
            error=error,
        )
        with_traceback = error is not None and error.category is ErrorCategory.EXECUTION
        logger.info(record.model_dump_json(), exc_info=with_traceback)
```

Keep `ToolInputValidationError`/`ToolOutputValidationError` imported — `Tool` still raises them. Remove nothing else.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_tool_observability.py tests/test_tool_core.py tests/test_tool_authorization.py tests/test_execution_semantics.py -q`
Expected: PASS.

- [ ] **Step 5: Document**

`docs/architecture/tool-model.md`, ToolRuntime section — replace the numbered list:

```markdown
`ToolRuntime.invoke(name, raw_input, *, principal)` is the whole of it:

1. create the invocation id and note the time, before anything can refuse
2. resolve the Tool by name, through ToolRegistry
3. the framework's default policy: the channel against `channels`, the principal's roles
   against `required_roles`
4. the App's policy, if it declared one
5. create the ToolContext, carrying that invocation id, the application-scoped resource, the
   principal and the channel
6. await the Tool
7. write the invocation record, whatever way steps 2–6 ended, and re-raise what they raised

`docs/architecture/runtime.md` owns the record.
```

`docs/architecture/runtime.md`:

- In "ToolRuntime as the execution center", replace the "Potential future cross-cutting concerns" list with `timeout`, `metrics`, `transaction hooks`, `rate limits` (audit and tracing are no longer future), and add a new subsection after it:

```markdown
## The invocation record

Every invocation ends with one record, written by ToolRuntime and by nothing else, so the Web
and the Agent channel are observed by one writer and cannot disagree. The record is
`InvocationRecord`, one pydantic model owned by `vibepy_core.tool`: the invocation id, the App
id, the Tool name, the channel, the principal, when it started, how long it took, and how it
ended — `error` is `None` when the Tool returned and the `ErrorInfo` a channel would report
otherwise. There is no status field; the failure is the presence of `error`, its kind is
`error.code`. Arguments and results are not recorded.

The id exists before the Tool is resolved, so a refusal and an unknown name are recorded with
one, and the id a handler reads as `ctx.invocation_id` is the id on the record. A cancellation
is recorded as `tool.cancelled` and re-raised; `KeyboardInterrupt` and `SystemExit` are not
recorded, because they end the process and the process reports its own ending (ADR-030).

It is written as `logger.info(record.model_dump_json())` on the logger
`vibepy_core.tool.runtime`, with the traceback appended when `error.category` is `execution`
and only then. The framework configures no handler on it; a process that runs the framework does
(`docs/architecture/packaging.md`, What a command writes to standard error), and a host that
wants the records elsewhere attaches a handler of its own. `read_invocation_record` reads a line
back, and a line is a record or a report or neither, never both.

See `docs/decisions/ADR-036-an-invocation-is-recorded-as-one-line-by-toolruntime.md`.
```

- In "ToolContext", change "ToolRuntime creates a ToolContext for every invocation, with an invocation id unique to that invocation." to "ToolRuntime creates a ToolContext for every invocation that passes authorization, with an invocation id unique to that invocation — the same id the invocation record carries, so a handler's own log line and the record can be read together." Remove `trace context` from the "Future fields" list only if you also remove the list's other items? No — leave the list; trace context remains a future field.

- [ ] **Step 6: Gate and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add src/vibepy_core/tool/runtime.py tests/test_tool_observability.py docs/architecture/runtime.md docs/architecture/tool-model.md
git commit -m "ToolRuntime writes one InvocationRecord as every invocation ends, id first so a refusal has one, traceback only where a developer has code to fix

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Both channels leave the same record, and the MCP adapter stops writing its own

**Files:**
- Modify: `src/vibepy_core/adapters/mcp/server.py`
- Modify: `tests/test_tool_observability.py`

**Interfaces:**
- Consumes: `one_store` from `tests/test_dual_channel.py`, `TODO_APP` from the `todo-app` fixture, `register_pages`, `page_runtime_for`, `build_mcp_server`, NiceGUI `User`.
- Produces: nothing new; removes two `logger` calls and the module's unused `logger`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tool_observability.py`. Imports to add: `from pathlib import Path`, `from mcp.client import Client`, `from nicegui.testing import User`, `from test_dual_channel import one_store`, `from todo_app.entry import TODO_APP`, `from vibepy_core.adapters.mcp import build_mcp_server`, `from vibepy_core.adapters.nicegui import register_pages`, `from vibepy_core.app import page_runtime_for`.

```python
async def test_both_channels_leave_the_same_record(
    user: User, tmp_path: Path, records: pytest.LogCaptureFixture
) -> None:
    """Consistency is structural: one writer, so the two channels cannot differ in kind."""
    config = {"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}
    lifespan = one_store(config)

    async with page_runtime_for(TODO_APP, lifespan, config=config) as pages:
        register_pages(TODO_APP, pages, principal=Principal(id="operator"))
        async with Client(
            build_mcp_server(TODO_APP, lifespan, config=config, principal=Principal(id="agent"))
        ) as agent:
            await agent.call_tool("list_todos", {})
            await user.open("/todos")
            await user.should_see("Add")

    listed = [record for record, _ in written(records) if record.tool == "list_todos"]
    by_channel = {record.channel: record for record in listed}
    assert set(by_channel) == {Channel.AGENT, Channel.WEB}
    web, agent_side = by_channel[Channel.WEB], by_channel[Channel.AGENT]
    assert agent_side.principal == Principal(id="agent")
    assert web.principal == Principal(id="operator")
    assert agent_side.invocation_id != web.invocation_id
    assert (agent_side.app_id, agent_side.tool, agent_side.error) == (web.app_id, web.tool, web.error)


async def test_a_handler_failure_over_mcp_is_recorded_once(
    records: pytest.LogCaptureFixture,
) -> None:
    """The adapter writes nothing of its own about a failure; the record is the one line."""
    run_tools = [tool("fail", fail)]
    registry: ToolRegistry[Seen] = ToolRegistry()
    for one in run_tools:
        registry.register(one)
    # Drive the runtime the adapter drives, with the adapter's own logger captured too.
    records.set_level(logging.INFO, logger="vibepy_core.adapters.mcp.server")
    run = ToolRuntime(app_id="observed", registry=registry, dependencies=Seen(), channel=Channel.AGENT)
    with pytest.raises(RuntimeError):
        await run.invoke("fail", {}, principal=TESTER)
    assert [log.name for log in records.records] == [RUNTIME_LOGGER]
```

Then replace the second test's body with one that goes through the adapter for real — the version above only proves the runtime, and the adapter's lines are what must be gone:

```python
async def test_a_handler_failure_over_mcp_is_recorded_once(
    tmp_path: Path, records: pytest.LogCaptureFixture
) -> None:
    """The adapter writes nothing of its own about a failure; the record is the one line."""
    records.set_level(logging.INFO, logger="vibepy_core.adapters.mcp.server")
    config = {"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}
    async with Client(
        build_mcp_server(TODO_APP, one_store(config), config=config, principal=Principal(id="agent"))
    ) as agent:
        failed = await agent.call_tool("complete_todo", {"id": "not-an-int"})

    assert failed.is_error is True
    assert [log.name for log in records.records] == [RUNTIME_LOGGER]
    [(record, _)] = written(records)
    assert record.error is not None
    assert record.error.code == "tool.input_invalid"
```

(Use only the second version. It is shown twice so the intent is unambiguous: the adapter is exercised, and the only line on any `vibepy_core` logger is the record.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_tool_observability.py -q -k "both_channels or recorded_once"`
Expected: `both_channels` PASSES already (the writer is one; this test pins it). `recorded_once` PASSES too for `tool.input_invalid`, because the adapter logs only for output-invalid and unhandled — so change the call to one that raises in the handler if the fixture has one; the Todo App has none. Therefore switch the test to an App built in the test: register `tool("fail", fail)` in a one-Tool `AppDefinition` and drive it through `build_mcp_server` with `no_dependencies` from `tests/lifecycle.py`:

```python
from lifecycle import no_dependencies
from vibepy_core import AppDefinition, NoConfig


async def test_a_handler_failure_over_mcp_is_recorded_once(
    records: pytest.LogCaptureFixture,
) -> None:
    """The adapter writes nothing of its own about a failure; the record is the one line."""
    records.set_level(logging.INFO, logger="vibepy_core.adapters.mcp.server")
    failing: AppDefinition[None, NoConfig] = AppDefinition(
        app_id="failing", name="Failing", version="0.0.0", config=NoConfig,
        tools=[tool_for_none("fail", fail_for_none)], pages=[],
    )
    async with Client(
        build_mcp_server(failing, no_dependencies, config={}, principal=Principal(id="agent"))
    ) as agent:
        failed = await agent.call_tool("fail", {})

    assert failed.is_error is True
    assert [log.name for log in records.records] == [RUNTIME_LOGGER]
    [(record, log)] = written(records)
    assert record.error is not None
    assert record.error.code == "app.unhandled"
    assert log.exc_info is not None
```

where `fail_for_none` is `async def fail_for_none(ctx: ToolContext[None], _payload: Empty) -> Empty: raise RuntimeError("the handler failed")` and `tool_for_none` builds a `Tool[None]` exactly as `tool` builds a `Tool[Seen]`. Check `AppDefinition`'s constructor fields in `src/vibepy_core/app/model.py` before writing it and match them.

Expected now: FAIL — the list of logger names contains `vibepy_core.adapters.mcp.server` as well.

- [ ] **Step 3: Implement**

In `src/vibepy_core/adapters/mcp/server.py`:

- Delete the line `logger.error("Tool %r returned output its own model rejected", params.name)` and the line `logger.exception("Tool %r raised", params.name)`. The two `except` arms become `return _failure(error)` alone; merge `ToolOutputValidationError` into the arm above it if that leaves them identical: `except (ToolForbiddenError, ToolInputValidationError, ToolOutputValidationError) as error: return _failure(error)`.
- Delete `logger = logging.getLogger(__name__)` and `import logging` — nothing else in the module logs. (Verify with `grep -n logger src/vibepy_core/adapters/mcp/server.py` → no output.)
- Update the comment on the broad `except Exception`: `# Broad on purpose: an app defect must not surface as a protocol error. ToolRuntime has already recorded it, traceback included.`

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_tool_observability.py tests/test_mcp_adapter.py tests/test_dual_channel.py -q`
Expected: PASS.

- [ ] **Step 5: Documentation check**

Run: `grep -n -i "log" docs/architecture/adapters.md docs/architecture/errors.md`
Expected: `errors.md` mentions a window reporting through `logging` (ADR-030, unchanged, correct). If any line says the Agent adapter logs a handler failure, delete that sentence. `adapters.md` had none at planning time.

- [ ] **Step 6: Gate and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add src/vibepy_core/adapters/mcp/server.py tests/test_tool_observability.py
git commit -m "The MCP adapter no longer describes a handler failure in its own words: the record ToolRuntime writes is the one line, traceback included, on either channel

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: One logging configuration for the three processes, proven from each process's standard error

**Files:**
- Create: `src/vibepy_core/logs.py`
- Modify: `src/vibepy_core/serve.py`, `src/vibepy_core/mcp.py`, `src/vibepy_core/invoke.py`
- Modify: `tests/test_invoke_command.py`, `tests/test_mcp_command.py`, `tests/test_serve_command.py`
- Modify: `docs/architecture/packaging.md`

**Interfaces:**
- Produces: `LOG_CONFIG: dict[str, object]`, `configure_logging() -> None` in `vibepy_core.logs`.

- [ ] **Step 1: Write the failing tests**

`tests/test_invoke_command.py` — add `from vibepy_core import Channel` and `from vibepy_core.tool import read_invocation_record`, then append:

```python
def records_in(stderr: str) -> list[InvocationRecord]:
    found = [read_invocation_record(line) for line in stderr.splitlines()]
    return [record for record in found if record is not None]


@pytest.mark.integration
def test_an_invocation_is_recorded_on_standard_error(tmp_path: Path) -> None:
    result = run_invoke(
        "todo-app", "create_todo", {"input": {"title": "milk"}}, config=todo_config(tmp_path)
    )
    assert result.returncode == 0, result.stderr
    [record] = records_in(result.stderr)
    assert record.tool == "create_todo"
    assert record.channel is Channel.AGENT
    assert record.principal.id == "tester"
    assert record.error is None
```

(add `InvocationRecord` to the `from vibepy_core import ...` line.)

`tests/test_mcp_command.py` — add `from mcp.client.stdio import stdio_client`, `from test_invoke_command import records_in`, `from vibepy_core import Channel`, then append:

```python
@pytest.mark.integration
async def test_an_invocation_is_recorded_on_the_server_process_standard_error(tmp_path: Path) -> None:
    """stdout is the wire; the record goes where the framework's own lines go."""
    errlog_path = tmp_path / "server.stderr"
    with errlog_path.open("w", encoding="utf-8") as errlog:
        async with Client(stdio_client(todo_server(tmp_path), errlog=errlog)) as agent:
            await agent.call_tool("create_todo", {"title": "milk"})

    [record] = records_in(errlog_path.read_text(encoding="utf-8"))
    assert record.tool == "create_todo"
    assert record.channel is Channel.AGENT
    assert record.principal.id == "agent"
    assert record.error is None
```

`tests/test_serve_command.py` — add `from test_invoke_command import records_in` (note: `test_invoke_command` imports from this module; to avoid the cycle, define `records_in` here in `test_serve_command.py` instead and import it from here in the other two files), `from vibepy_core import Channel`, then append:

```python
@pytest.mark.integration
def test_a_page_render_is_recorded_on_standard_error(tmp_path: Path) -> None:
    """Rendering `/todos` invokes `list_todos` through the Page; the record says so."""
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "vibepy_core.serve", "todo-app", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=todo_environment(tmp_path),
    )
    try:
        wait_for(f"http://127.0.0.1:{port}/todos", process)
    finally:
        process.terminate()
        _, stderr = process.communicate(timeout=10)

    listed = [r for r in records_in(stderr.decode(errors="replace")) if r.tool == "list_todos"]
    assert listed, stderr.decode(errors="replace")
    assert listed[0].channel is Channel.WEB
    assert listed[0].principal.id == "operator"
    assert listed[0].error is None
```

So: put `records_in` in `tests/test_serve_command.py` (it already exports `child_environment` and `reported_failure` to the other two), and import it in `test_invoke_command.py` and `test_mcp_command.py` from there.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_invoke_command.py tests/test_mcp_command.py tests/test_serve_command.py -q -k recorded`
Expected: all three FAIL — no record line on standard error (`invoke` has no configuration, `mcp` and `serve` are at ERROR).

- [ ] **Step 3: Implement**

Create `src/vibepy_core/logs.py`:

```python
"""How a framework process writes what it reports.

One configuration for the three processes that run an App — `serve`, `mcp` and
`invoke` — stated once so that a report line and an invocation record look the
same on each. The Cookbook leaves configuring handlers to the application; these
commands are the application, and this is their one statement of it.

Only the framework's own namespace is configured. An App's loggers are the App's
to configure, and the Web technology's loggers keep the settings its documentation
gives them.
"""

import logging.config

LOG_CONFIG: dict[str, object] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "reported": {"format": "%(message)s"},
        "server": {"format": "%(levelname)s: %(message)s"},
    },
    "handlers": {
        "reported": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "reported",
        },
        "server": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "server",
        },
    },
    "loggers": {
        "vibepy_core": {"handlers": ["reported"], "level": "INFO", "propagate": False},
        "uvicorn": {"handlers": ["server"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["server"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["server"], "level": "WARNING", "propagate": False},
    },
}
"""A `dictConfig` dictionary, which `uvicorn.run` also takes as `log_config`.

A framework record is written as its message alone: a report is one JSON object
and an invocation record is one JSON object, and a reader of this process's
standard error parses each line as such. `vibepy_core` is at INFO because the
invocation record is INFO; the framework has no other INFO line.
(<https://github.com/kludex/uvicorn/blob/main/docs/concepts/logging.md>)
"""


def configure_logging() -> None:
    """Apply `LOG_CONFIG` to this process. `serve` hands it to uvicorn instead."""
    logging.config.dictConfig(LOG_CONFIG)
```

`src/vibepy_core/serve.py`: delete the `_LOG_CONFIG` dictionary and its docstring; add `from vibepy_core.logs import LOG_CONFIG`; change the `uvicorn.run(...)` call to `log_config=LOG_CONFIG`. Remove `import logging` only if `logger` is then unused (it is defined at line 29; check with grep whether anything in the file calls `logger.` — at planning time nothing did, so remove both `logger = ...` and `import logging`).

`src/vibepy_core/mcp.py`: replace `logging.basicConfig(stream=sys.stderr, level=logging.ERROR, format="%(message)s")` with `configure_logging()`; add `from vibepy_core.logs import configure_logging`; remove `import logging`.

`src/vibepy_core/invoke.py`: add `from vibepy_core.logs import configure_logging`; call `configure_logging()` as the first statement of `main`. Keep its `logger.debug` calls and `import logging`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_invoke_command.py tests/test_mcp_command.py tests/test_serve_command.py -q`
Expected: PASS, the three new tests included. If `test_serve_command`'s new test times out reading stderr, the pipe is fine at this volume; check that `wait_for` returned (the page rendered) before suspecting the record.

- [ ] **Step 5: Document**

`docs/architecture/packaging.md` — insert a subsection before "## Running a channel":

```markdown
## What a command writes to standard error

`serve`, `mcp` and `invoke` share one logging configuration, `vibepy_core.logs`, so the three
processes that run an App write the framework's lines the same way: the `vibepy_core` loggers
at INFO, each record as its message alone, to standard error. Two kinds of line come from the
framework — a report (`ErrorInfo`, one per failure of the process or of opening its window) and
an invocation record (`InvocationRecord`, one per Tool invocation, `docs/architecture/runtime.md`)
— and each is one JSON object on one line, followed by a traceback when the record's failure is
an `execution` one. Everything else on the stream — the Web technology's own lines — is neither,
and a reader takes what validates and skips the rest, as Studio's reader of a child's log does.

An App's own loggers are not configured here. `describe` runs nothing and writes no record.
```

Then shorten the sentence in "Running a channel" that begins "The command writes one JSON object of `code`, `category`, `message` and `details`…" to "A failure of the command and a window that will not open are each one report line, as What a command writes to standard error says; see `docs/decisions/ADR-030-a-window-reports-its-own-failure.md`." and in "Opening the Agent channel" leave "the framework's own records go to standard error" as it is — it is now literally true.

- [ ] **Step 6: Gate and commit**

Run: `make lint typecheck test`
Expected: PASS.

```bash
git add src/vibepy_core/logs.py src/vibepy_core/serve.py src/vibepy_core/mcp.py src/vibepy_core/invoke.py tests/test_invoke_command.py tests/test_mcp_command.py tests/test_serve_command.py docs/architecture/packaging.md
git commit -m "The three processes that run an App share one logging configuration, so a report and an invocation record reach standard error the same way from each

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: ADR-036 and the final gate

**Files:**
- Create: `docs/decisions/ADR-036-an-invocation-is-recorded-as-one-line-by-toolruntime.md`

- [ ] **Step 1: Write the record**

```markdown
# ADR-036: An invocation is recorded as one line by ToolRuntime

Status: Accepted

## Context

Every invocation carried an id, a principal and a channel in its ToolContext, and `read_only`
was declared "for audit", yet nothing wrote any of it down. The id reached the handler alone;
a refused or unknown call had none, because the context was built after the policy ran. The
MCP adapter logged two human lines about handler failures and the Web adapter logged none, so
the channels were already observed differently. The three framework processes configured
logging three ways.

`docs/architecture/runtime.md` names ToolRuntime as where cross-cutting concerns are added and
forbids a middleware framework before a concrete need. `AGENTS.md` requires standard `logging`,
and one pydantic model for a value that crosses a process boundary. `docs/architecture/errors.md`
puts the classification of a failure in one place so that two reporters cannot disagree.

The conventions consulted: the Python Logging Cookbook (a library configures no handler; a
structured message is an object whose string form is JSON), the OpenTelemetry semantic
conventions for recording errors and for tool execution (a thrown exception is a failure; on
success no error attribute is set; tool arguments and results are opt-in and sensitive), OWASP's
Logging Cheat Sheet (when, where, who, what; log authorization and validation failures; exclude
sensitive data), the MCP specification on cancellation (log it, do not answer), asyncio on
`CancelledError` (catch, clean up, re-raise), and gRPC's status codes, where `CANCELLED` stands
apart from a client's and a server's errors.

## Decision

`ToolRuntime.invoke` writes exactly one `InvocationRecord` for every invocation it starts, as
the invocation ends, whatever way it ends — returned, raised, or cancelled — and re-raises what
it caught. The record is a frozen pydantic model in `vibepy_core.tool`: id, App, Tool, channel,
principal, start time, duration, and `error: ErrorInfo | None` as the outcome. No status field,
no arguments, no results. It is written as its JSON on the logger `vibepy_core.tool.runtime` at
INFO, with the traceback appended for an `execution` failure only. The framework configures no
handler; the three processes that run an App share one configuration in `vibepy_core.logs`.

The id is created before the Tool is resolved, so a refusal is recorded with one.

A cancellation is `tool.cancelled` in a new category, `interrupted`: the call was well formed,
the App was not at fault, something outside ended it, and the same call may succeed.
`to_error_info` classifies it, and its parameter widens to exactly
`Exception | asyncio.CancelledError`.

The MCP adapter's two log lines are removed; the record supersedes them.

Rejected:

- **OpenTelemetry** — an external dependency with no consumer here, and the MCP conventions
  that would give it a peer are at Development status. The record's fields map one-to-one
  onto the `execute_tool` attributes, so an exporter is a later adapter.
- **An observer protocol on AppDefinition** — a middleware seam before a concrete need, with no
  implementer in this repository.
- **A record per channel adapter** — two writers of one fact, which is what ToolRuntime exists
  to prevent.
- **A JSON logging library** — it formats arbitrary records and owns no schema, so a reader
  would re-declare the fields.
- **Classifying cancellation as `app.unhandled`** — false on both counts: not the App's, and
  not a failure that repeats. **A `finally` block** — cannot say what ended the invocation.
  **Recording `KeyboardInterrupt`** — the process ends, and reports its own ending (ADR-030).

## Consequences

- The Hub's per-App log file carries one structured line per Tool call on either channel, and
  a reader exists for it. Showing them in the Hub is proposed to the owner as a follow-up
  (`docs/milestones/M15/spec.md` at the time of writing; `docs/roadmap.md` thereafter).
- `ErrorCategory` has four members. A timeout code, when ADR-005's question is decided, joins
  `interrupted`.
- `ToolRuntime.invoke`'s signature is unchanged. A host that wants records elsewhere attaches a
  handler to `vibepy_core.tool.runtime`.
- A framework process's standard error is a stream of three kinds of line, and every reader of
  it parses line by line.
- Returning the invocation id to a caller (MCP `result._meta`, a Web response) is not decided
  here; the id exists to be returned when a channel needs it.
```

- [ ] **Step 2: Cross-check the documents against the code**

Run:

```bash
grep -rn "tool.cancelled\|interrupted\|InvocationRecord\|vibepy_core.logs\|ADR-036" docs/architecture docs/decisions | sort
```

Expected: `errors.md` (code, category, `to_error_info`), `runtime.md` (record section, ADR link), `tool-model.md` (steps), `packaging.md` (standard error section), `ADR-036`. If `runtime.md` still lists `audit` or `tracing` under future concerns, remove them.

- [ ] **Step 3: Final gate**

Run: `make lint typecheck test`
Expected: PASS. Note the `--durations` output; the three new process tests should each be in the range of the existing command tests.

- [ ] **Step 4: Commit**

```bash
git add docs/decisions/ADR-036-an-invocation-is-recorded-as-one-line-by-toolruntime.md docs/architecture
git commit -m "ADR-036 records why an invocation is one line written by ToolRuntime, and why a cancellation is interrupted rather than unhandled

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

Then stop: the branch is ready for the two review rounds and the structural audit before `--no-ff` merge into `main` (`superpowers:finishing-a-development-branch`). Do not push; a push happens once the milestone is merged, and its CI run is read.

## Known risks

- **Windows console encoding.** `model_dump_json()` emits non-ASCII as-is. A record whose
  `error.message` holds non-ASCII text goes through a `StreamHandler` on a pipe whose encoding
  Windows may set to a code page; `logging` then prints `--- Logging error ---` and continues.
  `report_line` has had the same property since M12 and CI has not met it; no action in M15, but
  if the Windows job shows a logging error, the fix is `sys.stderr.reconfigure(encoding="utf-8")`
  in `configure_logging`, applied to all three commands at once.
- **`caplog` and `propagate`.** The unit tests never call `configure_logging()`, so
  `vibepy_core.tool.runtime` propagates to the root and `caplog` sees it. If a future test applies
  the configuration in-process, `propagate: False` hides the records from `caplog`; use the
  subprocess tests for that case.
