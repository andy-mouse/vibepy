import vibepy


def test_public_api_is_exported_from_the_package_root() -> None:
    assert vibepy.__all__ == [
        "AppDefinition",
        "AppRuntime",
        "Page",
        "PageContext",
        "PageDefinition",
        "PageHandler",
        "PageNotFoundError",
        "PageRegistry",
        "PageRuntime",
        "Tool",
        "ToolContext",
        "ToolDefinition",
        "ToolHandler",
        "ToolInputValidationError",
        "ToolInvocation",
        "ToolInvoker",
        "ToolNotFoundError",
        "ToolOutputValidationError",
        "ToolRegistry",
        "ToolRuntime",
        "VibepyError",
    ]


def test_every_exported_name_is_reachable() -> None:
    for name in vibepy.__all__:
        assert hasattr(vibepy, name)
