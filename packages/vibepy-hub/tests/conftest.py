"""What the Hub's tests are given, and how often each of it is built.

pytest's guidance is that a resource which is expensive to build belongs to a
broader scope than the test that uses it, and that `tmp_path_factory` is where
a session-scoped one lives
(<https://docs.pytest.org/en/stable/how-to/fixtures.html>,
<https://docs.pytest.org/en/stable/how-to/tmp_path.html>).

An App's environment is exactly that resource. Building one runs `uv` and then
imports everything the App depends on, in a directory nothing has imported
before. Every test built its own, which is the shape that guidance names, and
the suite paid for it once per test rather than once.

It is built once here instead. A test that needs an App already installed is
given a fresh Hub root with a hardlinked copy of that environment: the same
inodes, so nothing is assessed or compiled a second time, and the copy costs
milliseconds. An environment is relocatable -- `pyvenv.cfg` records the base
Python and not its own location, and the Hub reaches an environment only
through `env/bin/python` -- so the only thing the copy rewrites is the one path
the Hub itself recorded.

A test whose subject *is* installing takes none of this. It drives
`install_app` like any caller, because that is the thing it is testing.
"""

import asyncio
import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests_support import EXAMPLES, FIXTURES
from vibepy_hub.internals.installer import (
    FACTS_FILE,
    describe,
    install,
    purelib,
    write_facts,
)

PLAIN = "vibepy-plain"
"""The smallest installable App. `fixtures/plain-app` says why it exists."""

NOTES = "vibepy-notes"
"""The example that declares a secret and no Pages."""


def _build(folder: Path, env: Path, /) -> None:
    """Install one distribution into one environment, as the Hub would.

    The Hub's own installer, so what a test is handed is what installing
    produces rather than a second construction of it that could drift.
    """

    async def built() -> None:
        await install(folder=folder, env=env)
        described = await describe(env)
        metadata = await purelib(env)
        await write_facts(env, described[0].model_copy(update={"purelib": metadata}))

    asyncio.run(built())


@pytest.fixture(scope="session")
def plain_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The minimal App's environment, built once for the whole session."""
    env = tmp_path_factory.mktemp("templates") / PLAIN
    _build(FIXTURES / "plain-app", env)
    return env


def _place(template: Path, root: Path, app_name: str, /) -> None:
    """Put a built environment where a Hub with this root will find it.

    Hardlinked rather than copied: the bytes are already on the disk and
    already assessed, and a second inode for each would be the cost this
    fixture exists to avoid.
    """
    env = root / "envs" / app_name
    env.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, env, copy_function=os.link)
    recorded = env / FACTS_FILE
    facts = json.loads(recorded.read_text(encoding="utf-8"))
    # The Hub records where the environment keeps its distribution metadata,
    # and this copy is somewhere else. Same segment, new root.
    facts["purelib"] = str(env / Path(facts["purelib"]).relative_to(template))
    # Unlinked first, because every file here is a hardlink to the template's:
    # writing through this name would write the template too, and the next
    # test would be handed an environment describing the previous one.
    recorded.unlink()
    recorded.write_text(json.dumps(facts, indent=1), encoding="utf-8")


@pytest.fixture
def plain_installed(tmp_path: Path, plain_template: Path) -> Iterator[Path]:
    """A Hub root that already holds the minimal App, and nothing else."""
    root = tmp_path / "hub"
    _place(plain_template, root, PLAIN)
    yield root


@pytest.fixture(scope="session")
def notes_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """`examples/notes` declares a secret and no Pages, built once."""
    env = tmp_path_factory.mktemp("templates") / NOTES
    _build(EXAMPLES / "notes", env)
    return env


@pytest.fixture
def notes_installed(tmp_path: Path, notes_template: Path) -> Iterator[Path]:
    """A Hub root that already holds an App declaring a secret."""
    root = tmp_path / "hub"
    _place(notes_template, root, NOTES)
    yield root


@pytest.fixture
def two_installed(tmp_path: Path, plain_template: Path, notes_template: Path) -> Iterator[Path]:
    """A Hub root holding two Apps, for what only happens when there are two."""
    root = tmp_path / "hub"
    _place(plain_template, root, PLAIN)
    _place(notes_template, root, NOTES)
    yield root
