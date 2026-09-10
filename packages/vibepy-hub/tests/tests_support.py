"""What more than one Hub test needs."""

import asyncio
import base64
import os
import socket
import sys
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from urllib.request import Request, urlopen

from vibepy_core.app.composition import tool_runtime_for
from vibepy_core.tool import ToolRuntime
from vibepy_hub.entry import APP, HUB_APP
from vibepy_hub.internals import HubDeps

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "examples"
FIXTURES = REPO / "fixtures"
"""Distributions that exist to be installed by a test. Not product surface."""

TRAEFIK_VERSION = "v3.7.12"
"""Pinned beside `scripts/fetch_traefik.py`, which fetches this exact binary."""

TRAEFIK = (
    REPO
    / ".tools"
    / (
        f"traefik-{TRAEFIK_VERSION}.exe"
        if sys.platform == "win32"
        else f"traefik-{TRAEFIK_VERSION}"
    )
)
"""The proxy `make install` fetched. Required: a skipped test cannot fail."""


def hub(
    root: Path, /, *, proxy_port: int = 8080
) -> AbstractAsyncContextManager[ToolRuntime[HubDeps]]:
    """One Hub window over a temporary root, published at one proxy port."""
    return tool_runtime_for(
        HUB_APP, APP.lifespan, config={"root": str(root), "proxy_port": proxy_port}
    )


def free_port() -> int:
    """A port nothing is listening on, for a server this test runs itself."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@asynccontextmanager
async def traefik(config: Path, *, port: int, host: str, path: str) -> AsyncGenerator[None]:
    """Traefik running against one configuration file, until it serves `path`.

    Traefik publishes no readiness signal, and this is its own position rather
    than something unfound: `/ping` "is expected to answer 200 OK before all
    dynamic configuration is loaded", and the request for an endpoint that does
    not is open and unassigned
    (<https://github.com/traefik/traefik/issues/10458>). Its API does answer
    which routers are loaded, but must be enabled, and the documentation says
    enabling it "is not recommended" because it exposes every configuration
    element -- and the configuration this runs against is the one the Hub
    writes, so enabling it would mean shaping a product's output for a test.

    So readiness is the whole fact the test depends on, asked of the thing
    itself: a request this test will actually make, answered by the App the
    route names. An open socket does not say it, because the entry point opens
    first; a non-`404` does not either, because an App answers `404` for a path
    it does not serve.
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
        return await asyncio.wait_for(_payload(reader), timeout=30)
    finally:
        writer.close()


async def _payload(reader: asyncio.StreamReader, /) -> bytes:
    """One server frame's payload, read by the length the frame declares.

    A server frame is unmasked, and its second byte carries a 7-bit length that
    escapes into two or eight further bytes above 125. Reading a fixed slice
    instead would turn a handshake that grew by one field into a failure that
    reads like a proxy defect.
    """
    first, length = await reader.readexactly(2)
    if first != 0x81:
        raise AssertionError(f"expected an unmasked text frame, got {first:#x}")
    if length == 126:
        length = int.from_bytes(await reader.readexactly(2), "big")
    elif length == 127:
        length = int.from_bytes(await reader.readexactly(8), "big")
    return await reader.readexactly(length)


async def served_body(port: int, *, host: str, path: str) -> str:
    """What the App behind this hostname answers with.

    A body rather than a status, because a status cannot tell two Apps apart:
    two requests answered by one App are also two 200s.

    The `Host` header is sent and never resolved, which is what the proxy routes
    on and what keeps this independent of whether the platform's resolver knows
    `.localhost` -- RFC 6761 makes that a SHOULD, and browsers rather than
    system resolvers are what implement it.
    """
    return await asyncio.to_thread(_body, f"http://127.0.0.1:{port}{path}", host)


def _body(url: str, host: str, /) -> str:
    with urlopen(Request(url, headers={"Host": host}), timeout=30) as answer:
        return answer.read().decode(errors="replace")


def write_project(folder: Path, *, name: str, declares: bool) -> None:
    """A project file like the one an App's own repository carries."""
    folder.mkdir(parents=True)
    declaration = '\n[project.entry-points."vibepy.apps"]\ndemo = "demo.entry:APP"\n'
    (folder / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "1.2.3"\n' + (declaration if declares else ""),
        encoding="utf-8",
    )
