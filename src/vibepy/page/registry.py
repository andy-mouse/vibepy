"""Storage of Pages under their names."""

from vibepy.errors import PageNotFoundError
from vibepy.page.model import Page, PageDefinition


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

    def definitions(self) -> tuple[PageDefinition, ...]:
        """Every registered declaration, in registration order.

        A Web channel adapter projects these into routes, which is enumeration
        rather than lookup.
        """
        return tuple(page.definition for page in self._pages.values())
