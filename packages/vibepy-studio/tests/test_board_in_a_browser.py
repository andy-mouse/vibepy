"""What only a real browser says about the board: its own CSS, and its own clock.

The `user` fixture simulates a client and never runs the stylesheet or the
timer. These tests drive headless Chrome through NiceGUI's `screen` fixture, so
each one asks something a simulation cannot answer.

The Screen fixture serves the page from uvicorn in a thread of its own, with an
event loop of its own, so every Tool the page invokes runs there while this
test's loop only holds the runtime open for the length of the `async with`.
That works because `StudioDeps.state_lock` is an `asyncio.Lock` first awaited on
the server's loop, and so binds to the loop that actually uses it.
"""

from pathlib import Path

import pytest
from nicegui.testing import Screen
from selenium.webdriver.common.keys import Keys

from tests_support import AGENT, studio, write_wheel
from vibepy_core.adapters.nicegui import register_pages
from vibepy_core.app import page_runtime_for
from vibepy_studio.entry import APP, STUDIO_APP
from vibepy_studio.operating.pages.board import REFRESH_SECONDS

GROUND = "rgb(234, 241, 241)"
"""What `board.css` paints behind the shell in light mode."""

CROWD = 10
"""Rows enough to overflow the list at the window size these tests ask for."""


def hub_pages(root: Path):
    return page_runtime_for(
        STUDIO_APP, APP.lifespan, config={"root": str(root), "proxy_port": 8080}
    )


def asked(screen: Screen, question: str) -> object:
    """Selenium leaves `execute_script` returning `Any`; what it answers is named here."""
    return screen.selenium.execute_script(question)  # pyright: ignore[reportUnknownMemberType]


async def crowded(root: Path, source: Path) -> None:
    """A registered folder holding more Apps than the list can show at once."""
    for index in range(CROWD):
        write_wheel(source, name=f"demo-app-{index}", version="1.0.0", declares=True)
    async with studio(root) as tools:
        await tools.invoke("register_package_source", {"path": str(source)}, principal=AGENT)


@pytest.mark.browser
async def test_the_board_arrives_dressed_in_its_own_stylesheet(
    screen: Screen, tmp_path: Path
) -> None:
    await crowded(tmp_path / "hub", tmp_path / "wheels")
    async with hub_pages(tmp_path / "hub") as pages:
        register_pages(STUDIO_APP, pages)
        screen.selenium.set_window_size(1280, 600)  # pyright: ignore[reportUnknownMemberType]
        screen.open("/")
        screen.should_contain("Your apps")
        screen.find_by_css(".vibepy-hub .hub-shell")
        screen.should_contain("demo-app-9")
        painted: object = asked(screen, "return getComputedStyle(document.body).backgroundColor")
        whole_page_still: object = asked(
            screen,
            "const p = document.scrollingElement; return p.scrollHeight <= p.clientHeight + 1",
        )
        list_scrolls: object = asked(
            screen,
            "const b = document.querySelector('.hub-board');"
            " return b !== null && b.scrollHeight > b.clientHeight",
        )
        head_stays: object = asked(
            screen,
            "const bar = document.querySelector('.hub-topbar');"
            " const b = document.querySelector('.hub-board');"
            " const before = bar.getBoundingClientRect().top;"
            " b.scrollTop += 200;"
            " return b.scrollTop > 0 && bar.getBoundingClientRect().top === before",
        )

    assert painted == GROUND
    assert whole_page_still is True
    assert list_scrolls is True
    assert head_stays is True


@pytest.mark.browser
async def test_the_clock_does_not_redraw_over_what_is_being_typed(
    screen: Screen, tmp_path: Path
) -> None:
    # A redraw rebuilds every element the refreshable holds, so the empty
    # state's DOM node is replaced by one each time the clock ticks. Holding on
    # to the node is therefore how a test sees a tick arrive, or not arrive.
    watched = (
        "const kept = window.__watched; window.__watched = document.querySelector('.hub-empty');"
    )
    async with hub_pages(tmp_path / "hub") as pages:
        register_pages(STUDIO_APP, pages)
        screen.open("/")
        screen.should_contain("No folder registered")
        asked(screen, watched)
        entry = screen.find_by_css(".hub-registry-entry input")
        typed = str(tmp_path / "wheels")
        entry.send_keys(typed)
        screen.wait(2 * REFRESH_SECONDS + 0.5)
        typing_survived: object = screen.find_by_css(".hub-registry-entry input").get_attribute(  # pyright: ignore[reportUnknownMemberType]
            "value"
        )
        held_off: object = asked(
            screen, f"{watched} return document.querySelector('.hub-empty') === kept"
        )

        # Nothing is being typed any more, so the clock is owed a redraw.
        # Erased key by key: `clear()` empties the field without the event
        # Quasar reports a change through, so the page would never hear of it.
        screen.find_by_css(".hub-registry-entry input").send_keys(Keys.BACKSPACE * len(typed))
        screen.wait(2 * REFRESH_SECONDS + 0.5)
        resumed: object = asked(
            screen, f"{watched} return document.querySelector('.hub-empty') !== kept"
        )

    assert typing_survived == typed
    assert held_off is True
    assert resumed is True
