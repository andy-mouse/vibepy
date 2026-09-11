"""The board's rules, stated once and away from the screen.

Everything here is a function of Tool output. It imports no Web technology, so
the rules the mockup states — which actions a state gets, when Start is
disabled, what a save sends — are checked without rendering anything.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vibepy_hub.models import AppRow, ConfigField, Diagnostic

STAGES: tuple[str, str, str, str] = ("Available", "Installed", "Configured", "Running")
_ORDER = {"running": 0, "installed": 1, "available": 2}


@dataclass(frozen=True)
class Mark:
    """One step of a row's rail."""

    label: str
    done: bool
    symbol: str


@dataclass(frozen=True)
class Action:
    """One button, and the Tool it invokes."""

    label: str
    tool: str
    primary: bool
    enabled: bool = True


@dataclass(frozen=True)
class RowView:
    """One App as the board shows it."""

    app_name: str
    title: str
    version: str | None
    marks: tuple[Mark, Mark, Mark, Mark]
    actions: tuple[Action, ...]
    diagnostic: Diagnostic | None


def _stage(row: AppRow, /, *, configured: bool) -> int:
    if row.state == "available":
        return 0
    if row.state == "running":
        return 3
    return 2 if configured else 1


def _mark_symbol(index: int, row: AppRow, /, *, needs_configuration: bool) -> str:
    if index == 2 and needs_configuration:
        return "!"
    if index == 1 and row.available_version is not None:
        return "↑"
    return "✓"


def row_view(row: AppRow, /, *, declares_fields: bool) -> RowView:
    """Describe one row: its rail, its actions, its diagnostic.

    An App declaring no fields is configured the moment it is installed; the Tool
    already says so in `configured`, and `declares_fields` only decides whether a
    Configure button has anything to open.
    """
    configured = row.configured or not declares_fields
    needs_configuration = row.state == "installed" and row.diagnostic is None and not configured
    stage = _stage(row, configured=configured)
    marks = tuple(
        Mark(
            label=label,
            done=index <= stage,
            symbol=_mark_symbol(index, row, needs_configuration=needs_configuration),
        )
        for index, label in enumerate(STAGES)
    )
    return RowView(
        app_name=row.app_name,
        title=row.name or row.app_name,
        version=row.distribution_version,
        marks=(marks[0], marks[1], marks[2], marks[3]),
        actions=_actions(row, configured=configured, declares_fields=declares_fields),
        diagnostic=row.diagnostic,
    )


def _actions(row: AppRow, /, *, configured: bool, declares_fields: bool) -> tuple[Action, ...]:
    if row.state == "available":
        return (Action("Install", "install_app", primary=True),)
    if row.state == "running":
        return (Action("Stop", "stop_app", primary=False),)
    if row.diagnostic is not None:
        return (Action("Uninstall", "remove_app", primary=False),)
    actions = [Action("Uninstall", "remove_app", primary=False)]
    if declares_fields:
        actions.append(Action("Configure", "describe_config", primary=not configured))
    if row.available_version is not None:
        actions.append(Action("Update", "update_app", primary=configured))
    else:
        # A window validates configuration before it acquires anything, so
        # starting an unconfigured App would only fail. Say so up front.
        actions.append(Action("Start", "start_app", primary=configured, enabled=configured))
    return tuple(actions)


def sort_rows(rows: Sequence[AppRow], /) -> list[AppRow]:
    """Sort running first, then installed, then available; by title within a state."""
    return sorted(
        rows,
        key=lambda row: (_ORDER.get(row.state, 3), (row.name or row.app_name).casefold()),
    )


def summary(rows: Sequence[AppRow], /) -> tuple[int, int, int]:
    """Count how many Apps are available, installed and running."""
    states = [row.state for row in rows]
    return states.count("available"), states.count("installed"), states.count("running")


def save_request(
    fields: Sequence[ConfigField],
    entered: Mapping[str, str],
    secrets_set: Sequence[str],
    /,
) -> dict[str, object] | list[str]:
    """Build what a Save sends to `configure_app`, or the required fields it still lacks.

    An empty secret is omitted, which the Hub reads as "keep what is held": a
    screen must not be able to blank a stored secret. A required field with no
    value and no held secret is named, and every such field is named at once.
    """
    values: dict[str, object] = {}
    for field in fields:
        typed = entered.get(field.name, "").strip()
        if field.type == "secret":
            if typed:
                values[field.name] = typed
            continue
        if field.name in entered:
            values[field.name] = typed
    missing = [
        field.name
        for field in fields
        if field.required
        and not entered.get(field.name, "").strip()
        and field.name not in secrets_set
    ]
    return missing if missing else values
