"""Lifespan helpers the test suite shares."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from vibepy.app import NoConfig


@asynccontextmanager
async def no_dependencies(_config: NoConfig) -> AsyncGenerator[None]:
    """The lifespan of an App with no application-scoped resource."""
    yield None
