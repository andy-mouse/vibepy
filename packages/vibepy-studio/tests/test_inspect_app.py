"""What a source project declares, read in the project's own environment."""

from pathlib import Path

import pytest

from tests_support import AGENT, FIXTURES, broken_project, studio
from vibepy_core import Channel, ErrorCategory
from vibepy_studio.authoring.models import AppInspection, InspectRequest


@pytest.mark.integration
async def test_a_project_is_inspected_with_its_tools_pages_and_config(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        inspected = await tools.invoke(
            "inspect_app", {"project": str(FIXTURES / "todo-app")}, principal=AGENT
        )
    assert isinstance(inspected, AppInspection)
    assert inspected.diagnostics == [], inspected.diagnostics
    assert [app.app_name for app in inspected.apps] == ["todo-app"]
    todo = inspected.apps[0]
    assert sorted(tool.name for tool in todo.description.tools) == [
        "complete_todo",
        "create_todo",
        "list_todos",
    ]
    assert [page.route for page in todo.description.pages] == ["/todos"]
    assert set(todo.description.config_schema["properties"]) == {"db_path", "db_key"}  # type: ignore[index]


async def test_a_directory_without_a_pyproject_is_not_a_project(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        inspected = await tools.invoke(
            "inspect_app", {"project": str(tmp_path / "nowhere")}, principal=AGENT
        )
    assert isinstance(inspected, AppInspection)
    assert inspected.apps == []
    assert [d.code for d in inspected.diagnostics] == ["authoring.project_not_found"]
    assert inspected.diagnostics[0].category == ErrorCategory.CALLER


@pytest.mark.integration
async def test_a_project_whose_environment_lacks_the_framework_fails_as_an_environment(
    tmp_path: Path,
) -> None:
    project = tmp_path / "plain"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "plain"\nversion = "0.0.0"\nrequires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        inspected = await tools.invoke("inspect_app", {"project": str(project)}, principal=AGENT)
    assert isinstance(inspected, AppInspection)
    assert [d.code for d in inspected.diagnostics] == ["authoring.environment_failed"]
    assert inspected.diagnostics[0].category == ErrorCategory.EXECUTION
    assert "vibepy_core" in inspected.diagnostics[0].message


def test_the_project_a_request_names_reaches_no_file_system() -> None:
    """The path a handler is handed is a `PurePath`, so it offers nothing that blocks."""
    request = InspectRequest.model_validate({"project": "/somewhere/a-project"})

    assert not hasattr(request.project, "is_dir")


@pytest.mark.integration
async def test_an_invalid_declaration_is_inspected_as_every_violation(tmp_path: Path) -> None:
    project = broken_project(tmp_path / "broken")
    async with studio(tmp_path / "studio", channel=Channel.AGENT) as tools:
        inspected = await tools.invoke("inspect_app", {"project": str(project)}, principal=AGENT)
    assert isinstance(inspected, AppInspection)
    assert inspected.apps == []
    assert [d.code for d in inspected.diagnostics] == [
        "app.declaration_invalid",
        "tool.name_conflict",
        "page.route_invalid",
        "page.tool_unresolved",
    ]
