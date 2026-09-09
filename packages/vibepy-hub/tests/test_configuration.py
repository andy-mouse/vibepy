"""What the Hub holds for an installed App, and what it hands back."""

import stat
import sys
from pathlib import Path

import pytest

from tests_support import EXAMPLES, hub
from vibepy_hub.internals.state import STATE_FILE
from vibepy_hub.models import AppListing, HeldConfig, RunningApp

TOKEN = "s3cret-token-value"


async def test_values_are_held_for_an_installed_app(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        held = await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.db"), "db_key": "k"},
            },
        )
        listed = await tools.invoke("list_apps", {})

    assert isinstance(held, HeldConfig)
    assert held.diagnostic is None
    assert held.values == {"db_path": str(tmp_path / "todo.db")}
    assert held.secret_fields == ["db_key"]
    assert held.secrets_set == ["db_key"]
    assert isinstance(listed, AppListing)
    assert [row.configured for row in listed.apps if row.app_name == "vibepy-todo"] == [True]


async def test_an_app_missing_a_required_value_is_not_configured(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(listed, AppListing)
    assert [row.configured for row in listed.apps if row.app_name == "vibepy-todo"] == [False]


async def test_configuring_an_app_that_is_not_installed_is_a_diagnostic(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("configure_app", {"app_name": "vibepy-todo", "values": {}})

    assert isinstance(answered, HeldConfig)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_installed"


async def held_notes_secret(root: Path) -> HeldConfig:
    """Notes declares a secret, so configuring it exercises the secret path."""
    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-notes"})
        held = await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-notes",
                "values": {"api_base_url": "https://notes.internal", "api_token": TOKEN},
            },
        )
    assert isinstance(held, HeldConfig)
    return held


async def test_a_secret_is_held_so_a_restart_needs_no_one(tmp_path: Path) -> None:
    """A second window over the same root starts the App with nobody present.

    Todo declares `db_key` as a secret and its window refuses to open without
    one, so a start that supplies no secret and answers anyway is the whole
    claim: the value came from what the first window held.
    """
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        held = await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.json"), "db_key": "held"},
            },
        )
        assert isinstance(held, HeldConfig)
        assert held.secrets_set == ["db_key"]

    async with hub(root) as tools:
        started = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})

    assert isinstance(started, RunningApp)
    assert started.diagnostic is None
    assert started.url is not None


async def test_a_held_secret_is_never_handed_back(tmp_path: Path) -> None:
    """It is not handed back at all, so the output type is safe as the input type.

    A secret has no value in `values`, so the natural round trip -- read the
    form, edit one field, send it back -- cannot carry anything over the stored
    secret. What is held is said beside the values, not inside them.
    """
    root = tmp_path / "hub"

    held = await held_notes_secret(root)

    assert held.values == {"api_base_url": "https://notes.internal"}
    assert held.secret_fields == ["api_token"]
    assert held.secrets_set == ["api_token"]

    async with hub(root) as tools:
        again = await tools.invoke(
            "configure_app", {"app_name": "vibepy-notes", "values": held.values}
        )

    assert isinstance(again, HeldConfig)
    assert again.diagnostic is None
    assert again.secrets_set == ["api_token"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
async def test_what_is_held_is_readable_only_by_its_owner(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    await held_notes_secret(root)

    assert stat.S_IMODE((root / STATE_FILE).stat().st_mode) == 0o600
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
