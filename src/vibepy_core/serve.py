"""Open one App's Web channel, in that App's own environment.

`vibepy_core.describe` reads a declaration; this runs one.

The adapter builds the application this serves; the command owns the process and
runs it.
"""

import argparse
import logging
import sys
from collections.abc import Mapping, Sequence
from importlib.metadata import EntryPoint
from typing import TypeGuard

import uvicorn
from pydantic import BaseModel, TypeAdapter, ValidationError

from vibepy_core.adapters.nicegui import build_web_app
from vibepy_core.app.entrypoint import AppEntrypoint
from vibepy_core.app.package import APP_GROUP, discover_apps
from vibepy_core.errors import (
    AppEntrypointInvalidError,
    AppEntrypointUnloadableError,
    AppNotDeclaredError,
    ServeConfigInvalidError,
    VibepyError,
    report_line,
    to_error_info,
)

logger = logging.getLogger(__name__)

_CONFIG = TypeAdapter(dict[str, object])
"""Standard input is one JSON object of configuration, validated as such."""

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


def _reported(error: VibepyError, /) -> None:
    """Write one failure of the command where whatever started it can read it."""
    sys.stderr.write(report_line(to_error_info(error)))


def _is_entrypoint(value: object, /) -> TypeGuard[AppEntrypoint[object, BaseModel]]:
    """Whether what a reference resolved to is a composition root.

    A runtime check cannot see type arguments, and this command never constructs
    a definition or calls a lifespan itself, so the widest pair is a sound
    reading of what was found.
    """
    return isinstance(value, AppEntrypoint)


def _entrypoint(app_name: str, /) -> AppEntrypoint[object, BaseModel]:
    """Resolve one declared App, importing only that one."""
    for ref in discover_apps():
        if ref.app_name != app_name:
            continue
        reference = f"{ref.module}:{ref.attr}"
        entry = EntryPoint(name=ref.app_name, value=reference, group=APP_GROUP)
        try:
            loaded: object = entry.load()
        except (ImportError, AttributeError) as error:
            raise AppEntrypointUnloadableError(app_name, reference) from error
        if not _is_entrypoint(loaded):
            raise AppEntrypointInvalidError(app_name, reference, type(loaded).__name__)
        return loaded
    raise AppNotDeclaredError(app_name)


def _serve(
    entrypoint: AppEntrypoint[object, BaseModel], config: Mapping[str, object], port: int, /
) -> None:
    """Serve one App for as long as its window is open."""
    served = build_web_app(entrypoint.definition, entrypoint.lifespan, config=config)
    # The window is the served application's own lifespan, so the `async with`
    # that opens it is the whole of the server's life, and a window that
    # refuses to open fails the server's startup.
    uvicorn.run(served, host="127.0.0.1", port=port, log_level="warning", log_config=_LOG_CONFIG)


def main(argv: Sequence[str], /) -> int:
    """Read configuration from standard input and serve one App.

    Exits 1 for a failure of the command itself: an App this environment does
    not declare, a declaration that will not load, or configuration that is not
    a JSON object. Each writes one JSON object of `code`, `category`, `message`
    and `details` to standard error, and each carries a framework code.
    """
    parser = argparse.ArgumentParser(prog="vibepy_core.serve")
    parser.add_argument("app_name")
    parser.add_argument("--port", type=int, required=True)
    parsed = parser.parse_args(argv)
    try:
        config: Mapping[str, object] = _CONFIG.validate_json(sys.stdin.read() or "{}")
    except ValidationError as invalid:
        _reported(ServeConfigInvalidError())
        logger.debug("configuration on standard input was unreadable", exc_info=invalid)
        return 1
    try:
        entrypoint = _entrypoint(str(parsed.app_name))
    except (
        AppNotDeclaredError,
        AppEntrypointUnloadableError,
        AppEntrypointInvalidError,
    ) as error:
        _reported(error)
        return 1
    _serve(entrypoint, config, int(parsed.port))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
