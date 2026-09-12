"""Creating an App's environment, and asking that environment what it holds.

`uv venv` with `uv pip install` gives an App an environment of its own for one
wheel, resolved against the wheelhouse it sits in.

Describing runs in that environment's interpreter, because reading a declaration
imports it and Studio must not import an App.
"""

import asyncio
import logging
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path, PurePath

from pydantic import ValidationError

from vibepy_core.app.package import AppRef, discover_apps
from vibepy_studio.internals.describing import DescribeFailed
from vibepy_studio.internals.describing import describe as describe_with
from vibepy_studio.internals.processes import NotRunnable, run
from vibepy_studio.operating.internals.files import is_directory
from vibepy_studio.operating.models import AppFacts

logger = logging.getLogger(__name__)

FACTS_FILE = ".vibepy-facts.json"


class InstallFailed(Exception):
    """A step of installation failed. Carries which step and what it wrote."""

    def __init__(self, step: str, output: str) -> None:
        """Record `step` and `output` for the message."""
        super().__init__(f"{step} failed: {output}")
        self.step = step
        self.output = output


class AppNameInvalid(Exception):
    """An App name does not address a directory inside this Studio's root."""

    def __init__(self, app_name: str) -> None:
        """Record `app_name` for the message."""
        super().__init__(f"App name {app_name!r} is not one path segment")
        self.app_name = app_name


ENV_DIR = "env"
"""The virtual environment inside an App's folder; update remakes this alone."""


def app_folder(root: PurePath, app_name: str, /) -> PurePath:
    """Where Studio keeps one App: its environment, and whatever it writes beside it.

    The name is refused unless the join names a direct child of the root. A Tool
    input is already constrained to one segment; this is the guarantee, because
    a Tool input is not the only caller and the result reaches `shutil.rmtree`.

    The comparison is lexical rather than resolved: `normpath` collapses `..`
    and discards the root for an absolute name on the platform where those mean
    traversal. What it deliberately does not do is follow a symlink under the
    root, which is not this gate's subject -- the subject is the name -- and
    which `shutil.rmtree` refuses of its own accord.

    Naming the child is required as well as reaching it, so a name that
    normalizes onto a sibling is refused rather than aliased: `x/../y` and `y`
    would otherwise be two names for one folder. That holds of names, not of
    the file system: a symlink inside the root still aliases.
    """
    candidate = PurePath(os.path.normpath(root / app_name))
    if candidate.parent != root or candidate.name != app_name:
        raise AppNameInvalid(app_name)
    return candidate


def environment(root: PurePath, app_name: str, /) -> PurePath:
    """Where one App's virtual environment lives, inside its folder."""
    return app_folder(root, app_name) / ENV_DIR


def interpreter(env: PurePath, /) -> PurePath:
    """Return the Python of an environment, on either platform."""
    return env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


async def purelib(env: PurePath, /) -> PurePath:
    """Where an environment keeps its distribution metadata.

    Asked of that environment rather than derived from this one. A virtual
    environment takes its version from the base Python that created it, so a
    path built from Studio's own version is a guess that fails as soon as the
    two differ. `sysconfig.get_path("purelib")` is the interpreter's own answer.
    """
    written = await _run(
        [str(interpreter(env)), "-c", "import sysconfig;print(sysconfig.get_path('purelib'))"]
    )
    return PurePath(written.strip())


async def _run(command: Sequence[str], /) -> str:
    """One command, its output, and a failure that says which step it was."""
    try:
        completed = await run(command)
    except NotRunnable as absent:
        raise InstallFailed(command[0], str(absent)) from absent
    written = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise InstallFailed(" ".join(command[:2]), written.strip())
    return completed.stdout


async def install(*, wheel: PurePath, source: PurePath, env: PurePath) -> None:
    """Create an environment of its own for one App and install one wheel there.

    `--find-links` names the wheelhouse the wheel came from, so its dependencies --
    the framework first -- resolve from the same folder. That is what a wheelhouse
    is for, and what lets an in-house operating role install with no index reachable.

    The link mode is stated rather than defaulted. uv links from its cache with
    `clone` on macOS and Linux and `hardlink` on Windows
    (<https://docs.astral.sh/uv/reference/settings/#link-mode>), and a clone
    gives every file a new inode. macOS assesses a `.so` it has not seen by
    inode, so an environment of cloned files is scanned in full the first time
    the App is imported -- which the operating role does immediately, to describe it. Every
    installed App pays that, and it is seconds
    (<https://github.com/astral-sh/uv/issues/18577>). Hardlinks reuse the
    cache's inodes, so the scan happens once for a dependency rather than once
    per App that holds it. The operating role never writes inside an environment it
    installed, which is what makes sharing an inode with the cache safe.
    """
    await asyncio.to_thread(Path(env).parent.mkdir, parents=True, exist_ok=True)
    await _run(["uv", "venv", str(env)])
    await _run(
        [
            "uv",
            "pip",
            "install",
            "--link-mode",
            "hardlink",
            "--python",
            str(interpreter(env)),
            "--find-links",
            str(source),
            str(wheel),
        ]
    )


async def describe(env: PurePath, /, *, cwd: PurePath | None = None) -> tuple[AppFacts, ...]:
    """Return what the Apps in one environment declare, read in that environment, run in `cwd`."""
    try:
        described = await describe_with([str(interpreter(env))], cwd=cwd)
    except (NotRunnable, DescribeFailed) as failure:
        raise InstallFailed("vibepy_core.describe", str(failure)) from failure
    return tuple(AppFacts(described=entry) for entry in described)


async def read_facts(env: PurePath, /) -> AppFacts | None:
    """Return what an installation learned when it was installed, or nothing."""
    return await asyncio.to_thread(_read_facts, env)


def _read_facts(env: PurePath, /) -> AppFacts | None:
    path = Path(env) / FACTS_FILE
    if not path.is_file():
        return None
    try:
        return AppFacts.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError:
        logger.warning("ignoring unreadable facts at %s", path)
        return None


async def write_facts(env: PurePath, facts: AppFacts, /) -> None:
    """Keep what an App declared beside the environment that holds it.

    The file lives inside the environment it describes and disappears with it, so
    removing an App leaves no record behind. It is not a second truth about what
    is installed: `discover_apps` still answers that.
    """
    await asyncio.to_thread(_write_facts, env, facts)


def _write_facts(env: PurePath, facts: AppFacts, /) -> None:
    (Path(env) / FACTS_FILE).write_text(facts.model_dump_json(indent=1), encoding="utf-8")


async def installed_facts(root: PurePath, app_name: str, /) -> AppFacts | None:
    """Return what one installed App declared, or nothing when it is not installed."""
    env = environment(root, app_name)
    return await read_facts(env) if await asyncio.to_thread(is_directory, env) else None


async def remove_environment(env: PurePath, /) -> None:
    """Delete one App's environment, if it is there."""
    await asyncio.to_thread(_remove_tree, env)


async def remove_app_folder(folder: PurePath, /) -> None:
    """Delete one App's folder — its environment and what it wrote beside it — if it is there."""
    await asyncio.to_thread(_remove_tree, folder)


def _remove_tree(path: PurePath, /) -> None:
    shutil.rmtree(Path(path), ignore_errors=True)


async def declarations(purelib: PurePath, /) -> tuple[AppRef, ...]:
    """Return what one environment declares, read from its metadata.

    `discover_apps` scans a `site-packages` directory, so it blocks for as long
    as that directory takes to read. A Tool handler asks this instead.
    """
    return await asyncio.to_thread(_declarations, purelib)


def _declarations(purelib: PurePath, /) -> tuple[AppRef, ...]:
    return discover_apps(path=[Path(purelib)])


async def environments(root: PurePath, /) -> tuple[PurePath, ...]:
    """Every environment this operating role created, in a stable order."""
    return await asyncio.to_thread(_environments, root)


def _environments(root: PurePath, /) -> tuple[PurePath, ...]:
    base = Path(root)
    if not base.is_dir():
        return ()
    return tuple(
        PurePath(folder / ENV_DIR)
        for folder in sorted(base.iterdir())
        if (folder / ENV_DIR).is_dir()
    )
