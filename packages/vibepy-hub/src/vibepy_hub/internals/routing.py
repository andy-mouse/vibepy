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
