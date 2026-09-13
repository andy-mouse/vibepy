"""A child is this window's resource from the moment it exists.

`Processes` is an internal, and this file is the departure from testing public
contracts that the spec names: an orphaned child is invisible to every operating Tool,
which is the defect itself.
"""

import asyncio
import sys
from pathlib import Path
from urllib.request import urlopen

import pytest
from pydantic import JsonValue

from tests_support import free_port
from vibepy_core import ErrorCategory
from vibepy_studio.internals.processes import (
    NotRunnable,
    child_environment,
    python_command,
    reported,
    reports,
    run,
)
from vibepy_studio.operating.internals import interpreter
from vibepy_studio.operating.internals.processes import (
    AlreadyStarted,
    Processes,
    StartFailed,
    _reported,  # pyright: ignore[reportPrivateUsage]
)

OWNED_TIMEOUT = 30.0
"""How long a child may take to exist before the test calls it a failure."""


def _body(url: str, /) -> str:
    """What the child answers at `url`, as text."""
    with urlopen(url, timeout=30) as answer:
        return answer.read().decode(errors="replace")


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
            cwd=tmp_path,
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
async def test_a_child_that_cannot_run_the_command_is_a_start_failure(
    tmp_path: Path,
) -> None:
    """An environment without the framework cannot run the command at all, so
    the child exits before it answers."""
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
            config={"db_path": "x", "db_key": "k"},
            known_as="gone",
            port=free_port(),
            cwd=tmp_path,
        )

    assert processes.running("gone") is False
    await processes.aclose()


@pytest.mark.integration
async def test_closing_a_window_releases_every_child(tmp_path: Path) -> None:
    """`aclose` is what `entry.py` promises: a window leaves no child behind.

    Asserted here rather than through an operating Tool, because it is a fact about
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
        cwd=tmp_path,
    )
    assert processes.running("todo-app") is True

    await processes.aclose()

    assert processes.running("todo-app") is False
    # Windows keeps a killed process's listening socket for a moment, accepting
    # and then resetting connections before it refuses them; the promise is that
    # the port is given up, not that the kernel is done in the same instant.
    async with asyncio.timeout(OWNED_TIMEOUT):
        while True:
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", port)
            except OSError:
                break
            writer.transport.abort()
            await asyncio.sleep(0.05)


@pytest.mark.integration
async def test_a_second_start_under_one_name_leaves_no_second_child(tmp_path: Path) -> None:
    """One name holds one child, and the start that was refused started nothing."""
    processes = Processes(logs=tmp_path / "logs")
    first, second = free_port(), free_port()
    config: dict[str, JsonValue] = {"db_path": str(tmp_path / "todo.json"), "db_key": "k"}
    await processes.start(
        app_name="todo-app",
        interpreter=Path(sys.executable),
        config=config,
        known_as="todo-app",
        port=first,
        cwd=tmp_path,
    )
    with pytest.raises(AlreadyStarted):
        await processes.start(
            app_name="todo-app",
            interpreter=Path(sys.executable),
            config=config,
            known_as="todo-app",
            port=second,
            cwd=tmp_path,
        )

    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", second)
    await processes.aclose()


@pytest.mark.integration
async def test_a_spawn_that_fails_leaves_the_name_free(tmp_path: Path) -> None:
    """A `cwd` that does not exist fails the spawn itself, before a child ever
    exists to release; the claim made ahead of it must not outlive the failure."""
    processes = Processes(logs=tmp_path / "logs")
    config: dict[str, JsonValue] = {"db_path": str(tmp_path / "todo.json"), "db_key": "k"}
    with pytest.raises(OSError):
        await processes.start(
            app_name="todo-app",
            interpreter=Path(sys.executable),
            config=config,
            known_as="todo-app",
            port=free_port(),
            cwd=tmp_path / "does-not-exist",
        )

    await processes.start(
        app_name="todo-app",
        interpreter=Path(sys.executable),
        config=config,
        known_as="todo-app",
        port=free_port(),
        cwd=tmp_path,
    )
    assert processes.running("todo-app") is True
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


@pytest.mark.integration
async def test_run_returns_both_streams_and_the_exit_code() -> None:
    completed = await run(
        [
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)",
        ]
    )
    assert completed.returncode == 3
    assert completed.stdout.strip() == "out"
    assert completed.stderr.strip() == "err"


@pytest.mark.integration
async def test_run_hands_the_child_standard_input() -> None:
    completed = await run(
        [sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"], stdin="hello"
    )
    assert completed.stdout.strip() == "HELLO"


async def test_run_refuses_a_program_that_is_not_there() -> None:
    with pytest.raises(NotRunnable):
        await run(["no-such-program-anywhere"])


def test_child_environment_drops_vibepy_prefixed_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBEPY_SOMETHING", "parent-only")
    monkeypatch.setenv("AN_UNRELATED_VARIABLE", "survives")
    env = child_environment()
    assert "VIBEPY_SOMETHING" not in env
    assert env.get("AN_UNRELATED_VARIABLE") == "survives"


def test_reported_reads_the_report_among_other_lines() -> None:
    text = (
        'noise\n{"code": "tool.not_found", "category": "caller", "message": "m",'
        ' "details": {}}\nTraceback\n'
    )
    found = reported(text)
    assert found is not None
    assert found.code == "tool.not_found"
    assert found.category == ErrorCategory.CALLER
    assert reported("nothing here") is None


@pytest.mark.integration
async def test_a_child_does_not_see_what_pythonpath_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The outcome, not the list: `-I` is Python's guarantee that `PYTHON*`
    is ignored, and this is what that guarantee buys the App."""
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "planted_module.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(planted))

    completed = await run(python_command([sys.executable], "-c", "import planted_module"))

    assert completed.returncode != 0
    assert "planted_module" in completed.stderr


@pytest.mark.integration
async def test_a_child_does_not_see_the_launchers_current_directory(tmp_path: Path) -> None:
    """`python -m` and `python -c` put the current directory on `sys.path`;
    `-I` does not, so a module beside Studio is not the App's."""
    (tmp_path / "beside_studio.py").write_text("", encoding="utf-8")

    completed = await run(
        python_command([sys.executable], "-c", "import beside_studio"), cwd=tmp_path
    )

    assert completed.returncode != 0


def test_python_command_puts_isolated_mode_before_the_program() -> None:
    assert python_command(["uv", "run", "python"], "-m", "vibepy_core.describe") == [
        "uv",
        "run",
        "python",
        "-I",
        "-m",
        "vibepy_core.describe",
    ]


def test_reports_reads_every_report_line_in_order() -> None:
    text = (
        '{"code": "app.declaration_invalid", "category": "declaration", "message": "m",'
        ' "details": {"count": "1"}}\n'
        '{"code": "tool.name_conflict", "category": "declaration", "message": "m",'
        ' "details": {}}\nTraceback\n'
    )
    found = reports(text)
    assert [info.code for info in found] == ["app.declaration_invalid", "tool.name_conflict"]
    first = reported(text)
    assert first is not None and first.code == "app.declaration_invalid"
    assert reports("nothing here") == ()


DRIVER = """
import asyncio, sys
from pathlib import Path
from vibepy_studio.operating.internals.processes import Processes

async def main() -> None:
    port = int(sys.argv[1])
    root = Path(sys.argv[2])
    processes = Processes(logs=root / "logs")
    await processes.start(
        app_name="todo-app",
        interpreter=Path(sys.executable),
        config={"db_path": str(root / "todo.json"), "db_key": "k"},
        known_as="todo-app",
        port=port,
        cwd=root,
    )
    print("started", flush=True)
    await asyncio.sleep(3600)

asyncio.run(main())
"""


@pytest.mark.integration
async def test_a_killed_launcher_leaves_no_live_child(tmp_path: Path) -> None:
    """The half of process isolation `aclose` cannot cover: the Studio that is
    killed runs no cleanup. The child holds the read end of a pipe whose write
    end died with the Studio, sees end-of-file, and leaves on its own."""
    port = free_port()
    driver = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        DRIVER,
        str(port),
        str(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        env=child_environment(),
    )
    assert driver.stdout is not None
    async with asyncio.timeout(OWNED_TIMEOUT):
        assert (await driver.stdout.readline()).strip() == b"started"

    driver.kill()
    await driver.wait()

    async with asyncio.timeout(OWNED_TIMEOUT):
        while True:
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", port)
            except OSError:
                break
            writer.transport.abort()
            await asyncio.sleep(0.05)


@pytest.mark.integration
async def test_a_child_stands_in_the_directory_it_is_given(tmp_path: Path) -> None:
    """`probe.txt` is what Timer writes when it names a file and no folder."""
    stand = tmp_path / "stand"
    stand.mkdir()
    processes = Processes(logs=tmp_path / "logs")
    port = free_port()
    await processes.start(
        app_name="timer-app",
        interpreter=Path(sys.executable),
        config={},
        known_as="timer-app",
        port=port,
        cwd=stand,
    )
    try:
        body = await asyncio.to_thread(_body, f"http://127.0.0.1:{port}/home")
    finally:
        await processes.aclose()

    assert f"cwd={stand.resolve()}" in body
    assert (stand / "probe.txt").is_file()
