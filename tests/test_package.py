import vibepy_core
import vibepy_core.app


def test_public_api_is_exported_from_the_package_root() -> None:
    assert vibepy_core.__all__ == [
        "ERROR_CATALOG",
        "AppConfig",
        "AppConfigInvalidError",
        "AppDefinition",
        "AppDefinitionInvalidError",
        "AppDescription",
        "AppEntrypoint",
        "AppEntrypointInvalidError",
        "AppEntrypointUnloadableError",
        "AppNotDeclaredError",
        "AuthorizationRequest",
        "Channel",
        "ConfigFieldDescription",
        "ConfigFieldType",
        "DescribedApp",
        "ErrorCategory",
        "ErrorInfo",
        "InvocationRecord",
        "InvocationRequest",
        "InvokeRequestInvalidError",
        "Lifespan",
        "NoConfig",
        "Page",
        "PageContext",
        "PageDefinition",
        "PageDescription",
        "PageHandler",
        "PageNameConflictError",
        "PageNotFoundError",
        "PageRegistry",
        "PageRouteConflictError",
        "PageRouteInvalidError",
        "PageRuntime",
        "PageToolUndeclaredError",
        "PageToolUnresolvedError",
        "Principal",
        "PrincipalToolInvoker",
        "Tool",
        "ToolChannelsEmptyError",
        "ToolContext",
        "ToolDefinition",
        "ToolDescription",
        "ToolForbiddenError",
        "ToolHandler",
        "ToolInputValidationError",
        "ToolInvoker",
        "ToolNameConflictError",
        "ToolNotFoundError",
        "ToolOutputValidationError",
        "ToolPolicy",
        "ToolRegistry",
        "ToolRuntime",
        "VibepyError",
        "WindowRecord",
        "page_runtime_for",
        "tool_runtime_for",
    ]


def test_the_app_subpackage_exports_declarations_and_descriptions() -> None:
    assert vibepy_core.app.__all__ == [
        "AppConfig",
        "AppDefinition",
        "AppDescription",
        "AppEntrypoint",
        "ConfigFieldDescription",
        "ConfigFieldType",
        "DescribedApp",
        "Lifespan",
        "NoConfig",
        "PageDescription",
        "ToolDescription",
        "WindowRecord",
        "page_registry_for",
        "page_runtime_for",
        "read_window_record",
        "tool_registry_for",
        "tool_runtime_for",
    ]


def test_every_exported_name_is_reachable() -> None:
    for name in vibepy_core.__all__:
        assert hasattr(vibepy_core, name)
    for name in vibepy_core.app.__all__:
        assert hasattr(vibepy_core.app, name)
