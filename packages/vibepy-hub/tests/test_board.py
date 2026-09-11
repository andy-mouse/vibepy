"""The board shows Hub Core's state and acts on it through the Hub's Tools."""

from pathlib import Path

import pytest
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

        user.find("package folder").type(str(source))
        user.find("Register").click()
        await user.should_see("demo-app")
        await user.should_see("v1.2.3")
        await user.should_see("Install")


@pytest.mark.apps("vibepy-notes")
@pytest.mark.integration
async def test_install_moves_a_row_to_installed_and_opens_its_configuration(
    user: User, installed: Path, wheelhouse: Path
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
async def test_a_saved_configuration_reaches_the_hub(user: User, installed: Path) -> None:
    async with hub_pages(installed) as pages:
        register_pages(HUB_APP, pages)
        await user.open("/")
        user.find("Configure").click()
        await user.should_see("api_base_url")
        user.find("api_base_url").type("https://notes.internal")
        user.find("api_token").type("k")
        user.find("Save").click()
        await user.should_see("Notes configured")

    async with hub(installed) as tools:
        described = await tools.invoke("describe_config", {"app_name": "vibepy-notes"})

    assert isinstance(described, ConfigDescription)
    assert described.values == {"api_base_url": "https://notes.internal"}
    assert described.secrets_set == ["api_token"]
