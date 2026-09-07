"""Framework exceptions. Exception types are the contract, message strings are not."""


class VibepyError(Exception):
    """Base class for every exception raised by the framework."""


class ToolNotFoundError(VibepyError):
    """No Tool is registered under the requested name."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"No Tool is registered under the name {tool_name!r}")
        self.tool_name = tool_name


class ToolInputValidationError(VibepyError):
    """Raw input did not satisfy the Tool's input model."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Input for Tool {tool_name!r} failed validation")
        self.tool_name = tool_name


class ToolOutputValidationError(VibepyError):
    """A handler result did not satisfy the Tool's output model."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Output of Tool {tool_name!r} failed validation")
        self.tool_name = tool_name


class PageNotFoundError(VibepyError):
    """No Page is registered under the requested name."""

    def __init__(self, page_name: str) -> None:
        super().__init__(f"No Page is registered under the name {page_name!r}")
        self.page_name = page_name


class PageRouteInvalidError(VibepyError):
    """A Page declared a route the Web channel cannot register."""

    def __init__(self, page_name: str, route: str) -> None:
        super().__init__(f"Page {page_name!r} declared the invalid route {route!r}")
        self.page_name = page_name
        self.route = route


class PageRouteConflictError(VibepyError):
    """Two Pages declared the same route."""

    def __init__(self, route: str, page_name: str, conflicting_page_name: str) -> None:
        super().__init__(
            f"Pages {page_name!r} and {conflicting_page_name!r} both declare the route {route!r}"
        )
        self.route = route
        self.page_name = page_name
        self.conflicting_page_name = conflicting_page_name
