"""The two things the framework does not answer: the registered wheelhouse and values.

What is installed is not kept here. Each App has an environment of its own and
`discover_apps(path=…)` reads an environment without importing it, so the file
system is the truth about installations.

The state is a Pydantic model because the file is JSON: one declaration validates
what is read and writes what is stored.
"""

import asyncio
import logging
from pathlib import Path, PurePath

from pydantic import BaseModel, JsonValue, ValidationError

from vibepy_studio.operating.internals.files import write_whole

logger = logging.getLogger(__name__)

STATE_FILE = "state.json"


class OperatingState(BaseModel):
    """Everything the operating role remembers between windows.

    A writer states what it changes, with `model_copy(update=...)`, and never
    rebuilds the whole. A writer that names every field is a writer that drops
    the next field someone adds, silently and everywhere at once.
    """

    source: PurePath | None = None
    """The one folder of wheels this operating role installs from. One, because in-house
    deployment is one wheelhouse, and two folders offering one App is a mistake to prevent rather
    than a case to explain."""

    config: dict[str, dict[str, JsonValue]] = {}
    ports: dict[str, int] = {}
    """The port each installed App serves on, allocated when it was installed."""


async def read_state(root: PurePath, /) -> OperatingState:
    """Return the stored state, or an empty one when nothing readable has been stored."""
    return await asyncio.to_thread(_read_state, root)


def _read_state(root: PurePath, /) -> OperatingState:
    path = Path(root) / STATE_FILE
    if not path.is_file():
        return OperatingState()
    try:
        return OperatingState.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError:
        logger.warning("ignoring an unreadable state file: %s", path)
        return OperatingState()


async def write_state(root: PurePath, state: OperatingState, /) -> None:
    """Replace the stored state, readable by its owner and no one else.

    The write goes to a neighbouring file and is moved into place, because
    `os.replace` overwrites the destination and the rename is atomic where POSIX
    requires it (<https://docs.python.org/3/library/os.html#os.replace>). No
    reader sees a half-written file, and a write that fails leaves the previous
    state where it was.

    The state holds the values an App runs with, secrets included, unencrypted
    and protected only by filesystem permissions. That is the same trade git's
    `store` credential helper makes and documents, and the same one it answers
    with: the file's permissions keep other users out
    (<https://git-scm.com/docs/git-credential-store>).

    `os.chmod` carries these bits on POSIX. On Windows it sets only the read-only
    flag, so a Studio root there is protected by the directory's own access control
    rather than by this call.
    """
    await asyncio.to_thread(_write_state, root, state)


def _write_state(root: PurePath, state: OperatingState, /) -> None:
    directory = Path(root)
    directory.mkdir(parents=True, exist_ok=True)
    write_whole(
        directory / STATE_FILE,
        state.model_dump_json(indent=1),
        staging=directory,
        owner_only=True,
    )
