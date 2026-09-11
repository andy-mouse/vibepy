"""Reading what an installed distribution declares, without importing it.

Entry point metadata is written to ``entry_points.txt`` in a distribution's
``dist-info`` at build time and is read from there, so a reader learns what an
environment offers without executing any of it. Only ``EntryPoint.load`` imports,
and this module's discovery never calls it.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import EntryPoint, distributions
from pathlib import Path
from typing import TypeGuard

from pydantic import BaseModel

from vibepy_core.app.entrypoint import AppDescription, AppEntrypoint
from vibepy_core.errors import (
    AppEntrypointInvalidError,
    AppEntrypointUnloadableError,
    AppNotDeclaredError,
)

logger = logging.getLogger(__name__)

APP_GROUP = "vibepy.apps"
"""The entry point group an App declares itself in.

A group name is metadata read as a string and imports nothing, so it claims no
distribution name on any index.
"""


@dataclass(frozen=True)
class AppRef:
    """Where an App is declared. Carries no imported object and no declaration."""

    app_name: str
    distribution: str
    distribution_version: str
    module: str
    attr: str


def discover_apps(*, path: Sequence[Path] | None = None) -> tuple[AppRef, ...]:
    """Every App declared in an environment, ordered and without importing one.

    ``path`` is forwarded to the distribution finder, so an environment other
    than the running interpreter's can be enumerated. That is what lets a host
    inspect an App it must not import.
    """
    found = distributions() if path is None else distributions(path=[str(entry) for entry in path])
    refs = [
        AppRef(
            app_name=entry.name,
            distribution=dist.name,
            distribution_version=dist.version,
            module=entry.module,
            attr=entry.attr,
        )
        for dist in found
        for entry in dist.entry_points.select(group=APP_GROUP)
    ]
    logger.debug("discovered %d App declaration(s)", len(refs))
    return tuple(sorted(refs, key=lambda ref: (ref.app_name, ref.distribution)))


def _is_entrypoint(value: object, /) -> TypeGuard[AppEntrypoint[object, BaseModel]]:
    """Whether what a reference resolved to is a composition root.

    A runtime check cannot see type arguments, and this module never constructs
    a definition or calls a lifespan itself, so the widest pair is a sound
    reading of what was found.
    """
    return isinstance(value, AppEntrypoint)


def _load(ref: AppRef, /) -> AppEntrypoint[object, BaseModel]:
    """Import one declared entrypoint and check it is one."""
    reference = f"{ref.module}:{ref.attr}"
    entry = EntryPoint(name=ref.app_name, value=reference, group=APP_GROUP)
    try:
        loaded: object = entry.load()
    except (ImportError, AttributeError) as error:
        raise AppEntrypointUnloadableError(ref.app_name, reference) from error
    if not _is_entrypoint(loaded):
        raise AppEntrypointInvalidError(ref.app_name, reference, type(loaded).__name__)
    return loaded


def describe_app(ref: AppRef, /) -> AppDescription:
    """Load one declared entrypoint and project it.

    This imports, so it belongs in the App's own environment. A host that cannot
    import an App runs `python -m vibepy_core.describe` in that environment instead.
    """
    return _load(ref).describe()


def load_app(app_name: str, /) -> AppEntrypoint[object, BaseModel]:
    """Load the App this interpreter's environment declares under `app_name`.

    This imports, so it belongs in the App's own environment: `serve` and
    `invoke` call it there, and a host reaches it only through them.

    Raises:
        AppNotDeclaredError: nothing in this environment declares `app_name`.
        AppEntrypointUnloadableError: the reference does not import.
        AppEntrypointInvalidError: the reference is not an `AppEntrypoint`.
    """
    for ref in discover_apps():
        if ref.app_name == app_name:
            return _load(ref)
    raise AppNotDeclaredError(app_name)
