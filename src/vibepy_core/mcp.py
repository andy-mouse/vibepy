"""Open one App's Agent channel over stdio, in that App's own environment.

`vibepy_core.serve` runs an App's Web channel; this runs its Agent channel. The
adapter builds the server; the MCP client owns this process and speaks to it
over standard input and output, so this command runs the server and writes
nothing of its own to standard output. Its configuration is the environment's,
`VIBEPY_<FIELD>` per declared field, as for every framework command.
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from typing import cast

from mcp.server.stdio import stdio_server

from vibepy_core.adapters.mcp import build_mcp_server
from vibepy_core.app.config import AppConfig
from vibepy_core.app.entrypoint import AppEntrypoint
from vibepy_core.app.package import load_app
from vibepy_core.errors import (
    AppEntrypointInvalidError,
    AppEntrypointUnloadableError,
    AppNotDeclaredError,
    report,
)

logger = logging.getLogger(__name__)


def _unwrapped(error: Exception, /) -> Exception:
    """Unwrap the single failure inside an anyio `TaskGroup`'s `ExceptionGroup`.

    `stdio_server` and the session it opens run inside task groups, so a
    window that refuses during `Server.run` reaches this process wrapped one or
    more times. Unwrapping is safe here because there is exactly one leaf: the
    window opens a single dependency. A group with more than one leaf is left
    wrapped and reported as itself, as `app.unhandled`.
    """
    while isinstance(error, ExceptionGroup):
        exceptions = cast("tuple[Exception, ...]", error.exceptions)
        if len(exceptions) != 1:
            break
        error = exceptions[0]
    return cast(Exception, error)


async def _serve(entrypoint: AppEntrypoint[object, AppConfig], /) -> None:
    """Run the server for as long as the client keeps this process alive.

    `Server.run` enters the App's window, so the window is the process.
    """
    server = build_mcp_server(entrypoint.definition, entrypoint.lifespan, config={})
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(argv: Sequence[str], /) -> int:
    """Serve one App's Tools over stdio.

    Exits 1 with one report line on standard error for a failure of the command
    itself -- an App this environment does not declare or cannot load -- and for
    a window that will not open, which `Server.run` propagates as it enters the
    lifespan. Standard output carries MCP messages and nothing else.
    """
    logging.basicConfig(stream=sys.stderr, level=logging.ERROR, format="%(message)s")
    parser = argparse.ArgumentParser(prog="vibepy_core.mcp")
    parser.add_argument("app_name")
    parsed = parser.parse_args(argv)
    try:
        entrypoint = load_app(str(parsed.app_name))
    except (AppNotDeclaredError, AppEntrypointUnloadableError, AppEntrypointInvalidError) as error:
        report(error)
        return 1
    try:
        asyncio.run(_serve(entrypoint))
    except Exception as error:
        # The window reports its own failure (ADR-030); the SDK's task groups wrap it.
        report(_unwrapped(error))
        logger.debug("the Agent channel did not open or did not stay open", exc_info=error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
