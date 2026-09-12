"""Open one App's Web channel, in that App's own environment.

`vibepy_core.describe` reads a declaration; this runs one.

The adapter builds the application this serves; the command owns the process and
runs it. Its configuration is the environment's (`docs/architecture/packaging.md`,
Configuration); the command reads nothing from standard input.
"""

import argparse
import logging
import sys
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
from vibepy_core.principal import Principal

logger = logging.getLogger(__name__)

OPERATOR = Principal(id="operator")
"""The party that runs this process."""

_LOG_CONFIG: dict[str, object] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "reported": {"format": "%(message)s"},
        "server": {"format": "%(levelname)s: %(message)s"},
    },
    "handlers": {
        "reported": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "reported",
        },
        "server": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "server",
        },
    },
    "loggers": {
        "vibepy_core": {"handlers": ["reported"], "level": "ERROR", "propagate": False},
        "uvicorn": {"handlers": ["server"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["server"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["server"], "level": "WARNING", "propagate": False},
    },
}
"""How this process writes what it and its App report.

A framework record is written as its message alone, because a window's report is
one JSON object and a reader of this process's standard error parses it as such.
`uvicorn.run` takes this as a `dictConfig` dictionary
(<https://github.com/kludex/uvicorn/blob/main/docs/concepts/logging.md>).
"""


def _serve(entrypoint: AppEntrypoint[object, AppConfig], port: int, /) -> None:
    """Serve one App for as long as its window is open."""
    served = build_web_app(
        entrypoint.definition, entrypoint.lifespan, config={}, principal=OPERATOR
    )
    # The window is the served application's own lifespan, so the `async with`
    # that opens it is the whole of the server's life, and a window that
    # refuses to open fails the server's startup.
    uvicorn.run(served, host="127.0.0.1", port=port, log_level="warning", log_config=_LOG_CONFIG)


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
    _serve(entrypoint, int(parsed.port))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
