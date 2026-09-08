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
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, TypeAdapter, ValidationError

from vibepy_hub.models import AppFacts

logger = logging.getLogger(__name__)

FACTS_FILE = ".vibepy-facts.json"


class InstallFailed(Exception):
    """A step of installation failed. Carries which step and what it wrote."""

    def __init__(self, step: str, output: str) -> None:
        super().__init__(f"{step} failed: {output}")
        self.step = step
        self.output = output


def environment(root: Path, app_name: str, /) -> Path:
    """Where this Hub keeps one App's environment."""
    return root / "envs" / app_name


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
    """One entry of what `vibepy.describe` writes, as the Hub reads it."""

    app_id: str
    name: str
    version: str
    config_schema: dict[str, object] = {}
    pages: list[object] = []


_DESCRIBED = TypeAdapter(list[_Described])


async def describe(env: Path, /) -> tuple[AppFacts, ...]:
    """What the Apps in one environment declare, read in that environment."""
    written = await _run([str(interpreter(env)), "-m", "vibepy.describe"])
    try:
        described = _DESCRIBED.validate_json(written)
    except ValidationError as invalid:
        raise InstallFailed("vibepy.describe", str(invalid)) from invalid
    return tuple(
        AppFacts(
            app_id=entry.app_id,
            name=entry.name,
            version=entry.version,
            config_schema=entry.config_schema,
            has_pages=bool(entry.pages),
        )
        for entry in described
    )


def read_facts(env: Path, /) -> AppFacts | None:
    """What an installation learned when it was installed, or nothing."""
    path = env / FACTS_FILE
    if not path.is_file():
        return None
    try:
        return AppFacts.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError:
        logger.warning("ignoring unreadable facts at %s", path)
        return None


def write_facts(env: Path, facts: AppFacts, /) -> None:
    """Keep what an App declared beside the environment that holds it.

    The file lives inside the environment it describes and disappears with it, so
    removing an App leaves no record behind. It is not a second truth about what
    is installed: `discover_apps` still answers that.
    """
    (env / FACTS_FILE).write_text(facts.model_dump_json(indent=1), encoding="utf-8")


def installed_facts(root: Path, app_name: str, /) -> AppFacts | None:
    """What one installed App declared, or nothing when it is not installed."""
    env = environment(root, app_name)
    return read_facts(env) if env.is_dir() else None
