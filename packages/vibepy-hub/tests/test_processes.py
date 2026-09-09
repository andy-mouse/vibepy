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


async def test_a_cancelled_start_leaves_no_live_child(tmp_path: Path) -> None:
    """`todo-app` is declared in this interpreter's own environment and takes a
    moment to answer, so the cancellation lands while the child is starting."""
    processes = Processes(logs=tmp_path / "logs")
    starting = asyncio.create_task(
        processes.start(
            app_name="todo-app",
            interpreter=Path(sys.executable),
            config={"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
            known_as="todo-app",
        )
    )
    await asyncio.sleep(0.2)
    owned = processes.owned("todo-app")
    assert owned is not None, "the child was not owned while it was starting"

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
