"""The command that opens an App's Web channel, run as a real process."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from vibepy_core import Channel, ErrorCategory, ErrorInfo, InvocationRecord
from vibepy_core.app.config import ENV_PREFIX, environment_for
from vibepy_core.errors import read_report_line
from vibepy_core.tool import read_invocation_record


def child_environment() -> dict[str, str]:
    """The environment a served App is entitled to.

    pytest sets `PYTEST_CURRENT_TEST` to say which test *this* process is
    running, and NiceGUI reads that variable to decide it is under test. The
    server is a separate process running no test, so handing it that marker
    would describe it falsely.

    Also drops `VIBEPY_`-prefixed variables: a developer's exported `VIBEPY_*`
    must not leak into the child under test.
    """
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    return {name: value for name, value in env.items() if not name.startswith(ENV_PREFIX)}


def free_port() -> int:
    """A port nothing is listening on, chosen by the operating system."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def wait_for(url: str, process: "subprocess.Popen[bytes]", *, timeout: float = 30.0) -> str:
    """The body the server answers with, once it answers."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"the server exited with {process.returncode}")
        try:
            with urlopen(url) as answer:
                return answer.read().decode()
        except URLError:
            time.sleep(0.2)
    raise AssertionError(f"{url} did not answer within {timeout}s")


def todo_environment(tmp_path: Path) -> dict[str, str]:
    """The Todo App's configuration, as a served App reads it."""
    return {
        **child_environment(),
        **environment_for({"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"}),
    }


@pytest.mark.integration
def test_a_declared_page_is_served(tmp_path: Path) -> None:
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "vibepy_core.serve", "todo-app", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        env=todo_environment(tmp_path),
    )
    try:
        body = wait_for(f"http://127.0.0.1:{port}/todos", process)
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert "<html" in body.lower()


@pytest.mark.integration
def test_an_unknown_app_name_fails_with_the_framework_code() -> None:
    """`packaging.md`: a failure writes the framework's code and message."""
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.serve", "absent", "--port", str(free_port())],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode == 1
    written = json.loads(finished.stderr.decode())
    assert written["code"] == "package.app_not_declared"
    assert "absent" in written["message"]


def reported_failure(stderr: bytes, /) -> ErrorInfo:
    """The last failure the child described, out of everything it wrote.

    Read with the framework's own reader, so what a window logs is held to the
    shape core writes rather than to a second reading of it.
    """
    for line in reversed(stderr.decode(errors="replace").splitlines()):
        found = read_report_line(line)
        if found is not None:
            return found
    raise AssertionError(f"nothing was reported: {stderr.decode(errors='replace')!r}")


@pytest.mark.integration
def test_a_window_that_will_not_open_stops_the_server() -> None:
    """A refused configuration is a server that does not serve, and it says so
    in the shape every other framework failure uses.

    The App's window is the served application's lifespan, and ASGI defines that
    a server seeing `lifespan.startup.failed` logs the message and exits. What
    makes the refusal legible to whatever started the process is the window
    reporting it as it fails.
    """
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.serve", "todo-app", "--port", str(free_port())],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode != 0
    reported = reported_failure(finished.stderr)
    assert reported.code == "config.invalid"
    assert reported.category is ErrorCategory.CALLER
    assert "db_path" in reported.details["fields"]


@pytest.mark.integration
def test_a_window_that_raises_for_its_own_reason_reports_that(tmp_path: Path) -> None:
    """The general case, not one code: any failure of opening crosses with a
    code. Studio requires a root it can create, and a path under a file is
    not one, so its lifespan raises where its configuration was valid.
    """
    blocking = tmp_path / "afile"
    blocking.write_text("not a directory", encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.serve", "studio", "--port", str(free_port())],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        env={**child_environment(), **environment_for({"root": str(blocking / "root")})},
    )

    assert finished.returncode != 0
    reported = reported_failure(finished.stderr)
    assert reported.code == "app.unhandled"
    assert reported.category is ErrorCategory.EXECUTION


def records_in(stderr: str) -> list[InvocationRecord]:
    found = [read_invocation_record(line) for line in stderr.splitlines()]
    return [record for record in found if record is not None]


@pytest.mark.integration
def test_a_page_render_is_recorded_on_standard_error(tmp_path: Path) -> None:
    """Rendering `/todos` invokes `list_todos` through the Page; the record says so."""
    port = free_port()
    # stderr is read only after terminate(): a single page render writes a handful
    # of lines, far below the pipe buffer, so the child cannot block on a full
    # pipe while unread, and communicate(timeout=10) bounds the wait regardless.
    process = subprocess.Popen(
        [sys.executable, "-m", "vibepy_core.serve", "todo-app", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=todo_environment(tmp_path),
    )
    try:
        wait_for(f"http://127.0.0.1:{port}/todos", process)
    finally:
        process.terminate()
        _, stderr = process.communicate(timeout=10)

    listed = [r for r in records_in(stderr.decode(errors="replace")) if r.tool == "list_todos"]
    assert listed, stderr.decode(errors="replace")
    assert listed[0].channel is Channel.WEB
    assert listed[0].principal.id == "operator"
    assert listed[0].error is None


@pytest.mark.integration
def test_the_command_does_not_wait_on_standard_input(tmp_path: Path) -> None:
    """Standard input is left open and nothing is ever written to it. The
    command reads none of it, so the App is served regardless; a command that
    read stdin would hang here, as it hung a terminal.
    """
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "vibepy_core.serve", "todo-app", "--port", str(port)],
        stdin=subprocess.PIPE,
        env=todo_environment(tmp_path),
    )
    try:
        body = wait_for(f"http://127.0.0.1:{port}/todos", process)
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert "<html" in body.lower()


@pytest.mark.integration
def test_closing_standard_input_ends_the_command_when_asked_to(tmp_path: Path) -> None:
    """Studio holds the pipe; the OS closes it when Studio is gone for any
    reason. The App sees end-of-file and leaves through its own shutdown: the
    lifespan's exit runs, and the exit code is a clean one.

    `communicate` closes the pipe itself, which is the EOF."""
    port = free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vibepy_core.serve",
            "todo-app",
            "--port",
            str(port),
            "--until-stdin-closes",
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=todo_environment(tmp_path),
    )
    assert process.stdin is not None
    wait_for(f"http://127.0.0.1:{port}/todos", process)

    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 0, stderr.decode(errors="replace")
    with pytest.raises(URLError):
        urlopen(f"http://127.0.0.1:{port}/todos", timeout=5)
