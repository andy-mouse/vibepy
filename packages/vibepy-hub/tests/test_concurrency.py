"""Two Hub Tool calls overlap, because no handler holds the loop.

The assertion is an ordering and not a duration: `docs/architecture/runtime.md`
requires overlap to be proven by what happened rather than by how long it took.
Installing runs `uv` twice and reads an environment; listing reads directories.
While the Hub's filesystem work sat on the loop, the light call could not answer
first.
"""

import asyncio
from pathlib import Path

from tests_support import EXAMPLES, hub
from vibepy_hub.models import AppListing


async def test_a_light_hub_call_answers_while_a_slow_one_is_still_running(
    tmp_path: Path,
) -> None:
    async with hub(tmp_path / "hub") as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        installing = asyncio.create_task(tools.invoke("install_app", {"app_name": "vibepy-todo"}))
        await asyncio.sleep(0)

        listed = await tools.invoke("list_apps", {})

        assert isinstance(listed, AppListing)
        assert not installing.done()
        await installing
