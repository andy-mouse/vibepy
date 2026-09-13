"""What one installed App can and cannot reach of another App and of its host.

The isolation invariant (`docs/architecture/packaging.md`) is kept by Studio's
construction; these are the tests that prove the construction holds, read from
inside a running App through Timer's `probe`.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from tests_support import AGENT, body, studio
from vibepy_core import Channel
from vibepy_core.app.composition import tool_runtime_for
from vibepy_core.tool import ToolRuntime
from vibepy_studio.entry import APP, STUDIO_APP, StudioConfig
from vibepy_studio.operating.internals import StudioDeps
from vibepy_studio.operating.internals.state import read_state
from vibepy_studio.operating.models import AppListing, RunningApp

WAIT = 30.0


@asynccontextmanager
async def window(root: Path, /) -> AsyncGenerator[tuple[ToolRuntime[StudioDeps], StudioDeps]]:
    """One Studio window, and the resource it opened over — so a test can reach the child.

    `ToolRuntime` keeps its dependencies private, rightly; a test that must kill
    a child by hand wraps the lifespan and keeps what it yielded.
    """
    held: list[StudioDeps] = []

    @asynccontextmanager
    async def capturing(config: StudioConfig) -> AsyncGenerator[StudioDeps]:
        async with APP.lifespan(config) as deps:
            held.append(deps)
            yield deps

    async with tool_runtime_for(
        STUDIO_APP, capturing, config={"root": str(root), "proxy_port": 8080}, channel=Channel.WEB
    ) as tools:
        yield tools, held[0]


async def _start(tools: ToolRuntime[StudioDeps], app_name: str, /) -> RunningApp:
    started = await tools.invoke(
        "start_app", {"app_name": app_name, "secrets": {}}, principal=AGENT
    )
    assert isinstance(started, RunningApp)
    assert started.diagnostic is None, started.diagnostic
    return started


async def _states(tools: ToolRuntime[StudioDeps]) -> dict[str, str]:
    listed = await tools.invoke("list_apps", {}, principal=AGENT)
    assert isinstance(listed, AppListing)
    return {row.app_name: row.state for row in listed.apps}


async def _gone(port: int, /) -> None:
    async with asyncio.timeout(WAIT):
        while True:
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", port)
            except OSError:
                return
            writer.transport.abort()
            await asyncio.sleep(0.05)


@pytest.mark.apps("vibepy-todo", "vibepy-timer")
@pytest.mark.integration
async def test_one_apps_death_leaves_the_other_and_studio_standing(
    tmp_path: Path, installed: Path
) -> None:
    async with window(installed) as (tools, deps):
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.db"), "db_key": "k"},
            },
            principal=AGENT,
        )
        await _start(tools, "vibepy-todo")
        await _start(tools, "vibepy-timer")
        ports = (await read_state(installed / "vibepy-studio")).ports

        todo = deps.processes.owned("vibepy-todo")
        assert todo is not None
        todo.kill()
        await todo.wait()

        answered = await asyncio.to_thread(body, f"http://127.0.0.1:{ports['vibepy-timer']}/home")
        assert "open for" in answered
        states = await _states(tools)
        assert states["vibepy-todo"] == "installed"
        assert states["vibepy-timer"] == "running"

        await _gone(ports["vibepy-todo"])
        await _start(tools, "vibepy-todo")
        assert (await _states(tools))["vibepy-todo"] == "running"


@pytest.mark.apps("vibepy-timer")
@pytest.mark.integration
async def test_an_app_sees_neither_studios_python_path_nor_its_directory(
    tmp_path: Path, installed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Planted on Studio, in the two places Python would otherwise look."""
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "planted_module.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(planted))
    monkeypatch.chdir(planted)

    async with studio(installed) as tools:
        await _start(tools, "vibepy-timer")
        port = (await read_state(installed / "vibepy-studio")).ports["vibepy-timer"]
        answered = await asyncio.to_thread(body, f"http://127.0.0.1:{port}/home")

    assert "importable=False" in answered
    assert f"path={planted}" not in answered
    assert f"cwd={installed / 'vibepy-timer'}" in answered


@pytest.mark.apps("vibepy-todo", "vibepy-timer")
@pytest.mark.integration
async def test_what_an_app_writes_beside_itself_is_its_own(tmp_path: Path, installed: Path) -> None:
    """Timer writes `probe.txt` where it stands; it lands in Timer's folder, not
    Studio's directory and not Todo's folder, and leaves with Timer."""
    timer = installed / "vibepy-timer"
    todo = installed / "vibepy-todo"

    async with studio(installed) as tools:
        await _start(tools, "vibepy-timer")
        port = (await read_state(installed / "vibepy-studio")).ports["vibepy-timer"]
        await asyncio.to_thread(body, f"http://127.0.0.1:{port}/home")
        await tools.invoke("stop_app", {"app_name": "vibepy-timer"}, principal=AGENT)

        assert (timer / "probe.txt").is_file()
        assert not (todo / "probe.txt").exists()
        assert not (Path.cwd() / "probe.txt").exists()

        await tools.invoke("remove_app", {"app_name": "vibepy-timer"}, principal=AGENT)

    assert not timer.exists()
