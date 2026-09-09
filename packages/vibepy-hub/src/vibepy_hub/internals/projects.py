"""What a registered folder offers, read from project files and nothing else.

Entry points are not core metadata and a build backend may add them, so a static
reading is a hint rather than a verdict: a folder with no visible declaration is
still offered, and installing it is what decides.
"""

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

APP_GROUP = "vibepy.apps"


@dataclass(frozen=True)
class Candidate:
    """One installable folder inside a registered source."""

    folder: Path
    name: str | None
    version: str | None
    declares_app: bool


class _Project(BaseModel):
    """The `[project]` fields a candidate is read from.

    `entry-points` is the key a project file uses, and the alias is what lets a
    field name it without a hyphen.
    """

    model_config = {"populate_by_name": True}

    name: str | None = None
    version: str | None = None
    entry_points: dict[str, dict[str, str]] = Field(default={}, alias="entry-points")


class _Document(BaseModel):
    """A project file, as much of it as a candidate needs."""

    project: _Project = _Project()


def _described(project: Path, /) -> _Project:
    """The `[project]` table of a project file, empty when it cannot be read."""
    try:
        document = tomllib.loads(project.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        logger.info("unreadable project file at %s", project)
        return _Project()
    try:
        return _Document.model_validate(document).project
    except ValidationError:
        logger.info("unexpected project table at %s", project)
        return _Project()


def candidates(source: Path, /) -> tuple[Candidate, ...]:
    """Every immediate subfolder of a source that carries a project file."""
    found: list[Candidate] = []
    for folder in sorted(path for path in source.iterdir() if path.is_dir()):
        project = folder / "pyproject.toml"
        if not project.is_file():
            continue
        described = _described(project)
        found.append(
            Candidate(
                folder=folder,
                name=described.name,
                version=described.version,
                declares_app=APP_GROUP in described.entry_points,
            )
        )
    return tuple(found)
