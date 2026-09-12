"""What does not conform in a source project, read in the project's own environment."""

from pathlib import Path

import pytest

from tests_support import AGENT, FIXTURES, broken_project, studio, warning_project
from vibepy_core import Channel, ErrorCategory
from vibepy_studio.authoring.models import AppValidation, Severity


@pytest.mark.integration
async def test_a_conforming_project_conforms(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        validated = await tools.invoke(
            "validate_app", {"project": str(FIXTURES / "todo-app")}, principal=AGENT
        )
    assert isinstance(validated, AppValidation)
    assert validated.conforms, validated.diagnostics
    assert [d for d in validated.diagnostics if d.severity is Severity.ERROR] == []


@pytest.mark.integration
async def test_every_violation_and_every_type_error_is_one_diagnostic(tmp_path: Path) -> None:
    project = broken_project(tmp_path / "broken")
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        validated = await tools.invoke("validate_app", {"project": str(project)}, principal=AGENT)
    assert isinstance(validated, AppValidation)
    assert not validated.conforms
    codes = [d.error.code for d in validated.diagnostics]
    assert codes[:3] == ["tool.name_conflict", "page.route_invalid", "page.tool_unresolved"]
    assert "app.declaration_invalid" not in codes
    typed = [d for d in validated.diagnostics if d.error.code == "authoring.type_error"]
    assert typed, codes
    assert all(d.severity is Severity.ERROR for d in validated.diagnostics[:3])
    first = typed[0].error
    assert first.category is ErrorCategory.DECLARATION
    assert first.details["file"].endswith("entry.py")
    assert first.details["line"].isdigit()
    assert first.details.get("rule") == "reportArgumentType"


@pytest.mark.integration
async def test_a_pyright_warning_conforms_but_is_still_reported(tmp_path: Path) -> None:
    project = warning_project(tmp_path / "warning")
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        validated = await tools.invoke("validate_app", {"project": str(project)}, principal=AGENT)
    assert isinstance(validated, AppValidation)
    assert validated.conforms is True
    typed = [d for d in validated.diagnostics if d.error.code == "authoring.type_error"]
    assert typed
    assert all(d.severity is Severity.WARNING for d in typed)
    assert typed[0].error.details["rule"] == "reportUnusedImport"


async def test_a_directory_without_a_pyproject_is_not_a_project(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        validated = await tools.invoke(
            "validate_app", {"project": str(tmp_path / "nowhere")}, principal=AGENT
        )
    assert isinstance(validated, AppValidation)
    assert not validated.conforms
    assert [d.error.code for d in validated.diagnostics] == ["authoring.project_not_found"]
