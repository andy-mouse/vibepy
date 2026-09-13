"""What only a real browser says about the board: its own CSS, and its own clock.

The `user` fixture simulates a client and never runs the stylesheet or the
timer. These tests drive headless Chrome through NiceGUI's `screen` fixture, so
each one asks something a simulation cannot answer.

The Screen fixture serves the page from uvicorn in a thread of its own, with an
event loop of its own, so every Tool the page invokes runs there while this
test's loop only holds the runtime open for the length of the `async with`.
That works because the lock `StudioRoot` holds is an `asyncio.Lock` first awaited
on the server's loop, and so binds to the loop that actually uses it.
"""

from pathlib import Path

import pytest
from nicegui.testing import Screen

from tests_support import AGENT, studio, write_wheel
from vibepy_core.adapters.nicegui import register_pages
from vibepy_core.app import page_runtime_for
from vibepy_core.principal import Principal
from vibepy_studio.entry import APP, STUDIO_APP
from vibepy_studio.operating.pages.board import REFRESH_SECONDS

GROUND_LIGHT = "rgb(234, 241, 241)"
GROUND_DARK = "rgb(11, 21, 24)"
"""`board.css`'s `light-dark(#eaf1f1, #0b1518)` pair for the body background."""

CROWD = 10
"""Rows enough to overflow the list at the window size these tests ask for."""


def operating_pages(root: Path):
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
    await crowded(tmp_path / "root", tmp_path / "wheels")
    async with operating_pages(tmp_path / "root") as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
        screen.selenium.set_window_size(1280, 600)  # pyright: ignore[reportUnknownMemberType]
        screen.open("/")
        screen.should_contain("Your apps")
        screen.find_by_css(".vibepy-operating .operating-shell")
        screen.should_contain("demo-app-9")
        painted: object = asked(screen, "return getComputedStyle(document.body).backgroundColor")
        prefers_dark: object = asked(
            screen, "return window.matchMedia('(prefers-color-scheme: dark)').matches"
        )
        whole_page_still: object = asked(
            screen,
            "const p = document.scrollingElement; return p.scrollHeight <= p.clientHeight + 1",
        )
        list_scrolls: object = asked(
            screen,
            "const b = document.querySelector('.operating-board');"
            " return b !== null && b.scrollHeight > b.clientHeight",
        )
        head_stays: object = asked(
            screen,
            "const bar = document.querySelector('.operating-topbar');"
            " const b = document.querySelector('.operating-board');"
            " const before = bar.getBoundingClientRect().top;"
            " b.scrollTop += 200;"
            " return b.scrollTop > 0 && bar.getBoundingClientRect().top === before",
        )

    assert painted == (GROUND_DARK if prefers_dark else GROUND_LIGHT)
    assert whole_page_still is True
    assert list_scrolls is True
    assert head_stays is True


@pytest.mark.browser
async def test_the_clock_leaves_the_screen_where_the_reader_left_it(
    screen: Screen, tmp_path: Path
) -> None:
    """What only a real clock in a real browser says: a tick moves nothing.

    The board binds its elements to the listing it holds, so a tick assigns a
    value and rebuilds nothing. A simulated client can say the elements are the
    same objects; only a browser can say the reader's scroll position is where
    the reader left it. Deleting a wheel is the proof that the clock is running:
    the row it offered leaves the board without anyone touching the screen.
    """
    source = tmp_path / "wheels"
    await crowded(tmp_path / "root", source)
    async with operating_pages(tmp_path / "root") as pages:
        register_pages(STUDIO_APP, pages, principal=Principal(id="operator"))
        screen.selenium.set_window_size(1280, 600)  # pyright: ignore[reportUnknownMemberType]
        screen.open("/")
        screen.should_contain("demo-app-9")
        scrolled: object = asked(
            screen,
            "const b = document.querySelector('.operating-board');"
            " b.scrollTop += 200;"
            " window.__row = document.querySelector('.operating-app-row');"
            " return b.scrollTop",
        )
        screen.wait(2 * REFRESH_SECONDS + 0.5)
        still_there: object = asked(
            screen,
            "const b = document.querySelector('.operating-board');"
            " return [b.scrollTop, document.querySelector('.operating-app-row') === window.__row]",
        )

        # The source no longer offers this wheel, and nothing has told the
        # board so. What reads it again is the clock.
        next(source.glob("demo_app_9-*.whl")).unlink()
        screen.wait(2 * REFRESH_SECONDS + 0.5)
        screen.should_not_contain("demo-app-9")

    assert still_there == [scrolled, True]
