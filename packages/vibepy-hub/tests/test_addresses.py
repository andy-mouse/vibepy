"""An App's address: allocated once, derived from what is stored.

The port belongs to the installation and the hostname is the App's canonical
name (ADR-028), so the address is built rather than kept. See
`docs/decisions/ADR-031-the-proxy-is-traefik.md`.
"""

from pathlib import Path

import yaml

from tests_support import EXAMPLES, hub
from vibepy_hub.internals import read_state
from vibepy_hub.internals.routing import PORT_BASE, address, allocate
from vibepy_hub.models import AppListing, Installation, RunningApp


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


async def test_the_window_writes_a_configuration_that_apps_do_not_change(
    tmp_path: Path,
) -> None:
    """The install configuration is written once and never follows an App."""
    root = tmp_path / "hub"

    async with hub(root, proxy_port=9999) as tools:
        written = (root / "traefik.yml").read_text(encoding="utf-8")
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        after = (root / "traefik.yml").read_text(encoding="utf-8")

    assert written == after
    config = yaml.safe_load(written)
    assert config["entryPoints"]["web"]["address"] == ":9999"
    assert config["providers"]["file"]["directory"] == str(root / "routes")
    assert config["providers"]["file"]["watch"] is True


async def test_installing_writes_a_route_and_removing_deletes_it(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        route = root / "routes" / "vibepy-todo.yml"
        written = yaml.safe_load(route.read_text(encoding="utf-8"))
        port = (await read_state(root)).ports["vibepy-todo"]
        await tools.invoke("remove_app", {"app_name": "vibepy-todo"})
        gone = route.exists()

    router = written["http"]["routers"]["vibepy-todo"]
    assert router["rule"] == "Host(`vibepy-todo.localhost`)"
    assert router["service"] == "vibepy-todo"
    servers = written["http"]["services"]["vibepy-todo"]["loadBalancer"]["servers"]
    assert servers == [{"url": f"http://127.0.0.1:{port}"}]
    assert gone is False


async def test_an_address_outlives_a_run(tmp_path: Path) -> None:
    """The port belongs to the installation, so stopping does not release it."""
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
            },
        )
        first = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        stopped = await tools.invoke("stop_app", {"app_name": "vibepy-todo"})
        second = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})

    assert isinstance(first, RunningApp)
    assert isinstance(stopped, RunningApp)
    assert isinstance(second, RunningApp)
    assert first.url == "http://vibepy-todo.localhost:8080"
    assert stopped.url == first.url
    assert second.url == first.url
