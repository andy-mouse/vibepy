"""Describe every App declared in this interpreter's environment, as JSON.

A host cannot import an App: each App is installed into an environment of its own,
and importing one would put that App's dependencies in the host's process. So the
host runs this module with that environment's interpreter and reads the result.
"""

import logging
import sys

from pydantic import TypeAdapter

from vibepy_core.app.entrypoint import DescribedApp
from vibepy_core.app.package import described, discover_apps
from vibepy_core.errors import VibepyError, report

__all__ = ["main"]


logger = logging.getLogger(__name__)

_DESCRIBED = TypeAdapter(list[DescribedApp])
"""The whole answer as one value, so the command writes what a reader validates."""


def main() -> int:
    """Write one JSON object per declared App to standard output.

    Each object carries the identity of the declaration it describes, so a
    reader that also enumerates the environment joins the two on a name rather
    than on a position.
    """
    try:
        written = _DESCRIBED.dump_json([described(ref) for ref in discover_apps()])
    except VibepyError as error:
        report(error)
        return 1
    sys.stdout.write(written.decode() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
