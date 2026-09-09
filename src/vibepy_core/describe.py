"""Describe every App declared in this interpreter's environment, as JSON.

A host cannot import an App: each App is installed into an environment of its own,
and importing one would put that App's dependencies in the host's process. So the
host runs this module with that environment's interpreter and reads the result.
"""

import json
import logging
import sys
from dataclasses import asdict

from vibepy_core.app.package import describe_app, discover_apps
from vibepy_core.errors import VibepyError, to_error_info

logger = logging.getLogger(__name__)


def main() -> int:
    """Write one JSON object per declared App to standard output.

    Each object carries the identity of the declaration it describes, so a
    reader that also enumerates the environment joins the two on a name rather
    than on a position.
    """
    try:
        described = [
            {
                "app_name": ref.app_name,
                "distribution": ref.distribution,
                "distribution_version": ref.distribution_version,
                **asdict(describe_app(ref)),
            }
            for ref in discover_apps()
        ]
    except VibepyError as error:
        info = to_error_info(error)
        sys.stderr.write(json.dumps({"code": info.code, "message": info.message}) + "\n")
        return 1
    sys.stdout.write(json.dumps(described) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
