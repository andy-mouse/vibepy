"""What a source project declares, read in the project's own environment."""

from pathlib import Path

import pytest

from tests_support import FIXTURES, studio
from vibepy_core import ErrorCategory
from vibepy_studio.authoring.models import AppInspection


@pytest.mark.integration
async def test_a_project_is_inspected_with_its_tools_pages_and_config(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        inspected = await tools.invoke("inspect_app", {"project": str(FIXTURES / "todo-app")})
    assert isinstance(inspected, AppInspection)
    assert inspected.diagnostic is None, inspected.diagnostic
    assert [app.app_name for app in inspected.apps] == ["todo-app"]
    todo = inspected.apps[0]
    assert sorted(tool.name for tool in todo.tools) == [
        "complete_todo",
        "create_todo",
        "list_todos",
    ]
    assert [page.route for page in todo.pages] == ["/todos"]
    assert set(todo.config_schema["properties"]) == {"db_path", "db_key"}  # type: ignore[index]


async def test_a_directory_without_a_pyproject_is_not_a_project(tmp_path: Path) -> None:
    async with studio(tmp_path / "studio") as tools:
        inspected = await tools.invoke("inspect_app", {"project": str(tmp_path / "nowhere")})
    assert isinstance(inspected, AppInspection)
    assert inspected.apps == []
    assert inspected.diagnostic is not None
    assert inspected.diagnostic.code == "authoring.project_not_found"
    assert inspected.diagnostic.category == ErrorCategory.CALLER


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
    async with studio(tmp_path / "studio") as tools:
        inspected = await tools.invoke("inspect_app", {"project": str(project)})
    assert isinstance(inspected, AppInspection)
    assert inspected.diagnostic is not None
    assert inspected.diagnostic.code == "authoring.environment_failed"
    assert inspected.diagnostic.category == ErrorCategory.EXECUTION
    assert "vibepy_core" in inspected.diagnostic.message
