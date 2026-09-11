"""What the framework says about itself, read by import and handed to an agent."""

from importlib.metadata import version
from pathlib import Path

from tests_support import studio
from vibepy_core import ERROR_CATALOG
from vibepy_studio.authoring.models import FrameworkDescription


async def test_the_framework_describes_its_version_group_extras_and_catalogue(
    tmp_path: Path,
) -> None:
    async with studio(tmp_path / "studio") as tools:
        described = await tools.invoke("inspect_framework", {})
    assert isinstance(described, FrameworkDescription)
    assert described.framework_version == version("vibepy-core")
    assert described.entry_point_group == "vibepy.apps"
    assert described.channel_extras == ["web", "agent"]
    assert {row.code: row.category for row in described.error_catalog} == dict(ERROR_CATALOG)
