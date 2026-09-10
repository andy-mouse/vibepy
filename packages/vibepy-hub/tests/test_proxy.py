"""What a Traefik in front of an App does and does not carry.

The proxy is adopted whole (ADR-031), so what is tested here is the seam: a
NiceGUI Page needs a WebSocket, and Traefik's documentation does not say it
carries one. This file answers that from the running pair rather than from a
document.
"""

from pathlib import Path

from tests_support import EXAMPLES, FIXTURES, first_frame, free_port, hub, served_body, traefik
from vibepy_hub.models import RunningApp

SOCKET_IO = "/_nicegui_ws/socket.io/?EIO=4&transport=websocket"
"""Where NiceGUI mounts socket.io (`nicegui/nicegui.py`, `app.mount('/_nicegui_ws/', ...)`)."""


async def test_a_page_s_websocket_survives_the_proxy(tmp_path: Path) -> None:
    """Traefik's documentation does not say it carries a WebSocket, and a
    NiceGUI Page does not work without one. This settles it, and settles it
    against the configuration the Hub itself wrote rather than one composed
    here."""
    proxy_port = free_port()
    root = tmp_path / "hub"

    async with hub(root, proxy_port=proxy_port) as tools:
        await tools.invoke("register_package_source", {"path": str(FIXTURES)})
        await tools.invoke("install_app", {"app_name": "vibepy-second"})
        started = await tools.invoke("start_app", {"app_name": "vibepy-second", "secrets": {}})
        assert isinstance(started, RunningApp)
        assert started.diagnostic is None

        async with traefik(
            root / "traefik.yml",
            port=proxy_port,
            host="vibepy-second.localhost",
            path="/home",
        ):
            opened = await first_frame(proxy_port, host="vibepy-second.localhost", path=SOCKET_IO)

    # engine.io's OPEN packet, which the server sends of its own accord once the
    # socket is up: the upgrade was carried, and so was what followed it.
    assert opened.startswith(b"0{")
    assert b'"sid"' in opened


async def test_two_apps_are_served_through_one_configuration(tmp_path: Path) -> None:
    """The acceptance criterion: one configuration, two Apps, at once.

    The configuration is read before either App exists and compared after both
    are running: what changes as Apps arrive is the routing files beside it, not
    this.
    """
    proxy_port = free_port()
    root = tmp_path / "hub"

    async with hub(root, proxy_port=proxy_port) as tools:
        config = root / "traefik.yml"
        written = config.read_text(encoding="utf-8")

        await tools.invoke("register_package_source", {"path": str(EXAMPLES)})
        await tools.invoke("register_package_source", {"path": str(FIXTURES)})

        await tools.invoke("install_app", {"app_name": "vibepy-todo"})
        await tools.invoke(
            "configure_app",
            {
                "app_name": "vibepy-todo",
                "values": {"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
            },
        )
        await tools.invoke("install_app", {"app_name": "vibepy-second"})

        for name in ("vibepy-todo", "vibepy-second"):
            started = await tools.invoke("start_app", {"app_name": name, "secrets": {}})
            assert isinstance(started, RunningApp)
            assert started.diagnostic is None

        async with traefik(config, port=proxy_port, host="vibepy-todo.localhost", path="/todos"):
            todo = await served_body(proxy_port, host="vibepy-todo.localhost", path="/todos")
            second = await served_body(proxy_port, host="vibepy-second.localhost", path="/home")

        assert config.read_text(encoding="utf-8") == written

    # Each host reached its own App. Two statuses would not say that: two
    # requests answered by one App are also two 200s, and the criterion is that
    # both Apps are served, not that both requests succeeded.
    assert "todos" in todo.lower()
    assert "second-app" in second
    # And neither answer came from the other App, which is what would happen if
    # one route shadowed the other and both requests still returned 200.
    assert "second-app" not in todo
    assert "todos" not in second.lower()
