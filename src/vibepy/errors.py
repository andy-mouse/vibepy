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
