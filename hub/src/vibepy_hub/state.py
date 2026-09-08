"""The two things the framework does not answer: registered folders and values.

What is installed is not kept here. Each App has an environment of its own and
`discover_apps(path=…)` reads an environment without importing it, so the file
system is the truth about installations.

The state is a Pydantic model because the file is JSON: one declaration validates
what is read and writes what is stored.
"""

import logging
from pathlib import Path

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

STATE_FILE = "state.json"


class HubState(BaseModel):
    """Everything the Hub remembers between windows."""

    sources: list[Path] = []
    config: dict[str, dict[str, object]] = {}


def read_state(root: Path, /) -> HubState:
    """The stored state, or an empty one when nothing readable has been stored."""
    path = root / STATE_FILE
    if not path.is_file():
        return HubState()
    try:
        return HubState.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError:
        logger.warning("ignoring an unreadable state file: %s", path)
        return HubState()


def write_state(root: Path, state: HubState, /) -> None:
    """Replace the stored state."""
    root.mkdir(parents=True, exist_ok=True)
    (root / STATE_FILE).write_text(state.model_dump_json(indent=1), encoding="utf-8")
