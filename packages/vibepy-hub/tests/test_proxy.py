"""What a Traefik in front of an App does and does not carry.

The proxy is adopted whole (ADR-031), so what is tested here is the seam: a
NiceGUI Page needs a WebSocket, and Traefik's documentation does not say it
carries one. This file answers that from the running pair rather than from a
document.
"""

import asyncio
import json
import sys
from pathlib import Path

from tests_support import first_frame, free_port, traefik

SOCKET_IO = "/_nicegui_ws/socket.io/?EIO=4&transport=websocket"
"""Where NiceGUI mounts socket.io (`nicegui/nicegui.py`, `app.mount('/_nicegui_ws/', ...)`)."""


def install_configuration(root: Path, *, port: int) -> Path:
    """The half of the proxy's configuration that does not change.

    Scaffolding: Task 4 of `docs/milestones/R1/plan.md` teaches the Hub to write
    this document, and this helper goes when it does.
    """
    routes = root / "routes"
    routes.mkdir(parents=True)
    config = root / "traefik.yml"
    config.write_text(
        f'entryPoints:\n  web:\n    address: ":{port}"\n'
        f"providers:\n  file:\n    directory: {routes}\n    watch: true\n",
        encoding="utf-8",
    )
    return config


def route(root: Path, *, host: str, port: int) -> None:
    """One App's routing configuration, written where the provider watches."""
    (root / "routes" / "one.yml").write_text(
        "http:\n"
        "  routers:\n"
        "    one:\n"
        f'      rule: "Host(`{host}`)"\n'
        "      service: one\n"
        "  services:\n"
        "    one:\n"
        "      loadBalancer:\n"
        "        servers:\n"
        f'          - url: "http://127.0.0.1:{port}"\n',
        encoding="utf-8",
    )


async def test_a_page_s_websocket_survives_the_proxy(tmp_path: Path) -> None:
    app_port, proxy_port = free_port(), free_port()
    config = install_configuration(tmp_path, port=proxy_port)
    route(tmp_path, host="todo-app.localhost", port=app_port)

    served = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "vibepy_core.serve",
        "todo-app",
        "--port",
        str(app_port),
        stdin=asyncio.subprocess.PIPE,
    )
    assert served.stdin is not None
    served.stdin.write(json.dumps({"db_path": str(tmp_path / "todo.json"), "db_key": "k"}).encode())
    await served.stdin.drain()
    served.stdin.close()
    try:
        async with traefik(config, port=proxy_port, host="todo-app.localhost", path="/todos"):
            frame = await first_frame(proxy_port, host="todo-app.localhost", path=SOCKET_IO)
    finally:
        served.terminate()
        await served.wait()

    # An unmasked text frame carrying engine.io's OPEN packet: the upgrade was
    # carried, and so was what the server sent after it.
    assert frame[0] == 0x81
    assert frame[2:4] == b"0{"
