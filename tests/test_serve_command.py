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
    config = json.dumps({"db_path": str(tmp_path / "todo.db")})
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


def test_an_unknown_app_name_fails_with_a_message() -> None:
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.serve", "absent", "--port", str(free_port())],
        input=b"{}",
        capture_output=True,
        check=False,
        env=child_environment(),
    )
    assert finished.returncode == 1
    assert "absent" in finished.stderr.decode()


def test_a_window_that_will_not_open_stops_the_server() -> None:
    """A refused configuration is a server that does not serve.

    The App's window is the served application's lifespan, and ASGI defines that
    a server seeing `lifespan.startup.failed` logs the message and exits. So the
    command ends rather than answering for an App that never opened.
    """
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.serve", "todo-app", "--port", str(free_port())],
        input=b"{}",
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode != 0
    written = finished.stderr.decode()
    assert "config.invalid" in written or "AppConfigInvalidError" in written
