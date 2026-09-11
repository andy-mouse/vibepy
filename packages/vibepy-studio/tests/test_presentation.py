"""The board's rules, with no screen involved."""

from vibepy_core.errors import ErrorCategory
from vibepy_studio.models import Diagnostic
from vibepy_studio.operating.models import AppRow, ConfigField
from vibepy_studio.operating.pages.presentation import row_view, save_request, sort_rows, summary


def available(name: str = "demo") -> AppRow:
    return AppRow(app_name=name, name=name.title(), distribution_version="1.0.0", state="available")


def installed(
    name: str = "demo", *, configured: bool = False, available_version: str | None = None
) -> AppRow:
    return AppRow(
        app_name=name,
        name=name.title(),
        version="0.0.0",
        distribution_version="1.0.0",
        state="installed",
        configured=configured,
        has_pages=True,
        available_version=available_version,
    )


def running(name: str = "demo") -> AppRow:
    return AppRow(
        app_name=name,
        name=name.title(),
        version="0.0.0",
        distribution_version="1.0.0",
        state="running",
        configured=True,
        has_pages=True,
    )


def test_an_available_app_offers_install_only() -> None:
    view = row_view(available(), declares_fields=False)
    assert [(a.label, a.tool, a.primary) for a in view.actions] == [
        ("Install", "install_app", True)
    ]
    assert [m.done for m in view.marks] == [True, False, False, False]


def test_a_running_app_offers_stop_only_and_every_stage_is_done() -> None:
    view = row_view(running(), declares_fields=True)
    assert [a.label for a in view.actions] == ["Stop"]
    assert [m.done for m in view.marks] == [True, True, True, True]


def test_an_unconfigured_app_cannot_start_and_is_told_to_configure() -> None:
    view = row_view(installed(configured=False), declares_fields=True)
    by_label = {a.label: a for a in view.actions}
    assert set(by_label) == {"Uninstall", "Configure", "Start"}
    assert by_label["Configure"].primary is True
    assert by_label["Start"].enabled is False
    assert view.marks[2].symbol == "!"
    assert view.marks[2].done is False


def test_a_configured_app_starts_and_configure_is_secondary() -> None:
    view = row_view(installed(configured=True), declares_fields=True)
    by_label = {a.label: a for a in view.actions}
    assert by_label["Start"].primary is True and by_label["Start"].enabled is True
    assert by_label["Configure"].primary is False
    assert [m.done for m in view.marks] == [True, True, True, False]


def test_an_app_declaring_no_fields_offers_no_configure_and_counts_as_configured() -> None:
    view = row_view(installed(configured=True), declares_fields=False)
    assert "Configure" not in [a.label for a in view.actions]
    assert view.marks[2].done is True


def test_a_newer_version_replaces_start_with_update() -> None:
    view = row_view(installed(configured=True, available_version="2.0.0"), declares_fields=False)
    labels = [a.label for a in view.actions]
    assert "Update" in labels and "Start" not in labels
    assert view.marks[1].symbol == "↑"
    update = next(a for a in view.actions if a.label == "Update")
    assert update.tool == "update_app" and update.primary is True


def test_each_rail_step_names_its_own_tone() -> None:
    assert [m.tone for m in row_view(running(), declares_fields=True).marks] == [
        "done",
        "done",
        "done",
        "live",
    ]
    assert [m.tone for m in row_view(installed(), declares_fields=True).marks] == [
        "done",
        "done",
        "required",
        "plain",
    ]
    offered = installed(configured=True, available_version="2.0.0")
    assert [m.tone for m in row_view(offered, declares_fields=True).marks] == [
        "done",
        "update",
        "done",
        "plain",
    ]


def test_a_row_with_a_diagnostic_offers_uninstall_only() -> None:
    broken = installed().model_copy(
        update={
            "diagnostic": Diagnostic(
                code="hub.facts_unreadable", category=ErrorCategory.EXECUTION, message="no record"
            )
        }
    )
    view = row_view(broken, declares_fields=False)
    assert [a.label for a in view.actions] == ["Uninstall"]
    assert view.diagnostic is not None and view.diagnostic.code == "hub.facts_unreadable"


def test_a_row_shows_the_wheels_version_not_the_apps_declared_one() -> None:
    view = row_view(installed(), declares_fields=False)
    assert view.version == "1.0.0"


def test_rows_sort_running_first_then_by_name() -> None:
    rows = [available("zeta"), installed("beta"), running("alpha"), available("gamma")]
    assert [r.app_name for r in sort_rows(rows)] == ["alpha", "beta", "gamma", "zeta"]


def test_summary_counts_each_state() -> None:
    assert summary([available(), available("b"), installed("c"), running("d")]) == (2, 1, 1)


FIELDS = [
    ConfigField(name="api_base_url", type="string", required=True),
    ConfigField(name="api_token", type="secret", required=True),
    ConfigField(name="limit", type="integer", required=False),
]


def test_a_save_omits_an_empty_secret_that_is_already_held() -> None:
    entered = {"api_base_url": "https://x", "api_token": "", "limit": ""}
    sent = save_request(FIELDS, entered, ["api_token"])
    assert sent == {"api_base_url": "https://x"}


def test_a_save_omits_a_blank_optional_field_and_sends_a_typed_one() -> None:
    blank = save_request(FIELDS, {"api_base_url": "https://x", "limit": "  "}, ["api_token"])
    typed = save_request(FIELDS, {"api_base_url": "https://x", "limit": "3"}, ["api_token"])
    assert blank == {"api_base_url": "https://x"}
    assert typed == {"api_base_url": "https://x", "limit": "3"}


def test_a_save_sends_a_typed_secret() -> None:
    sent = save_request(FIELDS, {"api_base_url": "https://x", "api_token": "new", "limit": "3"}, [])
    assert sent == {"api_base_url": "https://x", "api_token": "new", "limit": "3"}


def test_a_save_missing_a_required_value_names_every_missing_field() -> None:
    assert save_request(FIELDS, {"api_base_url": "", "api_token": "", "limit": ""}, []) == [
        "api_base_url",
        "api_token",
    ]


def test_a_held_secret_satisfies_its_requirement() -> None:
    assert save_request(FIELDS, {"api_base_url": "https://x", "api_token": ""}, ["api_token"]) == {
        "api_base_url": "https://x"
    }
