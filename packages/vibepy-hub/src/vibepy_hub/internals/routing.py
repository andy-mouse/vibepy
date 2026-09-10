"""Where an App is reached, and what the proxy in front of it is told.

This is the Hub's whole knowledge of Traefik. A different proxy replaces this
module and nothing else. The Hub writes files here and never signals, starts or
observes the proxy.
"""

import asyncio
import logging
from collections.abc import Collection
from pathlib import Path

import yaml

from vibepy_hub.internals.files import write_whole

logger = logging.getLogger(__name__)

PORT_BASE = 9000
"""The lowest port an App is given.

Above the range a user's own servers habitually take, and below the ephemeral
range an operating system allocates from, so a stored port and an incidental one
are unlikely to meet.
"""


def allocate(held: Collection[int], /) -> int:
    """Return the lowest port at or above the base that no installed App holds.

    Which App holds which port is not this function's fact: it is asked only for
    an App that holds none, because one that is already installed is refused
    before an allocation is reached.
    """
    used = set(held)
    port = PORT_BASE
    while port in used:
        port += 1
    return port


def address(app_name: str, proxy_port: int, /) -> str:
    """Where a caller reaches this App.

    The hostname is the App's canonical distribution name, which the normalization specification
    leaves as lowercase letters, digits and `-`, beginning and ending with a letter or digit. That
    is a DNS label as written, so nothing here escapes or maps it.
    """
    return f"http://{app_name}.localhost:{proxy_port}"


ROUTES = "routes"
INSTALL_CONFIG = "traefik.yml"


async def write_install_config(root: Path, /, *, proxy_port: int) -> None:
    """Write the half of the proxy's configuration that does not follow an App.

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
        root,
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
    # The directory is the window's, made when the install configuration that
    # names it is written. An App arrives through a window, so there is no
    # moment when a route is written and the directory it goes in is absent.
    _replace(
        root,
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
                    app_name: {"loadBalancer": {"servers": [{"url": f"http://127.0.0.1:{port}"}]}}
                },
            }
        },
    )


async def remove_route(root: Path, app_name: str, /) -> None:
    """Withdraw one App's route, if it has one."""
    await asyncio.to_thread(_remove_route, root, app_name)


def _remove_route(root: Path, app_name: str, /) -> None:
    (root / ROUTES / f"{app_name}.yml").unlink(missing_ok=True)


def _replace(root: Path, path: Path, document: object, /) -> None:
    """Write one of the proxy's files whole.

    Staged in the Hub's root rather than beside its destination, because the
    destination is inside the directory the provider watches. `write_whole`
    owns the rest, and says why.
    """
    write_whole(path, yaml.safe_dump(document, sort_keys=False), staging=root)
