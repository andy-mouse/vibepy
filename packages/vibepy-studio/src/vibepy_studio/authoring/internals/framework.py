"""What the framework this Studio runs on says about itself.

`importlib.metadata.version` reads a distribution's metadata from disk, so it is
behind an `asyncio.to_thread` here rather than at a handler's call site, per
`docs/architecture/runtime.md`.
"""

import asyncio
from importlib.metadata import version

FRAMEWORK = "vibepy-core"


async def framework_version() -> str:
    """Return the version of the framework distribution this Studio is installed against."""
    return await asyncio.to_thread(version, FRAMEWORK)
