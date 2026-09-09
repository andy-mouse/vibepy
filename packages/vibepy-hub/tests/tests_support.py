"""What more than one Hub test needs."""

import asyncio
import base64
import os
import socket
import sys
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from urllib.request import urlopen

from vibepy_core.app.composition import tool_runtime_for
from vibepy_core.tool import ToolRuntime
from vibepy_hub.entry import APP, HUB_APP
from vibepy_hub.internals import HubDeps

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "examples"

TRAEFIK = REPO / ".tools" / ("traefik.exe" if sys.platform == "win32" else "traefik")
"""The proxy `make install` fetched. Required: a skipped test cannot fail."""


def hub(root: Path, /) -> AbstractAsyncContextManager[ToolRuntime[HubDeps]]:
    """One Hub window over a temporary root."""
    return tool_runtime_for(HUB_APP, APP.lifespan, config={"root": str(root)})


def free_port() -> int:
    """A port nothing is listening on, for a server this test runs itself."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@asynccontextmanager
async def traefik(config: Path, *, port: int, host: str, path: str) -> AsyncGenerator[None]:
    """Traefik running against one configuration file, until it serves `path`.

    Waiting for the entry point to accept a connection is not enough: Traefik
    opens its entry points before it has read its routing configuration, and a
    request arriving in between is answered `404` by a proxy that is working
    correctly. Nor is a non-`404` enough, because an App may answer `404` for a
    path it does not serve, and the two are indistinguishable from out here.

    So readiness is the whole fact the test depends on: a request this test will
    actually make is answered by the App the route names.
    """
    if not TRAEFIK.exists():
        raise AssertionError(f"{TRAEFIK} is missing; run `make install`")
    process = await asyncio.create_subprocess_exec(
        str(TRAEFIK), f"--configFile={config}", stdout=asyncio.subprocess.DEVNULL
    )
    try:
        await _serving(port, host, path, process)
        yield
    finally:
        process.terminate()
        await process.wait()


async def _serving(port: int, host: str, path: str, process: asyncio.subprocess.Process, /) -> None:
    """Wait until the proxy answers for this host and path out of the App."""
    for _ in range(300):
        if process.returncode is not None:
            raise AssertionError(f"traefik exited with {process.returncode}")
        if await _proxy_status(port, host, path) == 200:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"traefik did not serve {host}{path} on {port}")


async def _proxy_status(port: int, host: str, path: str, /) -> int | None:
    """The status the proxy gives, or nothing while it will not talk."""
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
    except OSError:
        return None
    try:
        writer.write(f"GET {path} HTTP/1.0\r\nHost: {host}\r\n\r\n".encode())
        await writer.drain()
        head = await asyncio.wait_for(reader.readuntil(b"\r\n"), timeout=30)
    except (OSError, TimeoutError, asyncio.IncompleteReadError):
        return None
    finally:
        writer.close()
    return int(head.split()[1])


async def first_frame(port: int, *, host: str, path: str) -> bytes:
    """The first WebSocket frame a server sends, read through the proxy.

    A raw handshake rather than a client library: what is under test is whether
    the proxy carries the upgrade and the frames after it, and that is exactly
    the HTTP/1.1 101 and the bytes that follow.
    """
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        key = base64.b64encode(os.urandom(16)).decode()
        writer.write(
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        await writer.drain()
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=30)
        if not head.startswith(b"HTTP/1.1 101"):
            raise AssertionError(f"the proxy refused the upgrade: {head!r}")
        return await asyncio.wait_for(reader.read(64), timeout=30)
    finally:
        writer.close()


async def http_status(url: str, /) -> int:
    """The status a running App answers with.

    `urlopen` blocks, so it runs in a thread rather than on the loop the test
    shares with the Hub.
    """
    return await asyncio.to_thread(_status, url)


def _status(url: str, /) -> int:
    with urlopen(url, timeout=30) as answer:
        return int(answer.status)


def write_project(folder: Path, *, name: str, declares: bool) -> None:
    """A project file like the one an App's own repository carries."""
    folder.mkdir(parents=True)
    declaration = '\n[project.entry-points."vibepy.apps"]\ndemo = "demo.entry:APP"\n'
    (folder / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "1.2.3"\n' + (declaration if declares else ""),
        encoding="utf-8",
    )
