"""The command that opens an App's Web channel, run as a real process."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import TypedDict, cast
from urllib.error import URLError
from urllib.request import urlopen


def child_environment() -> dict[str, str]:
    """The environment a served App is entitled to.

    pytest sets `PYTEST_CURRENT_TEST` to say which test *this* process is
    running, and NiceGUI reads that variable to decide it is under test. The
    server is a separate process running no test, so handing it that marker
    would describe it falsely.
    """
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    return env


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


def test_a_declared_page_is_served(tmp_path: Path) -> None:
    port = free_port()
    config = json.dumps({"db_path": str(tmp_path / "todo.json"), "db_key": "test-key"})
    process = subprocess.Popen(
        [sys.executable, "-m", "vibepy_core.serve", "todo-app", "--port", str(port)],
        stdin=subprocess.PIPE,
        env=child_environment(),
    )
    assert process.stdin is not None
    process.stdin.write(config.encode())
    process.stdin.close()
    try:
        body = wait_for(f"http://127.0.0.1:{port}/todos", process)
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert "<html" in body.lower()


def test_an_unknown_app_name_fails_with_the_framework_code() -> None:
    """`packaging.md`: a failure writes the framework's code and message."""
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.serve", "absent", "--port", str(free_port())],
        input=b"{}",
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode == 1
    written = json.loads(finished.stderr.decode())
    assert written["code"] == "package.app_not_declared"
    assert "absent" in written["message"]


class Reported(TypedDict):
    """One failure a child described, as this test reads it."""

    code: str
    category: str
    message: str
    details: dict[str, str]


def _reported(stderr: bytes, /) -> Reported:
    """The last failure the child described, out of everything it wrote."""
    for line in reversed(stderr.decode(errors="replace").splitlines()):
        try:
            parsed: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "code" in parsed:
            return cast(Reported, parsed)
    raise AssertionError(f"nothing was reported: {stderr.decode(errors='replace')!r}")


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
        input=b"{}",
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode != 0
    reported = _reported(finished.stderr)
    assert reported["code"] == "config.invalid"
    assert reported["category"] == "caller"
    assert "db_path" in reported["details"]["fields"]


def test_a_window_that_raises_for_its_own_reason_reports_that(tmp_path: Path) -> None:
    """The general case, not one code: any failure of opening crosses with a
    code. The Hub App requires a root it can create, and a path under a file is
    not one, so its lifespan raises where its configuration was valid.
    """
    blocking = tmp_path / "afile"
    blocking.write_text("not a directory", encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.serve", "hub", "--port", str(free_port())],
        input=json.dumps({"root": str(blocking / "root")}).encode(),
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode != 0
    reported = _reported(finished.stderr)
    assert reported["code"] == "app.unhandled"
    assert reported["category"] == "execution"


def test_configuration_that_is_not_an_object_fails_with_a_framework_code() -> None:
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.serve", "todo-app", "--port", str(free_port())],
        input=b"[]",
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode == 1
    reported = _reported(finished.stderr)
    assert reported["code"] == "serve.config_invalid"
    assert reported["category"] == "caller"
