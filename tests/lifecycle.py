"""Lifespan helpers the test suite shares."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager


@asynccontextmanager
async def no_dependencies() -> AsyncGenerator[None]:
    """The lifespan of a Plugin with no application-scoped resource."""
    yield None
