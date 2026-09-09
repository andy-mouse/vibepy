"""A child is this window's resource from the moment it exists.

`Processes` is an internal, and this file is the departure from testing public
contracts that the spec names: an orphaned child is invisible to every Hub Tool,
which is the defect itself.
"""

import asyncio
import sys
from pathlib import Path

import pytest

from vibepy_hub.internals import interpreter
from vibepy_hub.internals.processes import Processes, StartFailed

OWNED_TIMEOUT = 30.0
"""How long a child may take to exist before the test calls it a failure."""


async def _owned_once_it_exists(
    processes: Processes, app_name: str, /
) -> asyncio.subprocess.Process:
    """The child, as soon as this window owns one. Waits on the fact, not a clock."""
    async with asyncio.timeout(OWNED_TIMEOUT):
        while True:
            owned = processes.owned(app_name)
            if owned is not None:
                return owned
            await asyncio.sleep(0.01)


async def test_a_cancelled_start_leaves_no_live_child(tmp_path: Path) -> None:
    """`todo-app` is declared in this interpreter's own environment and takes a
    moment to answer, so the cancellation lands while the child is starting.

    The wait is on ownership rather than a sleep: a sleep long enough to be safe
    on a slow machine is long enough for the child to answer on a fast one, and
    then there is nothing left to cancel.
    """
    processes = Processes(logs=tmp_path / "logs")
    starting = asyncio.create_task(
        processes.start(
            app_name="todo-app",
            interpreter=Path(sys.executable),
            config={"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
            known_as="todo-app",
        )
    )
    owned = await _owned_once_it_exists(processes, "todo-app")

    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting

    assert owned.returncode is not None
    assert processes.running("todo-app") is None
    await processes.aclose()


async def test_a_child_that_dies_before_reading_its_stdin_is_a_start_failure(
    tmp_path: Path,
) -> None:
    """An environment without the framework cannot run the command at all, so
    the child is gone before it reads a configuration large enough to fill the
    pipe. That used to escape as `BrokenPipeError`."""
    env = tmp_path / "bare"
    made = await asyncio.create_subprocess_exec(
        "uv", "venv", str(env), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    assert await made.wait() == 0

    processes = Processes(logs=tmp_path / "logs")
    with pytest.raises(StartFailed):
        await processes.start(
            app_name="gone",
            interpreter=interpreter(env),
            config={"payload": "x" * 500_000},
            known_as="gone",
        )

    assert processes.running("gone") is None
    await processes.aclose()
