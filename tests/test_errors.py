"""The error model contract from docs/architecture/errors.md.

The catalogue tests walk every framework exception rather than naming them one by
one: a code that is missing, duplicated, or unmapped is a defect in the model, and
a milestone that adds an error must not be able to skip the rule by not editing
this file.
"""

from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError

import pytest

from vibepy_core import errors
from vibepy_core.errors import (
    UNHANDLED_CODE,
    AppConfigInvalidError,
    AppEntrypointInvalidError,
    AppEntrypointUnloadableError,
    ErrorCategory,
    ErrorInfo,
    PageNotFoundError,
    PageRouteConflictError,
    PageRouteInvalidError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    VibepyError,
    to_error_info,
)


def _descendants(cls: type[VibepyError]) -> Iterator[type[VibepyError]]:
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _descendants(subclass)


def _framework_errors() -> list[type[VibepyError]]:
    """Every exception the framework itself defines.

    Filtered by module because the base is exported: an App may subclass it, and
    an App's exception is not the framework's to catalogue. `errors.md` says such
    an exception is described, not classified.
    """
    return sorted(
        (error for error in _descendants(VibepyError) if error.__module__ == errors.__name__),
        key=lambda error: error.__name__,
    )


# One constructed instance per framework exception, with the details its message
# interpolates. Adding an exception without adding a row fails
# test_every_framework_error_is_covered_here.
CASES: list[tuple[VibepyError, str, ErrorCategory, Mapping[str, str]]] = [
    (
        ToolNotFoundError("create_todo"),
        "tool.not_found",
        ErrorCategory.CALLER,
        {"tool_name": "create_todo"},
    ),
    (
        ToolInputValidationError("create_todo"),
        "tool.input_invalid",
        ErrorCategory.CALLER,
        {"tool_name": "create_todo"},
    ),
    (
        ToolOutputValidationError("create_todo"),
        "tool.output_invalid",
        ErrorCategory.EXECUTION,
        {"tool_name": "create_todo"},
    ),
    (
        PageNotFoundError("todos"),
        "page.not_found",
        ErrorCategory.CALLER,
        {"page_name": "todos"},
    ),
    (
        PageRouteInvalidError("todos", "todos"),
        "page.route_invalid",
        ErrorCategory.DECLARATION,
        {"page_name": "todos", "route": "todos"},
    ),
    (
        PageRouteConflictError("/todos", "todos", "other"),
        "page.route_conflict",
        ErrorCategory.DECLARATION,
        {"route": "/todos", "page_name": "todos", "conflicting_page_name": "other"},
    ),
    (
        AppConfigInvalidError("todo-app", ["db_path", "limits.max"]),
        "config.invalid",
        ErrorCategory.CALLER,
        {"app_id": "todo-app", "fields": "db_path, limits.max"},
    ),
    (
        AppEntrypointUnloadableError("todo", "todo_app.entry:app"),
        "package.entrypoint_unloadable",
        ErrorCategory.DECLARATION,
        {"app_name": "todo", "reference": "todo_app.entry:app"},
    ),
    (
        AppEntrypointInvalidError("todo", "todo_app.entry:app", "AppDefinition"),
        "package.entrypoint_invalid",
        ErrorCategory.DECLARATION,
        {
            "app_name": "todo",
            "reference": "todo_app.entry:app",
            "found": "AppDefinition",
        },
    ),
]


def test_every_framework_error_is_covered_here() -> None:
    covered = {type(error) for error, _, _, _ in CASES}
    assert covered == set(_framework_errors())


@pytest.mark.parametrize("error", [case[0] for case in CASES], ids=lambda e: type(e).__name__)
def test_a_code_is_namespaced_and_not_empty(error: VibepyError) -> None:
    namespace, separator, name = error.code.partition(".")
    assert namespace
    assert separator == "."
    assert name


def test_no_two_errors_share_a_code() -> None:
    codes = [error.code for error in _framework_errors()]
    assert len(codes) == len(set(codes))


def test_no_framework_error_uses_the_unhandled_code() -> None:
    assert UNHANDLED_CODE not in {error.code for error in _framework_errors()}


@pytest.mark.parametrize(("error", "code", "category", "details"), CASES, ids=lambda v: str(v)[:40])
def test_normalization_reports_the_declared_code(
    error: VibepyError, code: str, category: ErrorCategory, details: Mapping[str, str]
) -> None:
    info = to_error_info(error)

    assert info.code == code
    assert info.category is category
    assert info.details == details
    assert info.message == str(error)


@pytest.mark.parametrize("error", [case[0] for case in CASES], ids=lambda e: type(e).__name__)
def test_every_value_the_message_interpolates_is_in_details(error: VibepyError) -> None:
    """AIP-193: information contributing to the message belongs in the metadata.

    An agent must never have to parse the sentence to learn which Tool failed.
    """
    message = str(error)
    for value in to_error_info(error).details.values():
        assert value in message


def test_the_bare_base_is_described_rather_than_classified() -> None:
    info = to_error_info(VibepyError("boom"))

    assert info.code == UNHANDLED_CODE
    assert info.category is ErrorCategory.EXECUTION
    assert info.message == "boom"
    assert info.details == {}


def test_an_app_subclass_of_the_public_base_is_described() -> None:
    """The public base is an extension point for catching, not for classifying.

    `docs/architecture/errors.md`: an exception raised by an App's own code is
    described, not classified.
    """

    class AppOwnError(VibepyError):
        code = "app.something_specific"

        def details(self) -> Mapping[str, str]:
            return {"where": "the app"}

    info = to_error_info(AppOwnError("no good"))

    assert info.code == UNHANDLED_CODE
    assert info.category is ErrorCategory.EXECUTION
    assert info.message == "no good"
    assert info.details == {}


def test_an_exception_carrying_a_framework_code_it_does_not_own_is_described() -> None:
    """Classification reads the framework's own hierarchy, not any `code` attribute."""

    class Impostor(Exception):
        code = "tool.not_found"

    info = to_error_info(Impostor("pretending"))

    assert info.code == UNHANDLED_CODE
    assert info.category is ErrorCategory.EXECUTION


def test_an_exception_the_framework_did_not_define_is_execution() -> None:
    info = to_error_info(RuntimeError("the handler failed"))

    assert info.code == UNHANDLED_CODE
    assert info.category is ErrorCategory.EXECUTION
    assert info.message == "the handler failed"
    assert info.details == {}


def test_error_info_is_frozen() -> None:
    info = to_error_info(ToolNotFoundError("create_todo"))

    with pytest.raises(FrozenInstanceError):
        info.code = "tool.input_invalid"  # pyright: ignore[reportAttributeAccessIssue]


def test_a_category_reads_as_its_own_value() -> None:
    """The value crosses a channel boundary as a string."""
    assert ErrorCategory.CALLER == "caller"
    assert ErrorInfo("tool.not_found", ErrorCategory.CALLER, "m", {}).category == "caller"
