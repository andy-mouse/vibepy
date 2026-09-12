"""The invocation record: one line per Tool call, written by ToolRuntime.

Contract in docs/architecture/runtime.md (the record) and docs/architecture/errors.md
(`tool.cancelled`). One subject: what is written, when, and that it reads back.
"""

import asyncio
import logging
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from vibepy_core import Channel, ErrorCategory, ErrorInfo, InvocationRecord, Principal
from vibepy_core.errors import (
    ToolForbiddenError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    read_report_line,
    report_line,
    to_error_info,
)
from vibepy_core.tool import (
    Tool,
    ToolContext,
    ToolDefinition,
    ToolHandler,
    ToolRegistry,
    ToolRuntime,
    read_invocation_record,
)

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
    with pytest.raises(ValidationError):
        a_record().tool = "other"


RUNTIME_LOGGER = "vibepy_core.tool.runtime"
"""The logger `docs/architecture/runtime.md` documents. A host attaches its handler here."""


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


def tool(
    name: str,
    handler: ToolHandler[Seen, Empty, BaseModel],
    *,
    output: type[BaseModel] = Empty,
    channels: frozenset[Channel] = frozenset(Channel),
) -> Tool[Seen]:
    return Tool(
        definition=ToolDefinition(
            name=name,
            description=name,
            input_model=Empty,
            output_model=output,
            read_only=True,
            channels=channels,
        ),
        handler=handler,
    )


def runtime(*tools: Tool[Seen], channel: Channel = Channel.AGENT) -> tuple[ToolRuntime[Seen], Seen]:
    registry: ToolRegistry[Seen] = ToolRegistry()
    for one in tools:
        registry.register(one)
    seen = Seen()
    run = ToolRuntime(app_id="observed", registry=registry, dependencies=seen, channel=channel)
    return run, seen


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
