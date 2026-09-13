"""The board shows the operating role's core state and acts on it through the operating
role's Tools."""

import asyncio
from collections.abc import Awaitable, Mapping
from pathlib import Path, PurePath

import pytest
from nicegui import ui
from nicegui.testing import User
from pydantic import BaseModel

from tests_support import AGENT, studio, write_wheel
from vibepy_core.adapters.nicegui import register_pages
from vibepy_core.app import page_registry_for, page_runtime_for
from vibepy_core.page import PageRuntime
from vibepy_core.principal import Principal
from vibepy_studio.entry import APP, STUDIO_APP
from vibepy_studio.operating.models import AppListing, AppRow, ConfigDescription
from vibepy_studio.operating.pages import board

TICK = 0.05
"""What the board's clock is set to while a test waits out a tick."""


def operating_pages(root: Path):
    return page_runtime_for(
        STUDIO_APP, APP.lifespan, config={"root": str(root), "proxy_port": 8080}
    )


async def test_the_board_shows_what_list_apps_answers(user: User, tmp_path: Path) -> None:
    source = tmp_path / "wheels"
    write_wheel(source, name="demo-app", version="1.2.3", declares=True)

    async with operating_pages(tmp_path / "root") as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
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
    async with operating_pages(installed) as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
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
    async with operating_pages(installed) as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
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
    async with operating_pages(installed) as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
        await user.open("/")
        user.find("Configure").click()
        await user.should_see("api_base_url")
        user.find(marker="field-vibepy-notes-api_base_url").type("https://notes.internal")
        user.find(marker="field-vibepy-notes-api_token").type("k")
        user.find("Save").click()
        await user.should_see("Notes configured")

    async with studio(installed) as tools:
        described = await tools.invoke(
            "describe_config", {"app_name": "vibepy-notes"}, principal=AGENT
        )

    assert isinstance(described, ConfigDescription)
    assert described.values == {"api_base_url": "https://notes.internal"}
    assert described.secrets_set == ["api_token"]


@pytest.mark.integration
async def test_install_invokes_the_tool_and_shows_its_answer(user: User, tmp_path: Path) -> None:
    # A wheel that declares an App and brings no framework with it. `uv pip
    # install` succeeds; the description step is what fails, because the
    # environment it lands in has no `vibepy_core` for `python -m
    # vibepy_core.describe` to run. That is still this test's subject: the
    # board has to put whatever `install_app` answers on the screen, and a
    # diagnostic is the answer that is cheap to arrange. What a real
    # distribution installs is `test_installation.py`'s subject.
    source = tmp_path / "wheels"
    write_wheel(source, name="demo-app", version="1.2.3", declares=True)
    root = tmp_path / "root"
    async with studio(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)}, principal=AGENT)

    async with operating_pages(root) as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
        await user.open("/")
        user.find(marker="install-demo-app").click()
        await user.should_see("operating.install_failed", retries=600)


@pytest.mark.apps("vibepy-timer")
@pytest.mark.integration
async def test_an_app_declaring_no_fields_says_so_and_offers_no_save(
    user: User, installed: Path
) -> None:
    async with operating_pages(installed) as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
        await user.open("/")
        await user.should_see("Timer")
        user.find("Configure").click()
        await user.should_see("Nothing to configure")
        await user.should_not_see("Save")


@pytest.mark.apps("vibepy-notes")
@pytest.mark.integration
async def test_configure_opens_a_panel_and_cancel_closes_it(user: User, installed: Path) -> None:
    async with operating_pages(installed) as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
        await user.open("/")
        await user.should_see("Notes")
        user.find("Configure").click()
        await user.should_see("api_base_url")

        user.find("Cancel").click()
        await user.should_not_see("api_base_url")


@pytest.mark.apps("vibepy-notes")
@pytest.mark.integration
async def test_unregistering_is_confirmed_in_a_dialog(user: User, installed: Path) -> None:
    async with operating_pages(installed) as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
        await user.open("/")
        await user.should_see("Notes")
        user.find("Unregister").click()
        await user.should_see("Unregister this package folder?")

        user.find(marker="dialog-confirm").click()
        # The dialog says the installed Apps stay, so what the answer changes
        # is the source card and nothing else on the board.
        await user.should_see("No folder registered")
        await user.should_see("Notes")


class Listings:
    """A PrincipalToolInvoker answering `list_apps` with whatever it is set to.

    What the clock does to the elements the board drew is a question about the
    board, not about installing: the listing is scripted so that one tick's
    answer differs from the last by exactly what a test is asking about.
    """

    def __init__(self, listed: AppListing) -> None:
        """Answer with `listed` until something else is put in its place."""
        self.listed = listed

    def invoke(
        self, name: str, raw_input: Mapping[str, object], /, *, principal: Principal
    ) -> Awaitable[BaseModel]:
        """Answer `list_apps`; the board reads nothing else on the clock."""

        async def answered() -> BaseModel:
            assert name == "list_apps", name
            return self.listed

        return answered()


def board_over(listed: Listings) -> PageRuntime:
    """Register the board's Pages over a scripted listing."""
    pages = PageRuntime(registry=page_registry_for(STUDIO_APP), tools=listed)
    register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
    return pages


def app_row(app_name: str, state: str, /) -> AppRow:
    """One App in a listing, named and versioned so the board has something to draw."""
    return AppRow(app_name=app_name, name=app_name, state=state, distribution_version="1.0.0")


def listing(*rows: AppRow, source: str | None = "/wheels") -> AppListing:
    """A listing of `rows`, from a registered folder unless one is not wanted."""
    return AppListing(apps=list(rows), source=None if source is None else PurePath(source))


async def ticked(times: int = 2) -> None:
    """Wait out `times` ticks of the board's clock."""
    await asyncio.sleep(TICK * (times + 1))


@pytest.fixture
def fast_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the board's clock fast enough for a test to wait out a tick."""
    monkeypatch.setattr(board, "REFRESH_SECONDS", TICK)


async def test_a_tick_over_an_unchanged_listing_keeps_the_elements_it_drew(
    user: User, fast_clock: None
) -> None:
    board_over(Listings(listing(app_row("demo-app", "installed"))))
    await user.open("/")
    await user.should_see("demo-app")
    drawn = user.find(marker="row-demo-app").elements.pop()

    await ticked()

    assert user.find(marker="row-demo-app").elements.pop() is drawn


async def test_a_changed_state_reaches_the_row_without_replacing_it(
    user: User, fast_clock: None
) -> None:
    listed = Listings(listing(app_row("demo-app", "installed")))
    board_over(listed)
    await user.open("/")
    await user.should_see("Start")
    drawn = user.find(marker="row-demo-app").elements.pop()

    listed.listed = listing(app_row("demo-app", "running"))
    await ticked()

    await user.should_see("Stop")
    assert user.find(marker="row-demo-app").elements.pop() is drawn


async def test_an_app_added_and_one_removed_reach_the_board_on_a_tick(
    user: User, fast_clock: None
) -> None:
    listed = Listings(listing(app_row("demo-app", "installed")))
    board_over(listed)
    await user.open("/")
    await user.should_see("demo-app")

    listed.listed = listing(app_row("other-app", "available"))
    await ticked()

    await user.should_see("other-app")
    await user.should_not_see("demo-app")


async def test_a_tick_does_not_take_what_is_being_typed(user: User, fast_clock: None) -> None:
    board_over(Listings(listing(source=None)))
    await user.open("/")
    await user.should_see("No package folder selected")
    user.find(marker="package-folder").type("/wheels")

    await ticked()

    entry = user.find(kind=ui.input, marker="package-folder").elements.pop()
    assert entry.value == "/wheels"
