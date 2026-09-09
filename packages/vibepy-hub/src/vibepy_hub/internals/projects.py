"""What a registered folder offers, read from project files and nothing else.

Entry points are not core metadata and a build backend may add them, so a static
reading is a hint rather than a verdict: a folder with no visible declaration is
still offered, and installing it is what decides.
"""

import asyncio
import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

from packaging.utils import canonicalize_name
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

APP_GROUP = "vibepy.apps"


@dataclass(frozen=True)
class Candidate:
    """One installable folder inside a registered source.

    `name` is the canonical distribution name, which is what a Hub Tool
    addresses this App by. See
    `docs/decisions/ADR-028-an-app-is-addressed-by-its-distribution-name.md`.
    """

    folder: Path
    name: str
    version: str | None
    declares_app: bool


class _Project(BaseModel):
    """The `[project]` fields a candidate is read from.

    `name` is required and is one of the keys the specification says must be
    static, so a table without one is not a project table. `version` may be
    dynamic, so it stays optional. `entry-points` is the key a project file
    uses, and the alias is what lets a field name it without a hyphen.
    """

    model_config = {"populate_by_name": True}

    name: str
    version: str | None = None
    entry_points: dict[str, dict[str, str]] = Field(default={}, alias="entry-points")


class _Document(BaseModel):
    """A project file, as much of it as a candidate needs."""

    project: _Project


def _described(project: Path, /) -> _Project | None:
    """The `[project]` table of a project file, or nothing when there is none."""
    try:
        document = tomllib.loads(project.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        logger.info("unreadable project file at %s", project)
        return None
    try:
        return _Document.model_validate(document).project
    except ValidationError:
        logger.info("no usable project table at %s", project)
        return None


async def candidates(source: Path, /) -> tuple[Candidate, ...]:
    """Every immediate subfolder of a source that carries a usable project file."""
    return await asyncio.to_thread(_candidates, source)


def _candidates(source: Path, /) -> tuple[Candidate, ...]:
    try:
        folders = sorted(path for path in source.iterdir() if path.is_dir())
    except OSError:
        logger.info("unreadable source at %s", source)
        return ()
    found: list[Candidate] = []
    for folder in folders:
        project = folder / "pyproject.toml"
        if not project.is_file():
            continue
        described = _described(project)
        if described is None:
            continue
        found.append(
            Candidate(
                folder=folder,
                name=str(canonicalize_name(described.name)),
                version=described.version,
                declares_app=APP_GROUP in described.entry_points,
            )
        )
    return tuple(found)


async def readable(source: Path, /) -> bool:
    """Whether a registered source is still there to be read."""
    return await asyncio.to_thread(Path.is_dir, source)
