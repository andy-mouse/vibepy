"""A child is this window's resource from the moment it exists.

`Processes` is an internal, and this file is the departure from testing public
contracts that the spec names: an orphaned child is invisible to every Hub Tool,
which is the defect itself.
"""

import asyncio
import sys
from pathlib import Path

import pytest

from tests_support import free_port
from vibepy_hub.internals import interpreter
from vibepy_hub.internals.processes import (
    AlreadyStarted,
    Processes,
    StartFailed,
    _reported,  # pyright: ignore[reportPrivateUsage]
)

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


@pytest.mark.integration
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
            port=free_port(),
        )
    )
    owned = await _owned_once_it_exists(processes, "todo-app")

    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting

    assert owned.returncode is not None
    assert processes.running("todo-app") is False
    await processes.aclose()


@pytest.mark.integration
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
            port=free_port(),
        )

    assert processes.running("gone") is False
    await processes.aclose()


async def _who_holds(port: int, child_pid: int, /) -> str:
    """Diagnostic for CI: which process still answers on a killed child's port."""
    if sys.platform == "win32":
        commands = [
            ["netstat", "-ano"],
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/V"],
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' } "
                "| Select-Object ProcessId,ParentProcessId,CommandLine | Format-List",
            ],
        ]
    else:
        commands = [["lsof", "-nP", "-i", f":{port}"], ["ps", "-ef"]]
    parts = [
        f"port {port} still answers; killed child pid {child_pid}; sys.executable {sys.executable}"
    ]
    for command in commands:
        proc = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        out, _ = await proc.communicate()
        text = out.decode(errors="replace")
        if command[0] == "netstat":
            text = "\n".join(line for line in text.splitlines() if f":{port}" in line)
        parts.append(f"$ {' '.join(command)}\n{text}")
    return "\n\n".join(parts)


@pytest.mark.integration
async def test_closing_a_window_releases_every_child(tmp_path: Path) -> None:
    """`aclose` is what `entry.py` promises: a window leaves no child behind.

    Asserted here rather than through a Hub Tool, because it is a fact about
    `Processes` that no Tool can see -- which is what this file is for.
    """
    processes = Processes(logs=tmp_path / "logs")
    port = free_port()
    await processes.start(
        app_name="todo-app",
        interpreter=Path(sys.executable),
        config={"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
        known_as="todo-app",
        port=port,
    )
    assert processes.running("todo-app") is True
    child = await _owned_once_it_exists(processes, "todo-app")

    await processes.aclose()

    assert processes.running("todo-app") is False
    try:
        await asyncio.open_connection("127.0.0.1", port)
    except OSError:
        return
    pytest.fail(await _who_holds(port, child.pid))


@pytest.mark.integration
async def test_a_second_start_under_one_name_leaves_no_second_child(tmp_path: Path) -> None:
    """One name holds one child, and the start that was refused started nothing."""
    processes = Processes(logs=tmp_path / "logs")
    first, second = free_port(), free_port()
    config: dict[str, object] = {"db_path": str(tmp_path / "todo.json"), "db_key": "k"}
    await processes.start(
        app_name="todo-app",
        interpreter=Path(sys.executable),
        config=config,
        known_as="todo-app",
        port=first,
    )
    with pytest.raises(AlreadyStarted):
        await processes.start(
            app_name="todo-app",
            interpreter=Path(sys.executable),
            config=config,
            known_as="todo-app",
            port=second,
        )

    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", second)
    await processes.aclose()


def test_a_report_followed_by_more_output_is_still_found(tmp_path: Path) -> None:
    """A traceback the framework writes after its own report must not hide it.

    A real child writes its report near the top of the log and a traceback
    after it, long enough that a fixed-size tail would push the report out.
    """
    log = tmp_path / "child.log"
    report = '{"code": "config.invalid", "category": "caller", "message": "bad"}'
    trailer = "\n".join(f"line {n} of a long traceback" for n in range(400))
    log.write_text(f"{report}\n{trailer}\n", encoding="utf-8")
    assert len(trailer) > 4000

    failure = _reported(log)

    assert failure is not None
    assert failure.code == "config.invalid"
