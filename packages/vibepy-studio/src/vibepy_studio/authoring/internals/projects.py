"""Locating a source project and naming the environment it runs in.

uv owns the environment: `uv run --project <dir>` discovers the project, keeps
its lockfile and environment current, and runs the command inside it. The path
handed to it is absolute, because uv resolves other arguments against the
current directory rather than the project.
"""

import tomllib
from pathlib import Path

from packaging.utils import canonicalize_name

PYPROJECT = "pyproject.toml"


def locate(project: Path, /) -> Path | None:
    """Return the resolved project directory, or nothing when it holds no `pyproject.toml`."""
    resolved = project.resolve()
    return resolved if (resolved / PYPROJECT).is_file() else None


def declared_name(project: Path, /) -> str | None:
    """Return the canonical `[project].name`, or nothing when the file declares none."""
    try:
        document = tomllib.loads((project / PYPROJECT).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    table = document.get("project")
    if not isinstance(table, dict):
        return None
    name = table.get("name")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return canonicalize_name(name) if isinstance(name, str) else None


def python(project: Path, /) -> list[str]:
    """Return the command prefix that runs Python inside this project's environment."""
    return ["uv", "run", "--project", str(project), "python"]
