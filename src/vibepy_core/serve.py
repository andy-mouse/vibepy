"""Open one App's Web channel, in that App's own environment.

`vibepy_core.describe` reads a declaration; this runs one.

The adapter builds the application this serves; the command owns the process and
runs it. Its configuration is the environment's (`docs/architecture/packaging.md`,
Configuration); the command reads no configuration from standard input; with
`--until-stdin-closes` it reads standard input only to learn that its launcher
has gone.
"""

import argparse
import sys
import threading
from collections.abc import Sequence

import uvicorn

from vibepy_core.adapters.nicegui import build_web_app
from vibepy_core.app.config import AppConfig
from vibepy_core.app.entrypoint import AppEntrypoint
from vibepy_core.app.package import load_app
from vibepy_core.errors import (
    AppEntrypointInvalidError,
    AppEntrypointUnloadableError,
    AppNotDeclaredError,
    report,
)
from vibepy_core.logs import LOG_CONFIG
from vibepy_core.principal import Principal

OPERATOR = Principal(id="operator")
"""The party that runs this process."""

STARTUP_FAILURE = 3
"""uvicorn's own exit code for a server that never started (`uvicorn.main`)."""


def _end_on_stdin_eof(server: uvicorn.Server, /) -> None:
    """Block on standard input until it closes, then ask the server to leave.

    `should_exit` is what uvicorn's loop polls each tick; the documentation
    exposes no other programmatic stop, so the server's code is the authority.
    Reached only when the launcher asked for it, because a process manager gives
    a service `/dev/null` as standard input and a command that ended on
    end-of-file regardless would end at once under it.
    """
    sys.stdin.buffer.read()
    server.should_exit = True


def _serve(
    entrypoint: AppEntrypoint[object, AppConfig], port: int, /, *, until_stdin_closes: bool
) -> int:
    """Serve one App for as long as its window is open; return the exit code."""
    served = build_web_app(
        entrypoint.definition, entrypoint.lifespan, config={}, principal=OPERATOR
    )
    # The window is the served application's own lifespan, so the `async with`
    # that opens it is the whole of the server's life, and a window that
    # refuses to open fails the server's startup.
    server = uvicorn.Server(
        uvicorn.Config(
            served, host="127.0.0.1", port=port, log_level="warning", log_config=LOG_CONFIG
        )
    )
    if until_stdin_closes:
        threading.Thread(target=_end_on_stdin_eof, args=(server,), daemon=True).start()
    server.run()
    return 0 if server.started else STARTUP_FAILURE


def main(argv: Sequence[str], /) -> int:
    """Read configuration from the environment and serve one App.

    `VIBEPY_<FIELD>` per declared field; the command reads nothing from
    standard input.

    Exits 1 for a failure of the command itself: an App this environment does
    not declare, or a declaration that will not load. Each writes one JSON
    object of `code`, `category`, `message` and `details` to standard error,
    and each carries a framework code.
    """
    parser = argparse.ArgumentParser(prog="vibepy_core.serve")
    parser.add_argument("app_name")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--until-stdin-closes",
        action="store_true",
        help="end the server when standard input reaches end-of-file; for a launcher holding a pipe",  # noqa: E501
    )
    parsed = parser.parse_args(argv)
    try:
        entrypoint = load_app(str(parsed.app_name))
    except (
        AppNotDeclaredError,
        AppEntrypointUnloadableError,
        AppEntrypointInvalidError,
    ) as error:
        report(error)
        return 1
    return _serve(entrypoint, int(parsed.port), until_stdin_closes=bool(parsed.until_stdin_closes))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
