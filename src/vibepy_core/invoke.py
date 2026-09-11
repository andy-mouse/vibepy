"""Invoke one Tool of one App, in that App's own environment.

`vibepy_core.describe` reads a declaration and `vibepy_core.serve` runs its Web
channel; this opens the channel-neutral invocation window once, calls one Tool
through ToolRuntime, and closes the window. It is how a host that must not import
an App verifies that a Tool behaves. Its configuration is the environment's
(`docs/architecture/packaging.md`, Configuration); standard input carries one
JSON object of `input`, the Tool's own per-call data.
"""

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, ValidationError

from vibepy_core.app.composition import tool_runtime_for
from vibepy_core.app.config import AppConfig
from vibepy_core.app.entrypoint import AppEntrypoint
from vibepy_core.app.package import load_app
from vibepy_core.errors import (
    AppEntrypointInvalidError,
    AppEntrypointUnloadableError,
    AppNotDeclaredError,
    InvokeRequestInvalidError,
    report,
)

logger = logging.getLogger(__name__)


class _Request(BaseModel):
    """What standard input carries: one JSON object of the Tool's `input`.

    Any other key is refused rather than ignored, so a request written for the
    configuration channel this command no longer has fails and says so.
    """

    model_config = ConfigDict(extra="forbid")

    input: dict[str, object] = {}


async def _invoke(
    entrypoint: AppEntrypoint[object, AppConfig], tool_name: str, request: _Request, /
) -> BaseModel:
    """Open the window, invoke once, close the window."""
    async with tool_runtime_for(entrypoint.definition, entrypoint.lifespan, config={}) as runtime:
        return await runtime.invoke(tool_name, request.input)


def main(argv: Sequence[str], /) -> int:
    """Read a request from standard input and invoke one Tool.

    Standard input carries one JSON object of `input`; configuration is the
    environment's, `VIBEPY_<FIELD>` per declared field.

    Exits 0 with the Tool's output as one JSON object on standard output. Exits 1
    with one report line on standard error for any failure: a request that is
    not one JSON object of `input`, an App this environment does not declare or
    cannot load,
    configuration the window refuses, a Tool the App does not declare, input or
    output its models reject, and anything the lifespan or handler raised,
    which is reported as `app.unhandled`.
    """
    parser = argparse.ArgumentParser(prog="vibepy_core.invoke")
    parser.add_argument("app_name")
    parser.add_argument("tool_name")
    parsed = parser.parse_args(argv)
    try:
        request = _Request.model_validate_json(sys.stdin.read() or "{}")
    except ValidationError as invalid:
        report(InvokeRequestInvalidError())
        logger.debug("the request on standard input was unreadable", exc_info=invalid)
        return 1
    try:
        entrypoint = load_app(str(parsed.app_name))
    except (AppNotDeclaredError, AppEntrypointUnloadableError, AppEntrypointInvalidError) as error:
        report(error)
        return 1
    try:
        result = asyncio.run(_invoke(entrypoint, str(parsed.tool_name), request))
    except Exception as error:
        # The window reports its own failure (ADR-030): any exception the
        # lifespan or handler raises is normalized and written the same way.
        report(error)
        logger.debug("the invocation failed", exc_info=error)
        return 1
    sys.stdout.write(json.dumps(result.model_dump(mode="json")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
