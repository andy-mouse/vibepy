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
