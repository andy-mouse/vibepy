"""Creating an App's environment, and asking that environment what it holds.

`docs/architecture/packaging.md` states the contract that an App is installed
into an environment of its own, and leaves the mechanism to the Hub. `uv venv`
with `uv pip install` satisfies it for a local folder while leaving the
environment's path to the Hub.

Describing runs in that environment's interpreter, because reading a declaration
imports it and the Hub must not import an App.
"""

import asyncio
import logging
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, TypeAdapter, ValidationError

from vibepy_core.app.package import AppRef, discover_apps
from vibepy_hub.models import AppFacts

logger = logging.getLogger(__name__)

FACTS_FILE = ".vibepy-facts.json"


class InstallFailed(Exception):
    """A step of installation failed. Carries which step and what it wrote."""

    def __init__(self, step: str, output: str) -> None:
        super().__init__(f"{step} failed: {output}")
        self.step = step
        self.output = output


class AppNameInvalid(Exception):
    """An App name does not address a directory inside this Hub's environments."""

    def __init__(self, app_name: str) -> None:
        super().__init__(f"App name {app_name!r} is not one path segment")
        self.app_name = app_name


def environment(root: Path, app_name: str, /) -> Path:
    """Where this Hub keeps one App's environment.

    The name is refused unless the join names a direct child of the environments
    directory. A Tool input is already constrained to one segment; this is the
    guarantee, because a Tool input is not the only caller and the result reaches
    `shutil.rmtree`.

    The comparison is lexical rather than resolved: `normpath` collapses `..`
    and discards the root for an absolute name on the platform where those mean
    traversal. What it deliberately does not do is follow a symlink under
    `envs`, which is not this gate's subject -- the subject is the name -- and
    which `shutil.rmtree` refuses of its own accord.

    Naming the child is required as well as reaching it, so a name that
    normalizes onto a sibling is refused rather than aliased: `x/../y` and `y`
    would otherwise be two names for one environment. That holds of names, not
    of the file system: a symlink inside `envs` still aliases.
    """
    envs = root / "envs"
    candidate = Path(os.path.normpath(envs / app_name))
    if candidate.parent != envs or candidate.name != app_name:
        raise AppNameInvalid(app_name)
    return candidate


def interpreter(env: Path, /) -> Path:
    """The Python of an environment, on either platform."""
    return env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


async def purelib(env: Path, /) -> Path:
    """Where an environment keeps its distribution metadata.

    Asked of that environment rather than derived from this one. A virtual
    environment takes its version from the base Python that created it, so a
    path built from the Hub's own version is a guess that fails as soon as the
    two differ. `sysconfig.get_path("purelib")` is the interpreter's own answer.
    """
    written = await _run(
        [str(interpreter(env)), "-c", "import sysconfig;print(sysconfig.get_path('purelib'))"]
    )
    return Path(written.strip())


def _is_runnable(program: str, /) -> bool:
    """Whether a program is on PATH or is itself a file, as an env's Python is."""
    return shutil.which(program) is not None or Path(program).is_file()


async def _run(command: Sequence[str], /) -> str:
    """One command, its output, and a failure that says which step it was."""
    if not await asyncio.to_thread(_is_runnable, command[0]):
        raise InstallFailed(command[0], f"{command[0]} is not available")
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    output, _ = await process.communicate()
    written = output.decode(errors="replace")
    if process.returncode != 0:
        raise InstallFailed(" ".join(command[:2]), written.strip())
    return written


async def install(*, folder: Path, env: Path) -> None:
    """Create an environment of its own for one App and install it there."""
    await _run(["uv", "venv", str(env)])
    await _run(["uv", "pip", "install", "--python", str(interpreter(env)), str(folder)])


class _Described(BaseModel):
    """One entry of what `vibepy_core.describe` writes, as the Hub reads it."""

    app_name: str
    distribution: str
    app_id: str
    name: str
    version: str
    config_schema: dict[str, object] = {}
    pages: list[object] = []


_DESCRIBED = TypeAdapter(list[_Described])


async def describe(env: Path, /) -> tuple[AppFacts, ...]:
    """What the Apps in one environment declare, read in that environment."""
    written = await _run([str(interpreter(env)), "-m", "vibepy_core.describe"])
    try:
        described = _DESCRIBED.validate_json(written)
    except ValidationError as invalid:
        raise InstallFailed("vibepy_core.describe", str(invalid)) from invalid
    return tuple(
        AppFacts(
            app_id=entry.app_id,
            name=entry.name,
            version=entry.version,
            config_schema=entry.config_schema,
            has_pages=bool(entry.pages),
            declared_name=entry.app_name,
            distribution=entry.distribution,
        )
        for entry in described
    )


async def read_facts(env: Path, /) -> AppFacts | None:
    """What an installation learned when it was installed, or nothing."""
    return await asyncio.to_thread(_read_facts, env)


def _read_facts(env: Path, /) -> AppFacts | None:
    path = env / FACTS_FILE
    if not path.is_file():
        return None
    try:
        return AppFacts.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError:
        logger.warning("ignoring unreadable facts at %s", path)
        return None


async def write_facts(env: Path, facts: AppFacts, /) -> None:
    """Keep what an App declared beside the environment that holds it.

    The file lives inside the environment it describes and disappears with it, so
    removing an App leaves no record behind. It is not a second truth about what
    is installed: `discover_apps` still answers that.
    """
    await asyncio.to_thread(_write_facts, env, facts)


def _write_facts(env: Path, facts: AppFacts, /) -> None:
    (env / FACTS_FILE).write_text(facts.model_dump_json(indent=1), encoding="utf-8")


async def installed_facts(root: Path, app_name: str, /) -> AppFacts | None:
    """What one installed App declared, or nothing when it is not installed."""
    env = environment(root, app_name)
    return await read_facts(env) if await asyncio.to_thread(Path.is_dir, env) else None


async def remove_environment(env: Path, /) -> None:
    """Delete one App's environment, if it is there."""
    await asyncio.to_thread(shutil.rmtree, env, ignore_errors=True)


async def declarations(purelib: Path, /) -> tuple[AppRef, ...]:
    """What one environment declares, read from its metadata.

    `discover_apps` scans a `site-packages` directory, so it blocks for as long
    as that directory takes to read. A Tool handler asks this instead.
    """
    return await asyncio.to_thread(discover_apps, path=[purelib])


async def environments(root: Path, /) -> tuple[Path, ...]:
    """Every environment this Hub created, in a stable order."""
    return await asyncio.to_thread(_environments, root)


def _environments(root: Path, /) -> tuple[Path, ...]:
    envs = root / "envs"
    if not envs.is_dir():
        return ()
    return tuple(sorted(path for path in envs.iterdir() if path.is_dir()))
