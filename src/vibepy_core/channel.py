"""The channels an App is exposed through."""

from enum import StrEnum

__all__ = ["Channel"]


class Channel(StrEnum):
    """One of the two first-class channels. Fixed when a window opens."""

    WEB = "web"
    AGENT = "agent"
