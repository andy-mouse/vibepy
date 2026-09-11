"""What more than one Studio test needs."""

import asyncio
import base64
import os
import shutil
import socket
import subprocess
import sys
import tomllib
import zipfile
from collections.abc import AsyncGenerator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from urllib.request import Request, urlopen

from vibepy_core.app.composition import tool_runtime_for
from vibepy_core.tool import ToolRuntime
from vibepy_studio.consumption.internals import StudioDeps
from vibepy_studio.entry import APP, STUDIO_APP

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "fixtures"
"""Every distribution a test installs. There is no other kind here.

An example is a documentation artifact and this repository has no document that
walks through one, so what was `examples/` was a fixture wearing a sample's
name -- and paying a sample's costs. When a reader arrives, an example is
derived from what is true then.
"""

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


def studio(
    root: Path, /, *, proxy_port: int = 8080
) -> AbstractAsyncContextManager[ToolRuntime[StudioDeps]]:
    """One Studio window over a temporary root, published at one proxy port."""
    return tool_runtime_for(
        STUDIO_APP, APP.lifespan, config={"root": str(root), "proxy_port": proxy_port}
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
    element -- and the configuration this runs against is the one Studio
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


FIXTURE_PACKAGES = ("vibepy-notes", "vibepy-todo", "vibepy-timer")


def build_wheelhouse(out: Path, /) -> None:
    """Build the framework and every fixture App into one folder of wheels.

    `uv build --wheel` from the workspace root, once for the framework and once per
    fixture member, so the folder is what an in-house wheelhouse is: the Apps and
    the framework they depend on, resolvable with `--find-links` and no index.
    """
    out.mkdir(parents=True, exist_ok=True)
    _build(["uv", "build", "--wheel", "--no-build-logs", "-o", str(out)])
    for package in FIXTURE_PACKAGES:
        _build(["uv", "build", "--wheel", "--no-build-logs", "--package", package, "-o", str(out)])


def bumped_fixture_wheel(fixture: Path, out: Path, /, *, version: str) -> Path:
    """Build one fixture App at another version, for a test whose subject is updating.

    The source tree is copied so the fixture in the repository is never edited, and
    `[tool.uv.sources]` is dropped from the copy because it names a workspace the
    copy is no longer in. The wheel's dependencies still say `vibepy-core`, which the
    wheelhouse resolves.
    """
    staged = out / f"{fixture.name}-{version}-src"
    shutil.copytree(fixture, staged, ignore=shutil.ignore_patterns("__pycache__", "dist"))
    project = staged / "pyproject.toml"
    document = tomllib.loads(project.read_text(encoding="utf-8"))
    lines = [
        line
        for line in project.read_text(encoding="utf-8").splitlines()
        if not line.startswith("[tool.uv.sources]") and not line.startswith("vibepy-core = {")
    ]
    lines = [f'version = "{version}"' if line.startswith("version = ") else line for line in lines]
    project.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _build(["uv", "build", "--wheel", "--no-build-logs", str(staged), "-o", str(out)])
    name = str(document["project"]["name"]).replace("-", "_")
    return next(out.glob(f"{name}-{version}-*.whl"))


def _build(command: Sequence[str], /) -> None:
    subprocess.run(command, cwd=REPO, check=True, capture_output=True)


def write_wheel(folder: Path, /, *, name: str, version: str, declares: bool) -> Path:
    """A wheel that installs nothing, shaped as the specification shapes one.

    Enough for what reads a wheelhouse: a parseable file name and a `.dist-info`
    with `entry_points.txt` when `declares`. Installing it is not its purpose.
    """
    folder.mkdir(parents=True, exist_ok=True)
    normalized = name.replace("-", "_").lower()
    info = f"{normalized}-{version}.dist-info"
    path = folder / f"{normalized}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{info}/METADATA", f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
        )
        archive.writestr(
            f"{info}/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        )
        if declares:
            archive.writestr(f"{info}/entry_points.txt", "[vibepy.apps]\ndemo = demo.entry:APP\n")
        archive.writestr(f"{info}/RECORD", "")
    return path
