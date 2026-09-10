"""The Hub's state survives a second caller and an interrupted write."""

import asyncio
from pathlib import Path

import pytest

from tests_support import EXAMPLES, hub
from vibepy_hub.internals.state import STATE_FILE, HubState, read_state, write_state
from vibepy_hub.models import HeldConfig


async def test_two_overlapping_configurations_both_survive(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke("install_app", {"app_name": "vibepy-notes"})

        first, second = await asyncio.gather(
            tools.invoke(
                "configure_app",
                {"app_name": "vibepy-todo", "values": {"db_path": str(tmp_path / "t.db")}},
            ),
            tools.invoke(
                "configure_app",
                {"app_name": "vibepy-notes", "values": {"api_base_url": "https://n"}},
            ),
        )
        assert isinstance(first, HeldConfig)
        assert isinstance(second, HeldConfig)

    held = (await read_state(root)).config
    assert set(held) == {"vibepy-todo", "vibepy-notes"}


async def test_a_write_that_fails_leaves_the_previous_state_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A departure from testing public contracts only, named in the spec: no
    Tool can interrupt a write halfway."""
    root = tmp_path / "hub"
    await write_state(root, HubState(sources=[tmp_path / "kept"], config={}))

    def refuse(src: object, dst: object) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr("vibepy_hub.internals.files.os.replace", refuse)
    with pytest.raises(OSError):
        await write_state(root, HubState(sources=[], config={"lost": {}}))

    assert (await read_state(root)).sources == [tmp_path / "kept"]
    assert [path.name for path in root.iterdir()] == [STATE_FILE]
