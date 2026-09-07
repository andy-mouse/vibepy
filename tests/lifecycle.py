"""Lifecycle helpers the test suite shares.

The framework offers no ``async with`` over an AppRuntime, so tests that need a
started App pair start with stop themselves. This is that pairing, written once.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from vibepy.app import AppRuntime


@asynccontextmanager
async def started[DepsT](app: AppRuntime[DepsT]) -> AsyncGenerator[AppRuntime[DepsT]]:
    """Start an App for the duration of the block and stop it afterwards."""
    await app.start()
    try:
        yield app
    finally:
        await app.stop()


@asynccontextmanager
async def no_dependencies() -> AsyncGenerator[None]:
    """The lifespan of an App with no application-scoped resource."""
    yield None
