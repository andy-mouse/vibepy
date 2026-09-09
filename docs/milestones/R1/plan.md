# R1 - One address per App implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every installed App a stable address of its own, served through one Traefik
configuration the Hub writes and does not own.

**Architecture:** An App's address is decided at install, not at start. The Hub allocates a port
at or above 9000, stores it in its state, and writes one Traefik routing file per App into a
directory the proxy watches. Every answer the Hub gives names `http://<app>.localhost:<proxy
port>` — the proxy's address — and the child's own port stops leaving the Hub. The Hub's whole
knowledge of Traefik is one module, `internals/routing.py`.

**Tech Stack:** Python 3.12, pydantic, PyYAML (new, for the Hub), `uv` for environments, Traefik
v3.7.12 as a fetched binary, pytest with `asyncio_mode = auto`, ruff + pyright strict.

## Global Constraints

- The spec is `docs/milestones/R1/spec.md`. Its acceptance criteria are the tests.
- The branch is `r1-one-address-per-app`, already cut from `main`. Do not push.
- `make lint typecheck test` must pass at the end of every task. 229 tests pass at the start.
- Blocking calls inside async code are wrapped in `asyncio.to_thread`.
- `Any` and `cast` are not acceptable in the public API. Filesystem paths are `pathlib.Path`.
- Optional and configuration parameters are keyword-only.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- Tests verify public contracts. This stage adds no departure. `packages/vibepy-hub/tests/
  test_processes.py` is the departure CR2 already stated and remains the only one; Task 5 moves
  two assertions into it because they were always claims about `Processes` rather than about a
  Tool.
- Traefik is required, never skipped. `make install` fetches it.
- Run tests with `uv run pytest`. The Hub's tests live in `packages/vibepy-hub/tests/`.
- Do not touch `docs/roadmap.md`.

---

### Task 1: A WebSocket survives the proxy

The gate. Traefik's documentation does not state that it proxies WebSocket connections, and a
NiceGUI Page does not work without one. If this task fails, stop and report: the choice of proxy
is invalid and ADR-031 has to be rewritten before anything else is built.

Nothing in this task touches the Hub. It starts one App with the `serve` command, puts a
hand-written Traefik configuration in front of it, and proves a socket opens and carries a frame
through it.

The two helpers that write that configuration are scaffolding with an end date. Task 4 teaches
the Hub to write the same two documents, and Task 6 deletes these and points this test at what
the Hub wrote: one document must not have two writers at the end of the stage.

**Files:**
- Create: `scripts/fetch_traefik.py`
- Modify: `Makefile:3-5`
- Modify: `.gitignore`
- Modify: `packages/vibepy-hub/tests/tests_support.py`
- Test: `packages/vibepy-hub/tests/test_proxy.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `tests_support.TRAEFIK: Path`, `tests_support.free_port() -> int`,
  `tests_support.traefik(config: Path, *, port: int, host: str, path: str)` — an async context
  manager yielding once a request for `host` and `path` is answered `200` through the proxy, and
  `tests_support.first_frame(port: int, *, host: str, path: str) -> bytes` — the first WebSocket
  frame a server sends through the proxy.

Readiness is that whole fact rather than an open socket. Traefik opens its entry points before
it has read its routing configuration, so a request in between is answered `404` by a proxy that
is working correctly, and an App answers `404` for a path it does not serve, so a non-`404` does
not separate the two from outside either.

Traefik offers nothing better, by its own account: `/ping` answers 200 before the dynamic
configuration is loaded, and the request for an endpoint that does not is open and unassigned
(<https://github.com/traefik/traefik/issues/10458>). Its API reports which routers are loaded but
must be enabled, and the documentation says enabling it is not recommended because it exposes
every configuration element — and from Task 6 the configuration under test is the one the Hub
writes, so enabling it would shape a product's output for a test.

- [ ] **Step 1: Write the fetch script**

Create `scripts/fetch_traefik.py`:

```python
"""Fetch the pinned Traefik binary this repository's tests run against.

Traefik ships one static binary per platform, so the proxy the tests use is the
proxy a user runs. `make install` puts it in `.tools/`, which is not tracked.
"""

import hashlib
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "v3.7.12"
RELEASE = f"https://github.com/traefik/traefik/releases/download/{VERSION}"
TOOLS = Path(__file__).resolve().parents[1] / ".tools"


def asset() -> tuple[str, str]:
    """The archive for this platform, and the name of the binary inside it."""
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
    if sys.platform == "win32":
        return f"traefik_{VERSION}_windows_{arch}.zip", "traefik.exe"
    if sys.platform == "darwin":
        return f"traefik_{VERSION}_darwin_{arch}.tar.gz", "traefik"
    return f"traefik_{VERSION}_linux_{arch}.tar.gz", "traefik"


def expected(archive: str) -> str:
    """The digest the release publishes for this archive."""
    with urllib.request.urlopen(f"{RELEASE}/traefik_{VERSION}_checksums.txt") as answer:
        published = answer.read().decode()
    for line in published.splitlines():
        digest, _, name = line.partition("  ")
        if name.strip() == archive:
            return digest
    raise SystemExit(f"{archive} is not in the published checksums")


def main() -> None:
    archive, binary = asset()
    target = TOOLS / binary
    if target.exists():
        return
    TOOLS.mkdir(parents=True, exist_ok=True)
    downloaded = TOOLS / archive
    urllib.request.urlretrieve(f"{RELEASE}/{archive}", downloaded)
    got = hashlib.sha256(downloaded.read_bytes()).hexdigest()
    if got != expected(archive):
        downloaded.unlink()
        raise SystemExit(f"{archive} does not match its published digest")
    if archive.endswith(".zip"):
        with zipfile.ZipFile(downloaded) as held:
            held.extract(binary, TOOLS)
    else:
        with tarfile.open(downloaded) as held:
            held.extract(binary, TOOLS, filter="data")
    downloaded.unlink()
    target.chmod(target.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Wire it into `make install` and ignore what it writes**

In `Makefile`, the `install` target becomes:

```make
install:
	uv sync
	uv run pre-commit install
	uv run python scripts/fetch_traefik.py
```

Append one line to `.gitignore`:

```
.tools/
```

- [ ] **Step 3: Run it**

Run: `uv run python scripts/fetch_traefik.py && .tools/traefik version`
Expected: a version line naming `3.7.12`. On Windows the binary is `.tools/traefik.exe`.

- [ ] **Step 4: Add the proxy helpers to `tests_support`**

Append to `packages/vibepy-hub/tests/tests_support.py`, and add `base64`, `os`, `socket`, `sys`,
`AsyncGenerator` and `asynccontextmanager` to its imports:

```python
TRAEFIK = REPO / ".tools" / ("traefik.exe" if sys.platform == "win32" else "traefik")
"""The proxy `make install` fetched. Required: a skipped test cannot fail."""


def free_port() -> int:
    """A port nothing is listening on, for a server this test runs itself."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@asynccontextmanager
async def traefik(config: Path, *, port: int) -> AsyncGenerator[None]:
    """Traefik running against one configuration file, until it answers."""
    if not TRAEFIK.exists():
        raise AssertionError(f"{TRAEFIK} is missing; run `make install`")
    process = await asyncio.create_subprocess_exec(
        str(TRAEFIK), f"--configFile={config}", stdout=asyncio.subprocess.DEVNULL
    )
    try:
        await _answers(port, process)
        yield
    finally:
        process.terminate()
        await process.wait()


async def _answers(port: int, process: asyncio.subprocess.Process, /) -> None:
    """Wait until the proxy accepts a connection, or say that it never will."""
    for _ in range(300):
        if process.returncode is not None:
            raise AssertionError(f"traefik exited with {process.returncode}")
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.1)
            continue
        writer.close()
        return
    raise AssertionError(f"traefik did not listen on {port}")


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
```

- [ ] **Step 5: Write the failing test**

Create `packages/vibepy-hub/tests/test_proxy.py`:

```python
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
    """The half of the proxy's configuration that does not change."""
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
    served.stdin.write(
        json.dumps({"db_path": str(tmp_path / "todo.json"), "db_key": "k"}).encode()
    )
    await served.stdin.drain()
    served.stdin.close()
    try:
        async with traefik(config, port=proxy_port):
            frame = await first_frame(
                proxy_port, host="todo-app.localhost", path=SOCKET_IO
            )
    finally:
        served.terminate()
        await served.wait()

    # An unmasked text frame carrying engine.io's OPEN packet: the upgrade was
    # carried, and so was what the server sent after it.
    assert frame[0] == 0x81
    assert frame[2:4] == b"0{"
```

- [ ] **Step 6: Run the test**

Run: `uv run pytest packages/vibepy-hub/tests/test_proxy.py -v`
Expected: PASS. A failure here is the gate: report it and stop rather than working around it.

- [ ] **Step 7: Run the whole suite and commit**

Run: `make lint typecheck test`
Expected: 230 tests pass.

```bash
git add scripts/fetch_traefik.py Makefile .gitignore packages/vibepy-hub/tests/tests_support.py packages/vibepy-hub/tests/test_proxy.py
git commit -m "Prove a Page's WebSocket survives the proxy"
```

---

### Task 2: A port per installed App, and an address built from it

**Files:**
- Create: `packages/vibepy-hub/src/vibepy_hub/internals/routing.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/__init__.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/state.py:27-32`
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/deps.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/entry.py:22-46`
- Test: `packages/vibepy-hub/tests/test_addresses.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `routing.PORT_BASE: int`, `routing.allocate(taken: Mapping[str, int], app_name: str,
  /) -> int`, `routing.address(app_name: str, port: int, /) -> str`, `HubState.ports: dict[str,
  int]`, `HubConfig.proxy_port: int`, `HubDeps.proxy_port: int`.

- [ ] **Step 1: Write the failing test**

Create `packages/vibepy-hub/tests/test_addresses.py`:

```python
"""An App's address: allocated once, derived from what is stored.

The port belongs to the installation and the hostname is the App's canonical
name (ADR-028), so the address is built rather than kept. See
`docs/decisions/ADR-031-the-proxy-is-traefik.md`.
"""

from vibepy_hub.internals.routing import PORT_BASE, address, allocate


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/vibepy-hub/tests/test_addresses.py -v`
Expected: FAIL — `ModuleNotFoundError: vibepy_hub.internals.routing`.

- [ ] **Step 3: Write the module**

Create `packages/vibepy-hub/src/vibepy_hub/internals/routing.py`:

```python
"""Where an App is reached, and what the proxy in front of it is told.

This is the Hub's whole knowledge of Traefik. A different proxy replaces this
module and nothing else. The Hub writes files here and never signals, starts or
observes the proxy: see
`docs/decisions/ADR-031-the-proxy-is-traefik.md`.
"""

import logging
from collections.abc import Mapping

logger = logging.getLogger(__name__)

PORT_BASE = 9000
"""The lowest port an App is given.

Above the range a user's own servers habitually take, and below the ephemeral
range an operating system allocates from, so a stored port and an incidental one
are unlikely to meet.
"""


def allocate(taken: Mapping[str, int], app_name: str, /) -> int:
    """The port this App holds, or the lowest free one at or above the base.

    An App that already holds a port keeps it, so reinstalling does not move an
    address a user has kept.
    """
    held = taken.get(app_name)
    if held is not None:
        return held
    used = set(taken.values())
    port = PORT_BASE
    while port in used:
        port += 1
    return port


def address(app_name: str, proxy_port: int, /) -> str:
    """Where a caller reaches this App.

    The hostname is the App's canonical distribution name (ADR-028), which the
    normalization specification leaves as lowercase letters, digits and `-`,
    beginning and ending with a letter or digit. That is a DNS label as written,
    so nothing here escapes or maps it.
    """
    return f"http://{app_name}.localhost:{proxy_port}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/vibepy-hub/tests/test_addresses.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Give the state a place to hold ports, and the window a proxy port**

In `internals/state.py`, `HubState` gains one field:

```python
class HubState(BaseModel):
    """Everything the Hub remembers between windows."""

    sources: list[Path] = []
    config: dict[str, dict[str, object]] = {}
    ports: dict[str, int] = {}
    """The port each installed App serves on, allocated when it was installed."""
```

In `internals/deps.py`, `HubDeps` gains the port it publishes:

```python
@dataclass
class HubDeps:
    """What one Hub window owns."""

    root: Path
    processes: Processes
    proxy_port: int
    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
```

In `entry.py`, `HubConfig` declares it and the lifespan passes it on:

```python
class HubConfig(BaseModel):
    """What the Hub requires of its host.

    The root is declared rather than assumed, so a test supplies a temporary
    directory and two Hubs never share one. `proxy_port` is declared for the
    same reason and one more: it is part of every address the Hub answers with,
    and a Hub that assumed it would publish addresses reaching nothing, or
    something else, without ever being told. See
    `docs/decisions/ADR-031-the-proxy-is-traefik.md`.
    """

    root: Path
    proxy_port: int = 8080
```

and, inside `hub_lifespan`:

```python
        yield HubDeps(root=config.root, processes=processes, proxy_port=config.proxy_port)
```

Export the two functions from `internals/__init__.py`: add
`from vibepy_hub.internals.routing import address, allocate` and put `"address"` and
`"allocate"` in `__all__`, in alphabetical order.

- [ ] **Step 6: Let a test choose the port**

In `tests_support.py`, `hub` takes the proxy port a test runs its own Traefik on:

```python
def hub(root: Path, /, *, proxy_port: int = 8080) -> AbstractAsyncContextManager[ToolRuntime[HubDeps]]:
    """One Hub window over a temporary root."""
    return tool_runtime_for(
        HUB_APP, APP.lifespan, config={"root": str(root), "proxy_port": proxy_port}
    )
```

- [ ] **Step 7: Run the suite and commit**

Run: `make lint typecheck test`
Expected: 235 tests pass. Nothing else changed behaviour yet.

```bash
git add packages/vibepy-hub/src/vibepy_hub packages/vibepy-hub/tests
git commit -m "Give an App a port of its own and an address built from it"
```

---

### Task 3: Install allocates, remove releases, and every answer is an address

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/installation.py:60-115` (`_installed`),
  `:117-200` (`install_app`), `:236-258` (`remove_app`)
- Test: `packages/vibepy-hub/tests/test_addresses.py`

**Interfaces:**
- Consumes: `routing.allocate`, `routing.address`, `HubState.ports`, `HubDeps.proxy_port`.
- Produces: `AppRow.url` and `Installation.app.url` carrying the App's address whenever the App
  is installed.

- [ ] **Step 1: Write the failing test**

Append to `packages/vibepy-hub/tests/test_addresses.py` (and add the imports
`from pathlib import Path`, `from tests_support import EXAMPLES, hub`,
`from vibepy_hub.internals import read_state`,
`from vibepy_hub.models import AppListing, Installation`):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/vibepy-hub/tests/test_addresses.py -v`
Expected: FAIL — `installed.app.url` is `None`, and `read_state(root).ports` is empty.

- [ ] **Step 3: Allocate at install and release at remove**

In `tools/installation.py`, extend the imports from `vibepy_hub.internals` with `address`,
`allocate` and `HubState` (already imported), then, in `install_app`, immediately before the
final `return`:

```python
    def hold(state: HubState) -> HubState:
        return HubState(
            sources=state.sources,
            config=state.config,
            ports={**state.ports, payload.app_name: allocate(state.ports, payload.app_name)},
        )

    port = (await update_state(deps, hold)).ports[payload.app_name]
    return Installation(
        app=AppRow(
            app_name=payload.app_name,
            name=facts.name,
            version=facts.version,
            state="installed",
            url=address(payload.app_name, deps.proxy_port),
            has_pages=facts.has_pages,
        )
    )
```

`port` is bound here because Task 4 writes the route with it; until then it is used by the same
statement that allocates it.

In `remove_app`, `forget` drops the port with the configuration:

```python
    def forget(state: HubState) -> HubState:
        return HubState(
            sources=state.sources,
            config={
                name: values for name, values in state.config.items() if name != payload.app_name
            },
            ports={name: port for name, port in state.ports.items() if name != payload.app_name},
        )
```

- [ ] **Step 4: Answer with the address in the listing**

In `_installed`, the row's URL stops coming from the child. Replace the two lines that read
`port = deps.processes.running(env.name)` and build `url=` with:

```python
        held_port = (await read_state(deps.root)).ports.get(env.name)
        rows[env.name] = AppRow(
            app_name=env.name,
            name=facts.name,
            version=facts.version,
            state="running" if deps.processes.running(env.name) else "installed",
            url=None if held_port is None else address(env.name, deps.proxy_port),
```

`Processes.running` still returns a port at this point; Task 5 narrows it to `bool` and the
truth test above is already written for that.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest packages/vibepy-hub/tests/test_addresses.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 6: Run the suite**

Run: `make lint typecheck test`
Expected: `test_runtime.py::test_an_installed_app_starts_answers_and_stops` fails at
`http_status(f"{started.url}/todos")` — the address now names a proxy that is not running. Task 5
rewrites that test. Everything else passes. Do not fix it here.

- [ ] **Step 7: Commit**

```bash
git add packages/vibepy-hub/src/vibepy_hub/tools/installation.py packages/vibepy-hub/tests/test_addresses.py
git commit -m "Allocate an App's port when it is installed, and answer with its address"
```

---

### Task 4: The Hub writes both halves of the proxy's configuration

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/routing.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/__init__.py`
- Modify: `packages/vibepy-hub/src/vibepy_hub/entry.py:33-46` (`hub_lifespan`)
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/installation.py` (`install_app`,
  `remove_app`)
- Modify: `packages/vibepy-hub/pyproject.toml` (dependencies)
- Test: `packages/vibepy-hub/tests/test_addresses.py`

**Interfaces:**
- Consumes: `routing.address`, `routing.allocate`, `HubDeps.proxy_port`.
- Produces: `routing.write_install_config(root: Path, *, proxy_port: int) -> None`,
  `routing.write_route(root: Path, app_name: str, /, *, port: int) -> None`,
  `routing.remove_route(root: Path, app_name: str, /) -> None`, and the two paths
  `<root>/traefik.yml` and `<root>/routes/<app>.yml`.

- [ ] **Step 1: Declare the YAML dependency**

The routing files are YAML because that is what Traefik's file provider reads. Serializing YAML
is a solved problem and P1 delegates it rather than formatting strings by hand. In
`packages/vibepy-hub/pyproject.toml`, add to `[project].dependencies`:

```toml
    "pyyaml>=6.0",
```

Run: `uv sync`

- [ ] **Step 2: Write the failing test**

Append to `packages/vibepy-hub/tests/test_addresses.py` (adding `import yaml`):

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest packages/vibepy-hub/tests/test_addresses.py -v`
Expected: FAIL — `FileNotFoundError` on `traefik.yml`.

- [ ] **Step 4: Write the three writers**

Append to `internals/routing.py` (adding `asyncio`, `os`, `Path` and `yaml` to its imports):

```python
ROUTES = "routes"
INSTALL_CONFIG = "traefik.yml"


async def write_install_config(root: Path, /, *, proxy_port: int) -> None:
    """The half of the proxy's configuration that does not follow an App.

    Written when a window opens rather than when an App arrives, because it says
    only where the proxy listens and where it watches. Traefik calls this the
    install configuration and the files below it the routing configuration; only
    the second changes, and it is hot-reloaded
    (<https://doc.traefik.io/traefik/getting-started/configuration-overview/>).
    """
    await asyncio.to_thread(_write_install_config, root, proxy_port)


def _write_install_config(root: Path, proxy_port: int, /) -> None:
    (root / ROUTES).mkdir(parents=True, exist_ok=True)
    _replace(
        root / INSTALL_CONFIG,
        {
            "entryPoints": {"web": {"address": f":{proxy_port}"}},
            "providers": {"file": {"directory": str(root / ROUTES), "watch": True}},
        },
    )


async def write_route(root: Path, app_name: str, /, *, port: int) -> None:
    """One App's routing configuration, where the provider is watching."""
    await asyncio.to_thread(_write_route, root, app_name, port)


def _write_route(root: Path, app_name: str, port: int, /) -> None:
    (root / ROUTES).mkdir(parents=True, exist_ok=True)
    _replace(
        root / ROUTES / f"{app_name}.yml",
        {
            "http": {
                "routers": {
                    app_name: {
                        "rule": f"Host(`{app_name}.localhost`)",
                        "service": app_name,
                    }
                },
                "services": {
                    app_name: {
                        "loadBalancer": {"servers": [{"url": f"http://127.0.0.1:{port}"}]}
                    }
                },
            }
        },
    )


async def remove_route(root: Path, app_name: str, /) -> None:
    """Withdraw one App's route, if it has one."""
    await asyncio.to_thread((root / ROUTES / f"{app_name}.yml").unlink, True)


def _replace(path: Path, document: object, /) -> None:
    """Write a routing file whole.

    The provider watches this directory, so a half-written file is a
    configuration it would read. `os.replace` overwrites the destination and the
    rename is atomic where POSIX requires it
    (<https://docs.python.org/3/library/os.html#os.replace>).
    """
    pending = path.with_suffix(".pending")
    pending.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    try:
        os.replace(pending, path)
    except OSError:
        pending.unlink(missing_ok=True)
        raise
```

Export `remove_route`, `write_install_config` and `write_route` from `internals/__init__.py`,
in `__all__` in alphabetical order.

- [ ] **Step 5: Call them**

In `entry.py`, `hub_lifespan` writes the install configuration after it makes the root:

```python
    await asyncio.to_thread(config.root.mkdir, parents=True, exist_ok=True)
    await write_install_config(config.root, proxy_port=config.proxy_port)
```

In `tools/installation.py`, `install_app` writes the route with the port it just allocated,
before it returns:

```python
    port = (await update_state(deps, hold)).ports[payload.app_name]
    await write_route(deps.root, payload.app_name, port=port)
```

and `remove_app` withdraws it, before `update_state`:

```python
    await remove_route(deps.root, payload.app_name)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest packages/vibepy-hub/tests/test_addresses.py -v`
Expected: PASS, 10 tests.

- [ ] **Step 7: Run the suite and commit**

Run: `make lint typecheck test`
Expected: the one `test_runtime.py` failure from Task 3 and nothing new.

```bash
git add packages/vibepy-hub
git commit -m "Have the Hub write the proxy's configuration without owning the proxy"
```

---

### Task 5: `free_port` is gone, and a start hands over a port

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/processes.py:137-150` (`free_port`),
  `:152-160` (`_Child`), `:171-178` (`running`), `:242-300` (`start`)
- Modify: `packages/vibepy-hub/src/vibepy_hub/tools/runtime.py:42-110`
- Modify: `packages/vibepy-hub/tests/test_processes.py` (two assertions move in)
- Modify: `packages/vibepy-hub/tests/test_runtime.py` (one test moves out)
- Test: `packages/vibepy-hub/tests/test_addresses.py`

**Interfaces:**
- Consumes: `routing.address`, `HubState.ports`, `HubDeps.proxy_port`.
- Produces: `Processes.start(*, app_name: str, interpreter: Path, config: Mapping[str, object],
  known_as: str, port: int) -> None` and `Processes.running(app_name: str, /) -> bool`.

- [ ] **Step 1: Write the failing test**

Append to `packages/vibepy-hub/tests/test_addresses.py` (adding `RunningApp` to the models
import):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/vibepy-hub/tests/test_addresses.py::test_an_address_outlives_a_run -v`
Expected: FAIL — `first.url` is `http://127.0.0.1:<some port>`, and `stopped.url` is `None`.

- [ ] **Step 3: Delete `free_port` and hand `start` its port**

In `internals/processes.py`, delete `free_port` entirely and drop `import socket`. `start` takes
the port keyword-only and returns nothing — replace its signature, the line `port = free_port()`
and its final `return port`:

```python
    async def start(
        self,
        *,
        app_name: str,
        interpreter: Path,
        config: Mapping[str, object],
        known_as: str,
        port: int,
    ) -> None:
        """Serve one App on the port it was given, handing it its configuration on stdin.
```

Delete the line `port = free_port()` from the body, and replace the final two lines of `start`:

```python
        child.answering = True
        logger.info("started %s on port %d", known_as, port)
```

Update the docstring's first line and remove the paragraph that explained choosing a port; the
Hub allocates it now, and `internals/routing.py` says why.

`running` answers the question its callers ask:

```python
    def running(self, app_name: str, /) -> bool:
        """Whether an App is serving. The port it serves on is the Hub's, not this window's."""
        child = self._held(app_name)
        return child is not None and child.answering
```

- [ ] **Step 4: Have the runtime Tools answer with addresses**

In `tools/runtime.py`, add `address` and `read_state` to the imports from `vibepy_hub.internals`.
`_refusal` gains the address, so that a refusal names the App's address like every other answer:

```python
def _refusal(
    app_name: str, code: str, message: str, /, *, category: ErrorCategory, url: str | None = None
) -> RunningApp:
    """An App that will not start or stop, and why."""
    return RunningApp(
        app_name=app_name,
        state="installed",
        url=url,
        diagnostic=Diagnostic(
            code=code, category=category, message=message, details={"app_name": app_name}
        ),
    )
```

In `start_app`, read the state once and use it for both the held configuration and the port:

```python
    state = await read_state(deps.root)
    held = state.config.get(payload.app_name, {})
    port = state.ports.get(payload.app_name)
    if port is None:
        return _refusal(
            payload.app_name,
            "hub.not_installed",
            f"{payload.app_name!r} is not installed",
            category=ErrorCategory.CALLER,
        )
    where = address(payload.app_name, deps.proxy_port)
    try:
        await deps.processes.start(
            app_name=facts.declared_name,
            interpreter=interpreter(environment(deps.root, payload.app_name)),
            config={**held, **payload.secrets},
            known_as=payload.app_name,
            port=port,
        )
```

The two `_refusal` calls in the `except` blocks and the `RunningApp` built from a child's report
all take `url=where`. The final line becomes:

```python
    return RunningApp(app_name=payload.app_name, url=where, state="running")
```

`stop_app` answers with the address too:

```python
async def stop_app(ctx: ToolContext[HubDeps], payload: AppName) -> RunningApp:
    """Stop an App this window started."""
    deps = ctx.dependencies
    port = (await read_state(deps.root)).ports.get(payload.app_name)
    where = None if port is None else address(payload.app_name, deps.proxy_port)
    if not await deps.processes.stop(payload.app_name):
        return _refusal(
            payload.app_name,
            "hub.not_running",
            f"{payload.app_name!r} is not running here",
            category=ErrorCategory.CALLER,
            url=where,
        )
    return RunningApp(app_name=payload.app_name, url=where, state="installed")
```

The `hub.not_installed` check that reads `facts` stays where it is; the port check above it is
the second half of the same fact and is reached only for an App whose facts exist but whose port
predates this stage.

- [ ] **Step 5: Put the process-ownership claims where their subject lives**

Two assertions in `test_runtime.py` reach the child's own port by slicing it out of `started.url`.
That was always a claim about `Processes` — that a window releases what it started, and that a
refused second start leaves no second child — asserted from a file whose subject is the Hub's
Tools. The address change is what exposes it. They move to
`packages/vibepy-hub/tests/test_processes.py`, which CR2 already named as the one place a fact
invisible to every Tool is asserted, and where the test chooses the port itself and so needs to
read nothing.

In `packages/vibepy-hub/tests/test_processes.py`, add `free_port` to the `tests_support` import,
give every existing `start(...)` call a `port=free_port()`, and change the two
`assert processes.running(...) is None` lines to `is False`. Then append:

```python
async def test_closing_a_window_releases_every_child(tmp_path: Path) -> None:
    """`aclose` is what `entry.py` promises: a window leaves no child behind."""
    processes = Processes(logs=tmp_path / "logs")
    port = free_port()
    await processes.start(
        app_name="todo-app",
        interpreter=Path(sys.executable),
        config={"db_path": str(tmp_path / "todo.json"), "db_key": "k"},
        known_as="todo-app",
        port=port,
    )
    assert processes.running("todo-app") is True

    await processes.aclose()

    assert processes.running("todo-app") is False
    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", port)


async def test_a_second_start_under_one_name_leaves_no_second_child(tmp_path: Path) -> None:
    """One name holds one child, and the start that was refused started nothing."""
    processes = Processes(logs=tmp_path / "logs")
    first, second = free_port(), free_port()
    config = {"db_path": str(tmp_path / "todo.json"), "db_key": "k"}
    await processes.start(
        app_name="todo-app",
        interpreter=Path(sys.executable),
        config=config,
        known_as="todo-app",
        port=first,
    )
    with pytest.raises(AlreadyStarted):
        await processes.start(
            app_name="todo-app",
            interpreter=Path(sys.executable),
            config=config,
            known_as="todo-app",
            port=second,
        )

    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", second)
    await processes.aclose()
```

Add `AlreadyStarted` to the `vibepy_hub.internals.processes` import.

In `packages/vibepy-hub/tests/test_runtime.py`, the same three tests keep their own subjects and
stop reaching for a port:

- `test_an_installed_app_starts_answers_and_stops`: delete the
  `assert await http_status(f"{started.url}/todos") == 200` line and the `http_status` import.
  Reaching an App through its address is `test_proxy.py`'s subject; this test's subject is the
  lifecycle, and `assert [row.url ...] == [started.url]` already states it.
- `test_an_app_whose_window_rejects_its_configuration_does_not_start`: `started.url` is no longer
  `None`, because the App is installed. Replace `assert started.url is None` with
  `assert started.state == "installed"`.
- `test_two_overlapping_starts_answer_once`: the two answers are told apart by their diagnostic
  rather than by a url. Replace the block from `assert [one.url is not None ...]` to the end of
  the test with:

```python
    assert [one.diagnostic is None for one in answered].count(True) == 1
    refused = next(one for one in answered if one.diagnostic is not None)
    assert refused.diagnostic is not None
    assert refused.diagnostic.code == "hub.already_running"
```

  The comment and the assertions about the second child move with them into
  `test_processes.py`, above.
- `test_closing_the_window_leaves_no_child_behind`: delete it. Its claim is now
  `test_closing_a_window_releases_every_child`, asserted where `Processes` is the subject; leaving
  a copy here would be one fact in two files.

Remove the now-unused `pytest` and `asyncio` imports from `test_runtime.py` only if nothing else
in the file uses them — `asyncio.gather` in the overlapping-starts test still does.

- [ ] **Step 6: Run the suite**

Run: `make lint typecheck test`
Expected: 242 tests pass. `free_port` no longer exists in `vibepy_hub`; the helper of the same
name in `tests/test_serve_command.py` and `tests_support.py` is a test choosing a port for a
server it runs itself, and stays.

- [ ] **Step 7: Commit**

```bash
git add packages/vibepy-hub
git commit -m "Hand a started App the port it was allocated, and answer with its address"
```

---

### Task 6: Two Apps, concurrently, through one configuration

The acceptance criterion, as written.

**Files:**
- Create: `fixtures/second-app/pyproject.toml`,
  `fixtures/second-app/src/second_app/__init__.py`,
  `fixtures/second-app/src/second_app/entry.py`
- Modify: `pyproject.toml:20-21` (workspace members)
- Modify: `packages/vibepy-hub/tests/tests_support.py`
- Modify: `packages/vibepy-hub/tests/test_proxy.py`

**Interfaces:**
- Consumes: everything from Tasks 1 to 5.
- Produces: `tests_support.http_status(url: str, /, *, host: str | None = None) -> int` and
  `tests_support.FIXTURES: Path`.

- [ ] **Step 1: Let a request carry a host it does not resolve**

In `tests_support.py`, replace `from urllib.request import urlopen` with
`from urllib.request import Request, urlopen`, and replace `http_status` and `_status` with:

```python
async def http_status(url: str, /, *, host: str | None = None) -> int:
    """The status a running App answers with, asked through whatever serves `url`.

    `host` is sent as the `Host` header and is never resolved. That is what the
    proxy routes on, and it keeps the test independent of whether the platform's
    resolver knows `.localhost` -- RFC 6761 makes it a SHOULD, and browsers
    rather than system resolvers are what implement it.

    `urlopen` blocks, so it runs in a thread rather than on the loop the test
    shares with the Hub.
    """
    return await asyncio.to_thread(_status, url, host)


def _status(url: str, host: str | None, /) -> int:
    request = Request(url, headers={} if host is None else {"Host": host})
    with urlopen(request, timeout=30) as answer:
        return int(answer.status)
```

Every existing caller passes the url alone and is unaffected.

- [ ] **Step 2: Add the App the tests install**

This repository ships one App with a Web channel and does so deliberately: `examples/notes` is
Agent-only, which is what makes L1's extras split provable. An example is a product surface, so
the second servable App is a fixture — checked in as real files, in the same shape every other
distribution here has, and installed by the same `uv pip install <folder>` the Hub runs for an
example. It is not under `examples/` and not in the dev dependency group, so it ships with
nothing and is installed only by the test that asks for it.

Create `fixtures/second-app/pyproject.toml`:

```toml
[project]
name = "vibepy-second"
version = "0.0.0"
description = "A servable App the Hub's tests install. Not a sample."
requires-python = ">=3.12"
dependencies = [
    "vibepy-core[web]",
    "nicegui>=3.16",
]

[project.entry-points."vibepy.apps"]
second-app = "second_app.entry:APP"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/second_app"]

[tool.uv.sources]
vibepy-core = { workspace = true }
```

Create an empty `fixtures/second-app/src/second_app/__init__.py`, and
`fixtures/second-app/src/second_app/entry.py`:

```python
"""A servable App with nothing in it but a Page and the Tool it reaches.

A fixture, not a sample. `examples/` holds one App with a Web channel on
purpose, and a test that needs a second one needs it to be uninteresting: this
declares no configuration, so a test that installs it asserts about the Hub
rather than about what this App happens to require.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from nicegui import ui
from pydantic import BaseModel

from vibepy_core.app import AppDefinition, AppEntrypoint
from vibepy_core.page import Page, PageContext, PageDefinition
from vibepy_core.tool import Tool, ToolContext, ToolDefinition


class NoConfig(BaseModel):
    """This App requires nothing of its host."""


class Greeting(BaseModel):
    said: str


@asynccontextmanager
async def second_lifespan(_config: NoConfig) -> AsyncGenerator[None]:
    """It holds no resource, and says so by yielding None."""
    yield None


async def greet(_ctx: ToolContext[None], _payload: NoConfig) -> Greeting:
    return Greeting(said="second-app")


async def home(ctx: PageContext) -> None:
    """The Page reaches its domain through a Tool, like any other."""
    said = Greeting.model_validate(await ctx.tools.invoke("greet", {}))
    ui.label(said.said)


SECOND_APP: AppDefinition[None, NoConfig] = AppDefinition(
    app_id="second-app",
    name="Second",
    version="0.0.0",
    config=NoConfig,
    tools=[
        Tool(
            definition=ToolDefinition(
                name="greet",
                description="Say this App's name",
                input_model=NoConfig,
                output_model=Greeting,
            ),
            handler=greet,
        )
    ],
    pages=[
        Page(
            definition=PageDefinition(name="home", route="/home", title="Home"),
            handler=home,
        )
    ],
)

APP: AppEntrypoint[None, NoConfig] = AppEntrypoint(
    definition=SECOND_APP, lifespan=second_lifespan
)
```

In the root `pyproject.toml`, the workspace gains the fixture so that
`vibepy-core = { workspace = true }` resolves for it exactly as it does for an example:

```toml
[tool.uv.workspace]
members = ["packages/*", "examples/*", "fixtures/*"]
```

It is deliberately absent from `[dependency-groups].dev`: a member nothing depends on is
resolvable without being installed into this repository's own environment.

Checking an installable fixture distribution into the repository is the established practice —
pip's `tests/data/packages/` holds dozens of purpose-built ones its suite installs
(<https://github.com/pypa/pip/tree/main/tests/data/packages>). The placement here departs from
pip's, which keeps them under the tests tree, and the departure is deliberate: a distribution in
this repository resolves the core through the workspace, and a fixture that resolved it by a
relative path instead would be installed by a path no example is installed by. When an install
fails, that difference is the first thing anyone would have to rule out.

In `tests_support.py`, name where it lives, beside `EXAMPLES`:

```python
FIXTURES = REPO / "fixtures"
"""Distributions that exist to be installed by a test. Not product surface."""
```

Run: `uv sync && uv run pytest --collect-only -q | tail -2`
Expected: the collection is unchanged, and `.venv` holds no `second_app`.

- [ ] **Step 3: Write the failing test**

Append to `packages/vibepy-hub/tests/test_proxy.py`, extending its imports with
`from tests_support import EXAMPLES, FIXTURES, http_status, hub` and
`from vibepy_hub.models import RunningApp`:

```python
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

        async with traefik(
            config, port=proxy_port, host="vibepy-todo.localhost", path="/todos"
        ):
            todo = await served_body(proxy_port, host="vibepy-todo.localhost", path="/todos")
            second = await served_body(proxy_port, host="vibepy-second.localhost", path="/home")

        assert config.read_text(encoding="utf-8") == written

    # Each host reached its own App. Two statuses would not say that: two
    # requests answered by one App are also two 200s, and the criterion is that
    # both Apps are served, not that both requests succeeded.
    assert "todos" in todo.lower()
    assert "second-app" in second
```

`served_body` is `http_status`'s sibling in `tests_support.py`, added here because a status code
cannot tell two Apps apart:

```python
async def served_body(port: int, *, host: str, path: str) -> str:
    """What the App behind this hostname answers with.

    The `Host` header is sent and never resolved: that is what the proxy routes
    on, and it keeps the test independent of whether the platform's resolver
    knows `.localhost` -- RFC 6761 makes it a SHOULD, and browsers rather than
    system resolvers are what implement it.
    """
    return await asyncio.to_thread(_body, f"http://127.0.0.1:{port}{path}", host)


def _body(url: str, host: str, /) -> str:
    with urlopen(Request(url, headers={"Host": host}), timeout=30) as answer:
        return answer.read().decode(errors="replace")
```

- [ ] **Step 3b: Run the test**

Run: `uv run pytest packages/vibepy-hub/tests/test_proxy.py -v`
Expected: PASS, two tests. This test exercises finished work, so a failure is a defect in Tasks 2
to 5 rather than a step to implement — read it rather than working around it. A failed install
answers with `hub.install_failed`, whose details name the step and uv's own output.

- [ ] **Step 4: Retire the scaffolding, so one document has one writer**

Task 1's `install_configuration` and `route` wrote by hand what the Hub now writes. Delete both
from `packages/vibepy-hub/tests/test_proxy.py`, and rewrite the WebSocket test to drive the Hub,
which is also what makes it prove the thing that matters: that a socket survives *the
configuration the product generates*, not one a test composed.

```python
async def test_a_page_s_websocket_survives_the_proxy(tmp_path: Path) -> None:
    """Traefik's documentation does not say it carries a WebSocket, and a
    NiceGUI Page does not work without one. This is where that is settled, and
    it is settled against the configuration the Hub itself wrote."""
    proxy_port = free_port()
    root = tmp_path / "hub"

    async with hub(root, proxy_port=proxy_port) as tools:
        await tools.invoke("register_package_source", {"path": str(FIXTURES)})
        await tools.invoke("install_app", {"app_name": "vibepy-second"})
        started = await tools.invoke("start_app", {"app_name": "vibepy-second", "secrets": {}})
        assert isinstance(started, RunningApp)
        assert started.diagnostic is None

        async with traefik(root / "traefik.yml", port=proxy_port):
            frame = await first_frame(
                proxy_port, host="vibepy-second.localhost", path=SOCKET_IO
            )

    # An unmasked text frame carrying engine.io's OPEN packet: the upgrade was
    # carried, and so was what the server sent after it.
    assert frame[0] == 0x81
    assert frame[2:4] == b"0{"
```

The `json`, `sys` and `asyncio` imports the old version needed go with it, unless the file's other
test still uses them.

- [ ] **Step 5: Run the suite and commit**

Run: `make lint typecheck test`
Expected: 243 tests pass.

```bash
git add pyproject.toml fixtures packages/vibepy-hub/tests
git commit -m "Serve two Apps at once through one proxy configuration"
```

---

### Task 7: The record, and the documents this stage makes false

**Files:**
- Create: `docs/decisions/ADR-031-the-proxy-is-traefik.md`
- Modify: `packages/vibepy-hub/src/vibepy_hub/models.py:1-27` (module docstring)
- Modify: `docs/milestones/code-review-roadmap.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Write the record**

Create `docs/decisions/ADR-031-the-proxy-is-traefik.md` in the Nygard format the other records
use — Status, Context, Decision, Consequences — saying *why* and not *how*. It must contain:

- **Status:** Accepted, dated.
- **Context:** an App's address changed at every start, so nothing could be put in front of one;
  D6 had already rejected a path prefix because NiceGUI requires `root_path` and manual
  prefixing inside every App's own markup; P3 — an App author pays nothing for the deployment
  shape — is stated here for the first time, because no record owns it.
- **Decision:** the proxy is Traefik; the Hub writes its routing configuration and owns no proxy;
  the entry point is declared in `HubConfig` and each App's own port is allocated and stored.
- **Consequences:** nginx was rejected because its own documentation calls the Windows build a
  beta version and AGENTS.md says the framework runs on Windows; Caddy was rejected because
  routes reach it through an admin HTTP API, which would have the Hub hold a client and fail an
  install when the proxy is down, and because it installs a root certificate into the system
  trust store; a fixed port means a port taken by something else is a start that fails with
  `hub.start_failed`, which `free_port()` used to prevent; the Hub does not know whether the
  proxy is running; Traefik's documentation does not state that it carries WebSocket
  connections, and `packages/vibepy-hub/tests/test_proxy.py` is what holds it to doing so.

Cite rather than restate: ADR-025 for what is adopted rather than written, ADR-028 for the name
the hostname is taken from, and `docs/milestones/code-review/decisions.md` for D6 to D8.

- [ ] **Step 2: Say in `models.py` what an address is**

Append to the module docstring of `packages/vibepy-hub/src/vibepy_hub/models.py`, after the code
table, keeping the table where it is:

```
An installed App is reached at `http://<app>.localhost:<proxy port>`. The
hostname is the App's canonical distribution name (ADR-028) and the port is the
one the Hub was configured with; the port the App itself serves on is allocated
when it is installed and does not leave the Hub. See
`docs/decisions/ADR-031-the-proxy-is-traefik.md`, until CR3 gives the Hub a
document to carry this and the table above.
```

- [ ] **Step 3: Mark what is behind us**

In `docs/milestones/code-review-roadmap.md`, add `Merged.` under CR2's acceptance list, in the
form the earlier stages use, and change the `## Order` section's first line from `CR2 — next.` to
`CR3 — next.`

- [ ] **Step 4: Run the suite and commit**

Run: `make lint typecheck test`
Expected: 243 tests pass.

```bash
git add docs packages/vibepy-hub/src/vibepy_hub/models.py
git commit -m "Record that the proxy is Traefik and the Hub does not own it (ADR-031)"
```

---

## When the plan is done

- `make lint typecheck test` passes, 243 tests.
- Review the branch, then cross-check it against what R1 was for: two Apps through one static
  configuration, `RunningApp` answering with an address, `free_port` gone, and nothing added to
  either example App because of how it is served — `git diff main -- examples/` is empty.
- Do not push. Integration is `superpowers:finishing-a-development-branch`, and R1 merges
  `--no-ff` into `main`.
