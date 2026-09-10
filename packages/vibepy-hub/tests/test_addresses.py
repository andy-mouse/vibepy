"""An App's address: allocated once, derived from what is stored.

The port belongs to the installation and the hostname is the App's canonical
name (ADR-028), so the address is built rather than kept. See
`docs/decisions/ADR-031-the-proxy-is-traefik.md`.
"""

from pathlib import Path

from tests_support import EXAMPLES, hub
from vibepy_hub.internals import read_state
from vibepy_hub.internals.routing import PORT_BASE, address, allocate
from vibepy_hub.models import AppListing, Installation


def test_the_first_app_takes_the_base_port() -> None:
    assert allocate({}, "vibepy-todo") == PORT_BASE


def test_a_second_app_takes_the_next_free_port() -> None:
    assert allocate({"vibepy-todo": PORT_BASE}, "vibepy-notes") == PORT_BASE + 1


def test_an_app_that_already_holds_one_keeps_it() -> None:
    taken = {"vibepy-todo": PORT_BASE, "vibepy-notes": PORT_BASE + 1}
    assert allocate(taken, "vibepy-todo") == PORT_BASE


def test_a_released_port_is_taken_again_before_the_next_one() -> None:
    """Removing an App frees its port; the next install fills the gap."""
    assert allocate({"vibepy-notes": PORT_BASE + 1}, "vibepy-other") == PORT_BASE


def test_an_address_names_the_app_and_the_proxy() -> None:
    assert address("vibepy-todo", 8080) == "http://vibepy-todo.localhost:8080"


async def test_installing_gives_an_app_an_address_before_it_is_started(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub", proxy_port=8080) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        installed = await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(installed, Installation)
    assert installed.app.url == "http://vibepy-todo.localhost:8080"
    assert isinstance(listed, AppListing)
    rows = [row for row in listed.apps if row.app_name == "vibepy-todo"]
    assert [row.url for row in rows] == ["http://vibepy-todo.localhost:8080"]
    assert [row.state for row in rows] == ["installed"]


async def test_two_apps_hold_two_ports_and_removing_one_releases_it(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke("install_app", {"app_name": "vibepy-notes"})
        both = (await read_state(root)).ports
        await tools.invoke("remove_app", {"app_name": "vibepy-todo"})
        after = (await read_state(root)).ports

    assert sorted(both.values()) == [PORT_BASE, PORT_BASE + 1]
    assert "vibepy-todo" not in after
    assert after["vibepy-notes"] == both["vibepy-notes"]


async def test_reinstalling_keeps_the_address_a_user_kept(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-notes"})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        first = (await read_state(root)).ports["vibepy-todo"]
        again = await tools.invoke("install_app", {"app_name": "vibepy-todo"})

    assert isinstance(again, Installation)
    assert (await read_state(root)).ports["vibepy-todo"] == first
