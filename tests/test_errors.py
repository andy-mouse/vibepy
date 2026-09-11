"""The error model contract from docs/architecture/errors.md.

The catalogue tests walk every framework exception rather than naming them one by
one: a code that is missing, duplicated, or unmapped is a defect in the model, and
a milestone that adds an error must not be able to skip the rule by not editing
this file.
"""

import importlib
import json
import pkgutil
from collections.abc import Iterator, Mapping

import pytest
from pydantic import ValidationError

import vibepy_core
from vibepy_core.errors import (
    ERROR_CATALOG,
    UNHANDLED_CODE,
    AppConfigInvalidError,
    AppEntrypointInvalidError,
    AppEntrypointUnloadableError,
    AppNotDeclaredError,
    ErrorCategory,
    ErrorInfo,
    InvokeRequestInvalidError,
    PageNameConflictError,
    PageNotFoundError,
    PageRouteConflictError,
    PageRouteInvalidError,
    ToolInputValidationError,
    ToolNameConflictError,
    ToolNotFoundError,
    ToolOutputValidationError,
    VibepyError,
    read_report_line,
    report_line,
    to_error_info,
)

_CORE = vibepy_core.__name__
"""The package a framework exception is defined somewhere inside."""


def _import_every_core_module() -> None:
    """Make every framework exception exist before the catalogue walks for them.

    `__subclasses__()` sees only classes whose module has been imported, so the
    catalogue's reach is import coverage rather than a name filter. I1 was a
    framework exception in a module this file never imported: filtering alone
    would leave that shape of defect invisible, because the class would not yet
    exist.
    """
    for found in pkgutil.walk_packages(vibepy_core.__path__, f"{_CORE}."):
        importlib.import_module(found.name)


def _descendants(cls: type[VibepyError]) -> Iterator[type[VibepyError]]:
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _descendants(subclass)


def _framework_errors() -> list[type[VibepyError]]:
    """Every exception the framework itself defines, wherever it defines it.

    Filtered by package rather than by module. The base is exported, so an App
    may subclass it and a test may too, and such a subclass is not the
    framework's to catalogue -- `errors.md` says it is described, not
    classified. Filtering by `errors.py` alone would hide a framework exception
    declared in another core module, which is the shape of the defect this
    catalogue exists to catch.
    """
    _import_every_core_module()
    return sorted(
        (error for error in _descendants(VibepyError) if error.__module__.startswith(f"{_CORE}.")),
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
    (
        ToolNameConflictError("create_todo"),
        "tool.name_conflict",
        ErrorCategory.DECLARATION,
        {"tool_name": "create_todo"},
    ),
    (
        PageNameConflictError("todos", "/todos", "/todo-list"),
        "page.name_conflict",
        ErrorCategory.DECLARATION,
        {"page_name": "todos", "route": "/todos", "conflicting_route": "/todo-list"},
    ),
    (
        AppNotDeclaredError("absent"),
        "package.app_not_declared",
        ErrorCategory.CALLER,
        {"app_name": "absent"},
    ),
    (
        InvokeRequestInvalidError(),
        "invoke.request_invalid",
        ErrorCategory.CALLER,
        {},
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

    with pytest.raises(ValidationError):
        info.code = "tool.input_invalid"


def test_the_catalogue_is_public_and_includes_the_unhandled_code() -> None:
    assert ERROR_CATALOG["app.unhandled"] == ErrorCategory.EXECUTION
    for _error, code, category, _ in CASES:
        assert ERROR_CATALOG[code] == category


def test_a_report_line_is_one_json_object_of_the_four_fields() -> None:
    line = report_line(to_error_info(ToolNotFoundError("create_todo")))
    assert line.endswith("\n")
    assert json.loads(line) == {
        "code": "tool.not_found",
        "category": "caller",
        "message": str(ToolNotFoundError("create_todo")),
        "details": {"tool_name": "create_todo"},
    }


def test_a_category_reads_as_its_own_value() -> None:
    """The value crosses a channel boundary as a string."""
    assert ErrorCategory.CALLER == "caller"
    assert (
        ErrorInfo(code="tool.not_found", category=ErrorCategory.CALLER, message="m").category
        == "caller"
    )


def test_a_report_line_round_trips_as_the_same_error_info() -> None:
    """One format, three writers, one reader: what core writes, core reads."""
    info = to_error_info(ToolNotFoundError("x"))
    assert read_report_line(report_line(info)) == info


def test_a_line_naming_an_unknown_category_is_not_a_report() -> None:
    line = '{"code": "a.b", "category": "weather", "message": "", "details": {}}'
    assert read_report_line(line) is None


def test_a_line_that_is_not_a_report_reads_as_nothing() -> None:
    assert read_report_line("Traceback (most recent call last):") is None
    assert read_report_line('{"category": "caller"}') is None
