"""Storage of Pages under their names."""

from vibepy_core.errors import PageNotFoundError
from vibepy_core.page.model import Page


class PageRegistry:
    """Maps a Page name to the Page registered under it. Storage only.

    Keyed by name rather than by route: the name is the identifier that survives a
    route change, and routes have no meaning until a Web channel registers them.
    """

    def __init__(self) -> None:
        self._pages: dict[str, Page] = {}

    def register(self, page: Page) -> None:
        self._pages[page.definition.name] = page

    def resolve(self, name: str) -> Page:
        page = self._pages.get(name)
        if page is None:
            raise PageNotFoundError(name)
        return page
