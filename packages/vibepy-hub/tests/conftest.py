"""What the Hub's tests are given, and how often each of it is built.

pytest's guidance is that a resource which is expensive to build belongs to a
broader scope than the test that uses it, and that `tmp_path_factory` is where
a session-scoped one lives
(<https://docs.pytest.org/en/stable/how-to/fixtures.html>,
<https://docs.pytest.org/en/stable/how-to/tmp_path.html>). pip's own suite
applies that guidance to virtual environments: one is built a session and each
test is handed a copy of it, with nothing inside rewritten
(<https://github.com/pypa/pip/blob/main/tests/lib/venv.py>).

Here the expensive resource is a Hub root with the fixture Apps installed. It
is built once, by the same `install_app` a user calls, so what a test is handed
is what installing produces and not a second construction that could drift.
Each test receives a hardlinked copy: the same inodes, so nothing is assessed
or compiled a second time.

Two things in a root name the root's own path. `traefik.yml` is rewritten by
the Hub every time a window opens, so a copy is corrected the moment a test
opens it. Each environment's facts file records `purelib` as an absolute path,
and that one the copy rewrites. An environment's `pyvenv.cfg` records the base
interpreter, which is outside the root and does not move; the Hub reaches an
environment only through its interpreter and `-m`, so no installed script's
shebang is ever read.

A test whose subject *is* installing takes none of this. It drives
`install_app` like any caller, because that is the thing it is testing.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

from tests_support import build_wheelhouse, hub
from vibepy_hub.internals.installer import FACTS_FILE
from vibepy_hub.models import Installation

APPS = ("vibepy-notes", "vibepy-todo", "vibepy-timer")
"""Every fixture App, installed into the template in this order."""


@pytest.fixture(scope="session")
def wheelhouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One folder of wheels — the framework and the fixture Apps — built once a session.

    What a user registers is a folder of built wheels, so that is what the suite
    registers. Built here rather than committed, because a wheel of this checkout
    is a function of this checkout.
    """
    out = tmp_path_factory.mktemp("wheelhouse")
    build_wheelhouse(out)
    return out


@pytest.fixture(scope="session")
def template_root(tmp_path_factory: pytest.TempPathFactory, wheelhouse: Path) -> Path:
    """Build a Hub root with every fixture App installed, once for the session.

    Built through the Hub's own Tools rather than the installer's functions, so
    the root holds exactly what a user's install leaves: environments, facts,
    state with a port per App, and a route per App declaring Pages.
    """
    root = tmp_path_factory.mktemp("template") / "hub"

    async def build() -> None:
        async with hub(root) as tools:
            await tools.invoke("register_package_source", {"path": str(wheelhouse)})
            for app_name in APPS:
                installed = await tools.invoke("install_app", {"app_name": app_name})
                assert isinstance(installed, Installation)
                assert installed.diagnostic is None, installed.diagnostic

    asyncio.run(build())
    return root


@pytest.fixture
def installed(request: pytest.FixtureRequest, tmp_path: Path, template_root: Path) -> Path:
    """Give one test its own copy of the template root, holding the Apps it names.

    A test says which Apps it needs with `@pytest.mark.apps("vibepy-todo")`, the
    way pytest's guide has a fixture read a test's data from its marker. Only
    those Apps' environments are linked -- a copy has the same unit of cost as
    an install, entries created, and a test that needs one App must not pay for
    three. The Apps left out are then removed through `remove_app`, so the
    copy's state, ports and routes agree with its `envs/` directory. A test
    that names nothing gets nothing: a copy whose contents nobody chose is
    what the spec measured at 3.5s.

    Hardlinked rather than copied: the bytes are already on the disk and
    already assessed, and a second inode for each would be the cost the
    template exists to avoid. The only thing rewritten is the one path the Hub
    recorded inside the root, each environment's `purelib`.
    """
    # pytest leaves `FixtureRequest.node` unannotated; a function-scoped
    # fixture's node is the test, and once it is known to be one, pytest's own
    # annotations type the marker and its arguments.
    node = request.node  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(node, pytest.Item)
    marker = node.get_closest_marker("apps")
    assert marker is not None, "a test taking `installed` names its Apps with @pytest.mark.apps"
    named = frozenset[str](marker.args)
    unknown = named - frozenset(APPS)
    assert not unknown, f"not fixture Apps: {sorted(unknown)}"

    def leave_out(directory: str, names: list[str]) -> list[str]:
        if Path(directory) != template_root / "envs":
            return []
        return [name for name in names if name not in named]

    root = tmp_path / "hub"
    shutil.copytree(template_root, root, copy_function=os.link, ignore=leave_out)
    for recorded in root.glob(f"envs/*/{FACTS_FILE}"):
        facts = json.loads(recorded.read_text(encoding="utf-8"))
        facts["purelib"] = str(root / Path(facts["purelib"]).relative_to(template_root))
        # Unlinked first: every file here is a hardlink to the template's, and
        # writing through this name would write the template too.
        recorded.unlink()
        recorded.write_text(json.dumps(facts, indent=1), encoding="utf-8")

    async def prune() -> None:
        async with hub(root) as tools:
            for app_name in APPS:
                if app_name not in named:
                    await tools.invoke("remove_app", {"app_name": app_name})

    asyncio.run(prune())
    return root


pytest_plugins = ["nicegui.testing.user_plugin"]
"""The Hub has a Page from this milestone on, and its tests drive it as
`tests/test_nicegui_adapter.py` drives one: through the User fixture."""
