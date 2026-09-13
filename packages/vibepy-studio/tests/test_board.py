"""The board shows the operating role's core state and acts on it through the operating
role's Tools."""

import asyncio
import logging
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePath

import pytest
from nicegui import ui
from nicegui.testing import User
from pydantic import BaseModel

from tests_support import AGENT, studio, write_wheel
from vibepy_core.adapters.nicegui import register_pages
from vibepy_core.app import (
    ConfigFieldDescription,
    ConfigFieldType,
    page_registry_for,
    page_runtime_for,
)
from vibepy_core.page import PageRuntime
from vibepy_core.principal import Principal
from vibepy_studio.entry import APP, STUDIO_APP
from vibepy_studio.operating.host import PlatformUnsupported
from vibepy_studio.operating.models import AppListing, AppRow, ConfigDescription
from vibepy_studio.operating.pages import board

TICK = 0.05
"""What the board's clock is set to while a test waits out a tick."""


def operating_pages(root: Path):
    return page_runtime_for(
        STUDIO_APP, APP.lifespan, config={"root": str(root), "proxy_port": 8080}
    )


@dataclass
class Dialog:
    """The folder dialog as a test scripts it: what it was asked, and that it was."""

    titles: list[str]
    """The title the board gave each time it opened the dialog."""
    opened: asyncio.Event
    """Set the first time the board opens it.

    A click hands the handler to the event loop, and cancelling changes nothing
    on the screen, so reaching the seam is what a test waits for. The fake
    answers without awaiting, so a handler that has reached it has also run to
    the end of its step.
    """

    async def asked(self) -> None:
        """Wait until the board has opened the dialog."""
        async with asyncio.timeout(5):
            await self.opened.wait()


def dialog_answers(
    monkeypatch: pytest.MonkeyPatch, answer: PurePath | Exception | None, /
) -> Dialog:
    """Replace the board's one host-operation seam with one answering `answer`.

    `choose_folder` opens a window on the machine Studio runs on, so no test
    calls the real one. The board reaches it through its own module name, which
    is the seam its docstring names.
    """
    dialog = Dialog(titles=[], opened=asyncio.Event())

    async def chosen(*, title: str) -> PurePath | None:
        dialog.titles.append(title)
        dialog.opened.set()
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(board, "choose_folder", chosen)
    return dialog


def register_button(user: User) -> ui.html:
    """The Register folder button, whatever it currently says."""
    found = user.find(marker="register-folder").elements.pop()
    assert isinstance(found, ui.html)
    return found


async def test_the_board_registers_the_folder_the_dialog_answered(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "wheels"
    write_wheel(source, name="demo-app", version="1.2.3", declares=True)
    dialog = dialog_answers(monkeypatch, PurePath(source))

    async with operating_pages(tmp_path / "root") as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
        await user.open("/")
        await user.should_see("No folder registered")
        await user.should_see("No package folder selected")

        user.find(marker="register-folder").click()
        await user.should_see("demo-app")
        await user.should_see("v1.2.3")
        await user.should_see("Install")

    assert dialog.titles == [board.CHOOSE_TITLE]


async def test_cancelling_the_dialog_registers_nothing(
    user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancelling is an answer: no Tool is called at all, and the card is left as it was."""
    dialog = dialog_answers(monkeypatch, None)
    listed = Listings(listing(source=None))
    board_over(listed)
    await user.open("/")
    await user.should_see("No folder registered")

    user.find(marker="register-folder").click()
    await dialog.asked()
    await user.should_see("No folder registered")
    await user.should_see("No package folder selected")

    # The dialog was opened, so the handler ran past the seam -- and stopped
    # there. Without the `chosen is None` guard, `str(None)` would have reached
    # the Tool, which would answer with a diagnostic and leave the card looking
    # exactly like this.
    assert "register_package_source" not in listed.called


async def test_the_button_says_it_is_working_while_the_dialog_is_open(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dialog is a window on the desktop, so the control that opened it waits visibly."""
    opened = asyncio.Event()
    holding = asyncio.Event()

    async def chosen(*, title: str) -> PurePath | None:
        opened.set()
        await holding.wait()
        return None

    monkeypatch.setattr(board, "choose_folder", chosen)

    async with operating_pages(tmp_path / "root") as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
        await user.open("/")
        user.find(marker="register-folder").click()
        await asyncio.wait_for(opened.wait(), timeout=5)

        waiting = register_button(user)
        assert waiting.content == board.CHOOSING_LABEL
        assert "disabled" in waiting.props

        holding.set()
        await user.should_see(board.REGISTER_LABEL)
        assert "disabled" not in register_button(user).props


async def test_a_dialog_that_cannot_be_shown_is_said_and_the_button_comes_back(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A host failure is not a Tool's diagnostic, so it is said rather than bound."""
    dialog_answers(monkeypatch, PlatformUnsupported("linux"))

    async with operating_pages(tmp_path / "root") as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
        await user.open("/")

        user.find(marker="register-folder").click()
        await user.should_see("Could not open the folder dialog")
        await user.should_see("No folder registered")
        assert register_button(user).content == board.REGISTER_LABEL


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


FIELDS = [
    ConfigFieldDescription(name="api_base_url", type=ConfigFieldType.STRING, required=True),
    ConfigFieldDescription(name="api_token", type=ConfigFieldType.SECRET, required=True),
]
"""What a scripted App declares, for the panel a test opens."""


class Listings:
    """A PrincipalToolInvoker answering `list_apps` with whatever it is set to.

    What the clock does to the elements the board drew is a question about the
    board, not about installing: the listing is scripted so that one tick's
    answer differs from the last by exactly what a test is asking about.
    """

    def __init__(self, listed: AppListing) -> None:
        """Answer with `listed` until something else is put in its place."""
        self.listed = listed
        self.called: list[str] = []
        """Every Tool this invoker was asked for, so a test can assert one was not."""
        self.described = asyncio.Event()
        """Held closed to keep a `describe_config` in flight while the clock ticks."""
        self.described.set()

    def invoke(
        self, name: str, raw_input: Mapping[str, object], /, *, principal: Principal
    ) -> Awaitable[BaseModel]:
        """Answer `list_apps`, and what a row's configuration panel opens over."""
        self.called.append(name)

        async def answered() -> BaseModel:
            if name == "describe_config":
                await self.described.wait()
                return ConfigDescription(app_name=str(raw_input["app_name"]), fields=FIELDS)
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


async def test_a_row_rebuilt_under_an_open_panel_keeps_what_was_typed(
    user: User, fast_clock: None
) -> None:
    """A tick that reorders the rows must not take the form one of them is holding.

    `sort_rows` puts a running App first, so another App starting rebuilds every
    row -- including the one whose configuration panel is open. What was typed
    is the board's state, not the box's, so it survives the rebuild.
    """
    listed = Listings(listing(app_row("demo-app", "installed"), app_row("other-app", "installed")))
    board_over(listed)
    await user.open("/")
    user.find(marker="configure-demo-app").click()
    await user.should_see("api_base_url")
    user.find(marker="field-demo-app-api_base_url").type("https://notes.internal")
    drawn = user.find(marker="row-demo-app").elements.pop()

    listed.listed = listing(app_row("demo-app", "installed"), app_row("other-app", "running"))
    await ticked()

    await user.should_see("Stop")
    # The reordering is what makes this test's subject happen: without a rebuilt
    # row, the typing would survive whatever the draft is kept in.
    assert user.find(marker="row-demo-app").elements.pop() is not drawn
    entry = user.find(kind=ui.input, marker="field-demo-app-api_base_url").elements.pop()
    assert entry.value == "https://notes.internal"


async def test_a_rebuilt_row_still_names_what_its_panel_lacks(user: User, fast_clock: None) -> None:
    """What a save named as missing is state too, so a rebuilt row says it again."""
    listed = Listings(listing(app_row("demo-app", "installed"), app_row("other-app", "installed")))
    board_over(listed)
    await user.open("/")
    user.find(marker="configure-demo-app").click()
    await user.should_see("api_base_url")
    user.find("Save").click()
    await user.should_see("Missing required fields: api_base_url, api_token")
    drawn = user.find(marker="row-demo-app").elements.pop()

    listed.listed = listing(app_row("demo-app", "installed"), app_row("other-app", "running"))
    await ticked()

    assert user.find(marker="row-demo-app").elements.pop() is not drawn
    await user.should_see("Missing required fields: api_base_url, api_token")


async def test_an_empty_board_says_why_it_is_empty_after_a_tick(
    user: User, fast_clock: None
) -> None:
    """Why a board is empty is a value the clock can change without any row changing."""
    listed = Listings(listing())
    board_over(listed)
    await user.open("/")
    await user.should_see("No apps found")

    listed.listed = listing(source=None)
    await ticked()

    await user.should_see("No package folder selected")
    await user.should_not_see("No apps found")


async def test_an_app_that_leaves_the_board_takes_its_open_panel_with_it(
    user: User, fast_clock: None
) -> None:
    """A draft belongs to a row; a row the listing drops keeps nothing.

    An App leaves by paths that are nobody's button -- its wheel removed, the
    folder unregistered, an uninstall in another window -- and what was typed
    into its panel must not be waiting, filled in, if it comes back.
    """
    listed = Listings(listing(app_row("demo-app", "installed"), app_row("other-app", "installed")))
    board_over(listed)
    await user.open("/")
    user.find(marker="configure-demo-app").click()
    await user.should_see("api_base_url")
    user.find(marker="field-demo-app-api_base_url").type("https://notes.internal")

    listed.listed = listing(app_row("other-app", "installed"))
    await ticked()
    await user.should_not_see("api_base_url")

    listed.listed = listing(app_row("demo-app", "installed"), app_row("other-app", "installed"))
    await ticked()

    await user.should_see("demo-app")
    await user.should_not_see("api_base_url")


async def test_a_row_leaving_while_its_panel_opens_is_not_an_error(
    user: User, fast_clock: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Opening a panel runs across an await, and the clock runs during it."""
    listed = Listings(listing(app_row("demo-app", "installed"), app_row("other-app", "installed")))
    listed.described.clear()
    board_over(listed)
    await user.open("/")
    user.find(marker="configure-demo-app").click()

    # The App is gone and its row rebuilt before `describe_config` answers.
    listed.listed = listing(app_row("other-app", "installed"))
    await ticked()
    listed.described.set()
    await ticked()

    assert [record.message for record in caplog.records if record.levelno >= logging.ERROR] == []
    await user.should_see("other-app")
