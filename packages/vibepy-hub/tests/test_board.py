"""The board shows Hub Core's state and acts on it through the Hub's Tools."""

from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from tests_support import hub, write_wheel
from vibepy_core.adapters.nicegui import register_pages
from vibepy_core.app import page_runtime_for
from vibepy_hub.entry import APP, HUB_APP
from vibepy_hub.models import ConfigDescription


def hub_pages(root: Path):
    return page_runtime_for(HUB_APP, APP.lifespan, config={"root": str(root), "proxy_port": 8080})


async def test_the_board_shows_what_list_apps_answers(user: User, tmp_path: Path) -> None:
    source = tmp_path / "wheels"
    write_wheel(source, name="demo-app", version="1.2.3", declares=True)

    async with hub_pages(tmp_path / "hub") as pages:
        register_pages(HUB_APP, pages)
        await user.open("/")
        await user.should_see("No folder registered")
        await user.should_see("No package folder selected")

        user.find(marker="package-folder").type(str(source))
        user.find("Register").click()
        await user.should_see("demo-app")
        await user.should_see("v1.2.3")
        await user.should_see("Install")


@pytest.mark.apps("vibepy-notes")
@pytest.mark.integration
async def test_configuring_an_installed_app_names_what_it_lacks(
    user: User, installed: Path
) -> None:
    async with hub_pages(installed) as pages:
        register_pages(HUB_APP, pages)
        await user.open("/")
        await user.should_see("Notes")
        user.find("Configure").click()
        await user.should_see("api_base_url")
        await user.should_see("api_token")

        user.find("Save").click()
        await user.should_see("Missing required fields: api_base_url, api_token")


@pytest.mark.apps("vibepy-notes")
@pytest.mark.integration
async def test_a_failed_save_keeps_what_was_typed(user: User, installed: Path) -> None:
    async with hub_pages(installed) as pages:
        register_pages(HUB_APP, pages)
        await user.open("/")
        user.find("Configure").click()
        await user.should_see("api_base_url")
        user.find(marker="field-vibepy-notes-api_base_url").type("https://notes.internal")
        user.find("Save").click()
        await user.should_see("Missing required field: api_token")

        entry = user.find(kind=ui.input, marker="field-vibepy-notes-api_base_url").elements.pop()
        assert entry.value == "https://notes.internal"


@pytest.mark.apps("vibepy-notes")
@pytest.mark.integration
async def test_a_saved_configuration_reaches_the_hub(user: User, installed: Path) -> None:
    async with hub_pages(installed) as pages:
        register_pages(HUB_APP, pages)
        await user.open("/")
        user.find("Configure").click()
        await user.should_see("api_base_url")
        user.find(marker="field-vibepy-notes-api_base_url").type("https://notes.internal")
        user.find(marker="field-vibepy-notes-api_token").type("k")
        user.find("Save").click()
        await user.should_see("Notes configured")

    async with hub(installed) as tools:
        described = await tools.invoke("describe_config", {"app_name": "vibepy-notes"})

    assert isinstance(described, ConfigDescription)
    assert described.values == {"api_base_url": "https://notes.internal"}
    assert described.secrets_set == ["api_token"]


@pytest.mark.integration
async def test_install_invokes_the_tool_and_shows_its_answer(user: User, tmp_path: Path) -> None:
    # A wheel that declares an App and holds no code: `install_app` runs for
    # real and answers a diagnostic, which is what the board has to show. What
    # a real distribution installs is `test_installation.py`'s subject, and
    # building an environment here would buy this test nothing.
    source = tmp_path / "wheels"
    write_wheel(source, name="demo-app", version="1.2.3", declares=True)
    root = tmp_path / "hub"
    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)})

    async with hub_pages(root) as pages:
        register_pages(HUB_APP, pages)
        await user.open("/")
        user.find(marker="install-demo-app").click()
        await user.should_see("hub.install_failed", retries=600)


@pytest.mark.apps("vibepy-timer")
@pytest.mark.integration
async def test_an_app_declaring_no_fields_says_so_and_offers_no_save(
    user: User, installed: Path
) -> None:
    async with hub_pages(installed) as pages:
        register_pages(HUB_APP, pages)
        await user.open("/")
        await user.should_see("Timer")
        user.find("Configure").click()
        await user.should_see("Nothing to configure")
        await user.should_not_see("Save")
