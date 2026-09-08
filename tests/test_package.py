import vibepy


def test_public_api_is_exported_from_the_package_root() -> None:
    assert vibepy.__all__ == [
        "ErrorCategory",
        "ErrorInfo",
        "Lifespan",
        "Page",
        "PageContext",
        "PageDefinition",
        "PageHandler",
        "PageNotFoundError",
        "PageRegistry",
        "PageRouteConflictError",
        "PageRouteInvalidError",
        "PageRuntime",
        "PluginDefinition",
        "Tool",
        "ToolContext",
        "ToolDefinition",
        "ToolHandler",
        "ToolInputValidationError",
        "ToolInvoker",
        "ToolNotFoundError",
        "ToolOutputValidationError",
        "ToolRegistry",
        "ToolRuntime",
        "VibepyError",
        "page_runtime_for",
        "to_error_info",
        "tool_runtime_for",
    ]


def test_every_exported_name_is_reachable() -> None:
    for name in vibepy.__all__:
        assert hasattr(vibepy, name)
