"""What only a real browser says about the board: its own CSS, and its own clock.

The `user` fixture simulates a client and never runs the stylesheet or the
timer. These tests drive headless Chrome through NiceGUI's `screen` fixture, so
each one asks something a simulation cannot answer.
"""

from pathlib import Path

import pytest
from nicegui.testing import Screen

from vibepy_core.adapters.nicegui import register_pages
from vibepy_core.app import page_runtime_for
from vibepy_hub.entry import APP, HUB_APP

GROUND = "rgb(234, 241, 241)"
"""What `board.css` paints behind the shell in light mode."""


def hub_pages(root: Path):
    return page_runtime_for(HUB_APP, APP.lifespan, config={"root": str(root), "proxy_port": 8080})


@pytest.mark.browser
async def test_the_board_arrives_dressed_in_its_own_stylesheet(
    screen: Screen, tmp_path: Path
) -> None:
    async with hub_pages(tmp_path / "hub") as pages:
        register_pages(HUB_APP, pages)
        screen.open("/")
        screen.should_contain("Your apps")
        screen.find_by_css(".vibepy-hub .hub-shell")
        # Selenium leaves both of these returning `Any`, so what each answers
        # is named here rather than carried untyped into an assertion.
        painted: object = screen.selenium.execute_script(  # pyright: ignore[reportUnknownMemberType]
            "return getComputedStyle(document.body).backgroundColor"
        )

    assert painted == GROUND


@pytest.mark.browser
@pytest.mark.integration
@pytest.mark.apps("vibepy-notes")
async def test_configure_opens_a_panel_and_cancel_closes_it(
    screen: Screen, installed: Path
) -> None:
    async with hub_pages(installed) as pages:
        register_pages(HUB_APP, pages)
        screen.open("/")
        screen.should_contain("Notes")
        screen.click("Configure")
        screen.should_contain("api_base_url")
        screen.click("Cancel")
        # Closing is a redraw of the whole board over the socket, which is
        # longer than the half second `should_not_contain` waits by default.
        screen.should_not_contain("api_base_url", wait=2)


@pytest.mark.browser
@pytest.mark.integration
@pytest.mark.apps("vibepy-notes")
async def test_unregistering_is_confirmed_in_a_dialog(screen: Screen, installed: Path) -> None:
    async with hub_pages(installed) as pages:
        register_pages(HUB_APP, pages)
        screen.open("/")
        screen.click("Unregister")
        screen.should_contain("Unregister this package folder?")
        # Both the card and the dialog say "Unregister", and it is the dialog's
        # answer this is after.
        screen.find_by_css(".hub-dialog .hub-primary").click()
        screen.should_contain("No folder registered")


@pytest.mark.browser
async def test_the_clock_does_not_redraw_over_what_is_being_typed(
    screen: Screen, tmp_path: Path, wheelhouse: Path
) -> None:
    async with hub_pages(tmp_path / "hub") as pages:
        register_pages(HUB_APP, pages)
        screen.open("/")
        screen.should_contain("No folder registered")
        screen.find_by_css(".hub-registry-entry input").send_keys(str(wheelhouse))
        screen.wait(3.5)
        entry = screen.find_by_css(".hub-registry-entry input")
        still: object = entry.get_attribute("value")  # pyright: ignore[reportUnknownMemberType]

    assert still == str(wheelhouse)
