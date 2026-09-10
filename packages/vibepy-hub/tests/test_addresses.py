"""An App's address: allocated once, derived from what is stored.

The port belongs to the installation and the hostname is the App's canonical
name (ADR-028), so the address is built rather than kept. See
`docs/decisions/ADR-031-the-proxy-is-traefik.md`.

This file is the second departure from testing public contracts, after
`test_processes.py`. An App's own port is never published -- that is the
decision, not an oversight -- so no Tool's answer can be asked which port an
App holds, and `allocate` and the stored state are reached directly. What a
Tool can answer is asked of the Tool.
"""

from pathlib import Path

import yaml

from tests_support import FIXTURES, hub
from vibepy_core.errors import ErrorCategory
from vibepy_hub.internals import read_state, write_state
from vibepy_hub.internals.routing import PORT_BASE, address, allocate
from vibepy_hub.models import AppListing, Installation, RunningApp


def test_the_first_app_takes_the_base_port() -> None:
    assert allocate([]) == PORT_BASE


def test_a_timer_app_takes_the_next_free_port() -> None:
    assert allocate([PORT_BASE]) == PORT_BASE + 1


def test_a_released_port_is_taken_again_before_the_next_one() -> None:
    """Removing an App frees its port; the next install fills the gap."""
    assert allocate([PORT_BASE + 1]) == PORT_BASE


def test_an_address_names_the_app_and_the_proxy() -> None:
    assert address("vibepy-todo", 8080) == "http://vibepy-todo.localhost:8080"


async def test_installing_gives_an_app_an_address_before_it_is_started(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub", proxy_port=8080) as tools:
        await tools.invoke("register_package_source", {"path": str(FIXTURES)})
        installed = await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        listed = await tools.invoke("list_apps", {})

    assert isinstance(installed, Installation)
    assert installed.app.url == "http://vibepy-todo.localhost:8080"
    assert isinstance(listed, AppListing)
    rows = [row for row in listed.apps if row.app_name == "vibepy-todo"]
    assert [row.url for row in rows] == ["http://vibepy-todo.localhost:8080"]
    assert [row.state for row in rows] == ["installed"]


async def test_two_apps_hold_two_ports_and_removing_one_releases_it(tmp_path: Path) -> None:
    """Both Apps declare Pages, because only an App that can be served holds a port."""
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(FIXTURES)})
        await tools.invoke("register_package_source", {"path": str(FIXTURES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke("install_app", {"app_name": "vibepy-timer"})
        both = (await read_state(root)).ports
        await tools.invoke("remove_app", {"app_name": "vibepy-todo"})
        after = (await read_state(root)).ports

    assert sorted(both.values()) == [PORT_BASE, PORT_BASE + 1]
    assert "vibepy-todo" not in after
    assert after["vibepy-timer"] == both["vibepy-timer"]


async def test_installing_an_installed_app_is_refused(tmp_path: Path) -> None:
    """What installing over an installation means is nobody's decision yet.

    No milestone owns updating an App and the Hub publishes no Tool for it, so
    the Hub says what is true and names two operations that already exist.
    """
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(FIXTURES)})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        held = (await read_state(root)).ports["vibepy-todo"]
        again = await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        after = await read_state(root)
        env = (root / "envs" / "vibepy-todo").is_dir()

    assert isinstance(again, Installation)
    assert again.diagnostic is not None
    assert again.diagnostic.code == "hub.already_installed"
    assert again.diagnostic.category == ErrorCategory.CALLER
    # The refusal changed nothing: the environment is where it was, and so is
    # the address. The failure this replaces removed the environment.
    assert env is True
    assert after.ports["vibepy-todo"] == held


async def test_the_window_writes_a_configuration_that_apps_do_not_change(
    installed: Path,
) -> None:
    """The install configuration is written once and never follows an App."""
    async with hub(installed, proxy_port=9999) as tools:
        written = (installed / "traefik.yml").read_text(encoding="utf-8")
        await tools.invoke("list_apps", {})
        after = (installed / "traefik.yml").read_text(encoding="utf-8")

    assert written == after
    config = yaml.safe_load(written)
    assert config["entryPoints"]["web"]["address"] == ":9999"
    assert config["providers"]["file"]["directory"] == str(installed / "routes")
    assert config["providers"]["file"]["watch"] is True


async def test_installing_writes_a_route_and_removing_deletes_it(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(FIXTURES)})
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


async def test_an_address_outlives_a_run(tmp_path: Path, installed: Path) -> None:
    """The port belongs to the installation, so stopping does not release it."""
    async with hub(installed) as tools:
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


async def test_an_app_with_no_pages_gets_no_address(installed: Path) -> None:
    """An address is for an App that can answer at one.

    `fixtures/notes` declares no Pages, so it has no Web channel (ADR-017) and
    `start_app` refuses it. An address for it would name something that will
    never answer, and its route would point the proxy at a port nothing binds.
    """
    async with hub(installed) as tools:
        listed = await tools.invoke("list_apps", {})
        held = (await read_state(installed)).ports
        route = (installed / "routes" / "vibepy-notes.yml").exists()

    assert isinstance(listed, AppListing)
    rows = {row.app_name: row for row in listed.apps}
    assert rows["vibepy-notes"].has_pages is False
    assert rows["vibepy-notes"].url is None
    assert "vibepy-notes" not in held
    assert route is False


async def test_an_installed_app_holding_no_port_is_told_to_install_it_again(
    tmp_path: Path, installed: Path
) -> None:
    """An App is installed once its facts are written, and given a port after.

    A window that closes between the two leaves this state behind, and so does
    a state file written before this stage; the state file is written here
    because it is the same file either one leaves. The environment is there and
    works, so the refusal is not `hub.not_installed` -- installing is refused
    while the App is there, and a start that allocated a port would be a
    partial install under another name.
    """
    async with hub(installed) as tools:
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
            },
        )
        # What either leaves behind: an installed App, its configuration, and
        # no port.
        before = await read_state(installed)
        await write_state(installed, before.model_copy(update={"ports": {}}))

        refused = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})
        listed = await tools.invoke("list_apps", {})

        # And the remedy the code names: remove it, then install it again.
        await tools.invoke("remove_app", {"app_name": "vibepy-todo"})
        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
            },
        )
        started = await tools.invoke("start_app", {"app_name": "vibepy-todo", "secrets": {}})

    assert isinstance(refused, RunningApp)
    assert refused.diagnostic is not None
    assert refused.diagnostic.code == "hub.no_address"
    assert refused.url is None
    assert isinstance(listed, AppListing)
    assert [row.url for row in listed.apps if row.app_name == "vibepy-todo"] == [None]
    assert isinstance(started, RunningApp)
    assert started.diagnostic is None
    assert started.url == "http://vibepy-todo.localhost:8080"
