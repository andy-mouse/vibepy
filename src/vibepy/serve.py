"""Open one App's Web channel, in that App's own environment.

`vibepy.describe` reads a declaration; this runs one. Both are commands rather
than library calls for the same reason: the import belongs on the App's side of a
process boundary. See `docs/architecture/packaging.md`.

Composing a channel's running window is the framework's, which is why this lives
here and not in a Hub. NiceGUI owns the server, and `app.on_startup` and
`app.on_shutdown` are its documented lifecycle hooks, so nothing here builds an
ASGI application or calls a server.
"""

import argparse
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from contextlib import AsyncExitStack
from importlib.metadata import EntryPoint
from typing import TypeGuard

from nicegui import app, ui
from pydantic import BaseModel, TypeAdapter, ValidationError

from vibepy.adapters.nicegui import register_pages
from vibepy.app.composition import page_runtime_for
from vibepy.app.entrypoint import AppEntrypoint
from vibepy.app.package import APP_GROUP, discover_apps
from vibepy.errors import AppEntrypointInvalidError, AppEntrypointUnloadableError, to_error_info

logger = logging.getLogger(__name__)

_CONFIG = TypeAdapter(dict[str, object])
"""Standard input is one JSON object of configuration, validated as such."""


class AppNotDeclared(Exception):
    """No App of that name is declared in this environment."""


def _is_entrypoint(value: object, /) -> TypeGuard[AppEntrypoint[object, BaseModel]]:
    """Whether what a reference resolved to is a composition root.

    A runtime check cannot see type arguments, and this command never constructs
    a definition or calls a lifespan itself, so the widest pair is a sound
    reading of what was found.
    """
    return isinstance(value, AppEntrypoint)


def _entrypoint(app_name: str, /) -> AppEntrypoint[object, BaseModel]:
    """Resolve one declared App, importing only that one."""
    for ref in discover_apps():
        if ref.app_name != app_name:
            continue
        reference = f"{ref.module}:{ref.attr}"
        entry = EntryPoint(name=ref.app_name, value=reference, group=APP_GROUP)
        try:
            loaded: object = entry.load()
        except (ImportError, AttributeError) as error:
            raise AppEntrypointUnloadableError(app_name, reference) from error
        if not _is_entrypoint(loaded):
            raise AppEntrypointInvalidError(app_name, reference, type(loaded).__name__)
        return loaded
    raise AppNotDeclared(f"No App named {app_name!r} is declared in this environment")


def _serve(
    entrypoint: AppEntrypoint[object, BaseModel], config: Mapping[str, object], port: int, /
) -> None:
    """Hold the App's window open for as long as the server runs.

    The stack is what binds acquisition to release across two hooks: it registers
    a release only after its acquisition returned, which is the property
    `docs/architecture/lifecycle.md` relies on.
    """
    stack = AsyncExitStack()

    async def opened() -> None:
        pages = await stack.enter_async_context(
            page_runtime_for(entrypoint.definition, entrypoint.lifespan, config=config)
        )
        register_pages(entrypoint.definition, pages)

    async def closed() -> None:
        await stack.aclose()

    app.on_startup(opened)  # pyright: ignore[reportUnknownMemberType]
    app.on_shutdown(closed)  # pyright: ignore[reportUnknownMemberType]
    # `ui.run` takes `**kwargs: Any`, so its type is partially unknown to a strict
    # checker. Reload is off because a reloading child never calls `ui.run` again
    # under `python -m`, and the browser is not this process's to open.
    ui.run(  # pyright: ignore[reportUnknownMemberType]
        host="127.0.0.1", port=port, reload=False, show=False
    )


def main(argv: Sequence[str], /) -> int:
    """Read configuration from standard input and serve one App."""
    parser = argparse.ArgumentParser(prog="vibepy.serve")
    parser.add_argument("app_name")
    parser.add_argument("--port", type=int, required=True)
    parsed = parser.parse_args(argv)
    try:
        config: Mapping[str, object] = _CONFIG.validate_json(sys.stdin.read() or "{}")
    except ValidationError:
        sys.stderr.write('{"code": "serve.config_invalid", "message": "expected a JSON object"}\n')
        return 1
    try:
        entrypoint = _entrypoint(str(parsed.app_name))
    except AppNotDeclared as absent:
        sys.stderr.write(f"{absent}\n")
        return 1
    except (AppEntrypointUnloadableError, AppEntrypointInvalidError) as error:
        info = to_error_info(error)
        sys.stderr.write(json.dumps({"code": info.code, "message": info.message}) + "\n")
        return 1
    _serve(entrypoint, config, int(parsed.port))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
