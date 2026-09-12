"""The invocation record: one line per Tool call, written by ToolRuntime.

Contract in docs/architecture/runtime.md (the record) and docs/architecture/errors.md
(`tool.cancelled`). One subject: what is written, when, and that it reads back.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from vibepy_core import Channel, ErrorInfo, InvocationRecord, Principal
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
    with pytest.raises(ValidationError):
        a_record().tool = "other"
