"""What a registered wheelhouse offers, read from file names and one metadata file.

A wheel is a finished build. Its name and version are in its file name by
specification, and its entry points are in `entry_points.txt` inside it, so both
are read without installing or importing anything — and, unlike a project file,
neither is a hint.
"""

import asyncio
import configparser
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePath

from packaging.utils import InvalidWheelFilename, parse_wheel_filename
from packaging.version import Version

from vibepy_core.app.group import APP_GROUP
from vibepy_studio.operating.internals.files import is_directory

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class Candidate:
    """One installable wheel inside a registered source.

    `name` is the canonical distribution name, which is what an operating Tool addresses
    this App by.
    """

    wheel: PurePath
    name: str
    version: str
    declares_app: bool


async def candidates(source: PurePath, /) -> tuple[Candidate, ...]:
    """Every distribution the source offers, one wheel each: the highest version."""
    return await asyncio.to_thread(_candidates, source)


def _candidates(source: PurePath, /) -> tuple[Candidate, ...]:
    try:
        wheels = sorted(
            path for path in Path(source).iterdir() if path.is_file() and path.suffix == ".whl"
        )
    except OSError:
        logger.info("unreadable source at %s", source)
        return ()
    best: dict[str, tuple[Version, Path]] = {}
    for wheel in wheels:
        try:
            name, version, _build, _tags = parse_wheel_filename(wheel.name)
        except InvalidWheelFilename:
            logger.info("not a wheel file name: %s", wheel)
            continue
        held = best.get(name)
        if held is None or version > held[0]:
            best[name] = (version, wheel)
    return tuple(
        Candidate(
            wheel=PurePath(wheel),
            name=name,
            version=str(version),
            declares_app=_declares_app(wheel),
        )
        for name, (version, wheel) in sorted(best.items())
    )


def _declares_app(wheel: Path, /) -> bool:
    """Whether the wheel's `entry_points.txt` carries the `vibepy.apps` group."""
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = [n for n in archive.namelist() if n.endswith(".dist-info/entry_points.txt")]
            if not names:
                return False
            text = archive.read(names[0]).decode("utf-8", errors="replace")
    except (OSError, zipfile.BadZipFile):
        logger.info("unreadable wheel at %s", wheel)
        return False
    parser = configparser.ConfigParser()
    parser.read_string(text)
    return parser.has_section(APP_GROUP)


async def readable(source: PurePath, /) -> bool:
    """Whether a registered source is still there to be read."""
    return await asyncio.to_thread(is_directory, source)
