"""A secret is stored, protected by permissions, and never handed back."""

import stat
import sys
from pathlib import Path

import pytest

from tests_support import SAMPLES, hub
from vibepy_hub.models import AppListing, HeldConfig
from vibepy_hub.state import STATE_FILE

TOKEN = "s3cret-token-value"


async def configured_notes(root: Path, samples: Path) -> HeldConfig:
    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(samples)})
        await tools.invoke("install_app", {"app_name": "notes"})
        held = await tools.invoke(
            "configure_app",
            {
                "app_name": "notes",
                "values": {"api_base_url": "https://notes.internal", "api_token": TOKEN},
            },
        )
    assert isinstance(held, HeldConfig)
    return held


async def test_a_secret_is_stored_so_a_restart_needs_no_one(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    await configured_notes(root, SAMPLES)

    assert TOKEN in (root / STATE_FILE).read_text(encoding="utf-8")


async def test_a_stored_secret_is_not_handed_back(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    held = await configured_notes(root, SAMPLES)

    assert held.values["api_token"] == "set"
    assert held.values["api_base_url"] == "https://notes.internal"
    assert held.secret_fields == ["api_token"]

    async with hub(root) as tools:
        listed = await tools.invoke("list_apps", {})
    assert isinstance(listed, AppListing)
    assert [row.configured for row in listed.apps if row.app_name == "notes"] == [True]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
async def test_the_state_file_is_readable_only_by_its_owner(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    await configured_notes(root, SAMPLES)

    mode = stat.S_IMODE((root / STATE_FILE).stat().st_mode)
    assert mode == 0o600
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
