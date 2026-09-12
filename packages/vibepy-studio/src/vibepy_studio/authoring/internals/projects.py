"""Locating a source project and naming the environment it runs in.

uv owns the environment: `uv run --project <dir>` discovers the project, keeps
its lockfile and environment current, and runs the command inside it. The path
handed to it is absolute, because uv resolves other arguments against the
current directory rather than the project.

What touches the file system is `async` and wraps its own blocking work in
`asyncio.to_thread`, per `docs/architecture/runtime.md`: a Tool module awaits an
operation here, it never wraps one.
"""

import asyncio
import tomllib
from pathlib import Path, PurePath

from packaging.utils import canonicalize_name

PYPROJECT = "pyproject.toml"


async def locate(project: PurePath, /) -> PurePath | None:
    """Return the resolved project directory, or nothing when it holds no `pyproject.toml`."""
    return await asyncio.to_thread(_locate, project)


def _locate(project: PurePath, /) -> PurePath | None:
    resolved = Path(project).resolve()
    return resolved if (resolved / PYPROJECT).is_file() else None


async def declared_name(project: PurePath, /) -> str | None:
    """Return the canonical `[project].name`, or nothing when the file declares none."""
    return await asyncio.to_thread(_declared_name, project)


def _declared_name(project: PurePath, /) -> str | None:
    try:
        document = tomllib.loads((Path(project) / PYPROJECT).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    table = document.get("project")
    if not isinstance(table, dict):
        return None
    name = table.get("name")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return canonicalize_name(name) if isinstance(name, str) else None


def python(project: PurePath, /) -> list[str]:
    """Return the command prefix that runs Python inside this project's environment.

    Pure: it builds a command line and reads nothing, so it stays synchronous.
    """
    return ["uv", "run", "--project", str(project), "python"]
