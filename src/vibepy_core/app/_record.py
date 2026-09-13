"""One window, written down as it closes.

The record crosses a process boundary — a framework process writes it to standard
error, and whatever started the process reads it — so it is one pydantic model:
the window dumps it, a reader validates it, and no surface re-declares its
fields. It lives with the App vocabulary it is made of, next to the composition
that opens the window, not with the command that transports it, per
`docs/decisions/ADR-035-the-package-root-is-the-app-authors-vocabulary.md`.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, ValidationError

from vibepy_core.channel import Channel


class WindowRecord(BaseModel):
    """Which App's window closed, for which channel, and when.

    Written once the App's lifespan has exited, so the record witnesses the
    release of the resource and not merely the end of the runtime. A window that
    ends by raising writes no record: that ending is already one report
    (`ErrorInfo`), and the same fact is not stated twice.

    The window's opening is not carried: a process that serves one window opens
    it before it can write anything a reader would correlate, and what a reader
    wants of this line is that the window is gone.
    """

    model_config = ConfigDict(frozen=True)

    app_id: str
    channel: Channel
    closed_at: datetime


def read_window_record(line: str, /) -> WindowRecord | None:
    """Read one line as the record a closing window writes, or `None` if it is not one.

    Reading belongs beside writing, as `read_invocation_record` does for an
    invocation. A framework process's standard error carries reports, records and
    other lines on one stream; a reader takes what validates and skips the rest.
    """
    try:
        return WindowRecord.model_validate_json(line)
    except ValidationError:
        return None
