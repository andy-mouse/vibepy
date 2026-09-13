"""Storage of Pages under their names."""

from vibepy_core.errors import PageNotFoundError
from vibepy_core.page._model import Page


class PageRegistry:
    """Maps a Page name to the Page registered under it. Storage only.

    Keyed by name rather than by route: the name is the identifier that survives a
    route change, and routes have no meaning until a Web channel registers them.
    """

    def __init__(self) -> None:
        """Start with no Page registered."""
        self._pages: dict[str, Page] = {}

    def register(self, page: Page) -> None:
        """Register `page` under its own name, replacing any earlier one."""
        self._pages[page.definition.name] = page

    def resolve(self, name: str) -> Page:
        """Return the Page registered under `name`.

        Raises:
            PageNotFoundError: no Page is registered under that name.
        """
        page = self._pages.get(name)
        if page is None:
            raise PageNotFoundError(name)
        return page
