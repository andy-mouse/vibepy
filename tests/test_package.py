import vibepy_core


def test_public_api_is_exported_from_the_package_root() -> None:
    assert vibepy_core.__all__ == [
        "APP_GROUP",
        "AppConfigInvalidError",
        "AppDefinition",
        "AppDescription",
        "AppEntrypoint",
        "AppEntrypointInvalidError",
        "AppEntrypointUnloadableError",
        "AppNotDeclaredError",
        "AppRef",
        "ErrorCategory",
        "ErrorInfo",
        "Lifespan",
        "NoConfig",
        "Page",
        "PageContext",
        "PageDefinition",
        "PageDescription",
        "PageHandler",
        "PageNotFoundError",
        "PageRegistry",
        "PageRouteConflictError",
        "PageRouteInvalidError",
        "PageRuntime",
        "Tool",
        "ToolContext",
        "ToolDefinition",
        "ToolDescription",
        "ToolHandler",
        "ToolInputValidationError",
        "ToolInvoker",
        "ToolNotFoundError",
        "ToolOutputValidationError",
        "ToolRegistry",
        "ToolRuntime",
        "VibepyError",
        "describe_app",
        "discover_apps",
        "page_runtime_for",
        "to_error_info",
        "tool_runtime_for",
    ]


def test_every_exported_name_is_reachable() -> None:
    for name in vibepy_core.__all__:
        assert hasattr(vibepy_core, name)
