"""How a framework process writes what it reports.

One configuration for the three processes that run an App — `serve`, `mcp` and
`invoke` — stated once so that a report line and an invocation record look the
same on each. The Cookbook leaves configuring handlers to the application; these
commands are the application, and this is their one statement of it.

Only the framework's own namespace is configured. An App's loggers are the App's
to configure, and the Web technology's loggers keep the settings its documentation
gives them.
"""

import logging.config

LOG_CONFIG: dict[str, object] = {
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
        "vibepy_core": {"handlers": ["reported"], "level": "INFO", "propagate": False},
        "uvicorn": {"handlers": ["server"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["server"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["server"], "level": "WARNING", "propagate": False},
    },
}
"""A `dictConfig` dictionary, which `uvicorn.run` also takes as `log_config`.

A framework record is written as its message alone: a report is one JSON object
and an invocation record is one JSON object, and a reader of this process's
standard error parses each line as such. `vibepy_core` is at INFO because the
invocation record is INFO; the framework has no other INFO line.
(<https://github.com/kludex/uvicorn/blob/main/docs/concepts/logging.md>)
"""


def configure_logging() -> None:
    """Apply `LOG_CONFIG` to this process. `serve` hands it to uvicorn instead."""
    logging.config.dictConfig(LOG_CONFIG)
