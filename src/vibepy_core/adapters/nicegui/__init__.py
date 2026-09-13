"""The Web channel: framework Pages projected onto NiceGUI routes."""

from vibepy_core.adapters.nicegui._application import build_web_app
from vibepy_core.adapters.nicegui._web import register_pages

__all__ = ["build_web_app", "register_pages"]
