"""The two things the framework does not answer: registered folders and values.

What is installed is not kept here. Each App has an environment of its own and
`discover_apps(path=…)` reads an environment without importing it, so the file
system is the truth about installations.

The state is a Pydantic model because the file is JSON: one declaration validates
what is read and writes what is stored.
"""

import asyncio
import logging
import os
import stat
import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from vibepy_hub.internals.deps import HubDeps

logger = logging.getLogger(__name__)

STATE_FILE = "state.json"


class HubState(BaseModel):
    """Everything the Hub remembers between windows."""

    sources: list[Path] = []
    config: dict[str, dict[str, object]] = {}
    ports: dict[str, int] = {}
    """The port each installed App serves on, allocated when it was installed."""


async def read_state(root: Path, /) -> HubState:
    """The stored state, or an empty one when nothing readable has been stored."""
    return await asyncio.to_thread(_read_state, root)


def _read_state(root: Path, /) -> HubState:
    path = root / STATE_FILE
    if not path.is_file():
        return HubState()
    try:
        return HubState.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError:
        logger.warning("ignoring an unreadable state file: %s", path)
        return HubState()


OWNER_ONLY_FILE = stat.S_IRUSR | stat.S_IWUSR
OWNER_ONLY_DIRECTORY = stat.S_IRWXU


async def write_state(root: Path, state: HubState, /) -> None:
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
    flag, so a Hub root there is protected by the directory's own access control
    rather than by this call.
    """
    await asyncio.to_thread(_write_state, root, state)


def _write_state(root: Path, state: HubState, /) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / STATE_FILE
    pending = root / f"{STATE_FILE}.pending"
    pending.write_text(state.model_dump_json(indent=1), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(root, OWNER_ONLY_DIRECTORY)
        os.chmod(pending, OWNER_ONLY_FILE)
    try:
        os.replace(pending, path)
    except OSError:
        pending.unlink(missing_ok=True)
        raise


async def update_state(deps: HubDeps, change: Callable[[HubState], HubState], /) -> HubState:
    """Read, change and store the state, with no other call in between.

    ToolRuntime permits concurrent invocations and does not serialize them, so
    a read-modify-write is the App's own to make safe --
    `docs/architecture/runtime.md` puts overlapping mutation in the domain row.
    The lock is the window's, which is where application-scoped state belongs.
    """
    async with deps.state_lock:
        changed = change(await read_state(deps.root))
        await write_state(deps.root, changed)
        return changed
