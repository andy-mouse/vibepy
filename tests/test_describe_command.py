"""The command that describes an App from inside its own environment."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_app_entrypoint import properties
from test_app_package import write_distribution
from vibepy_core.app import DescribedApp

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_describe(environment_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the command with an extra environment on the path, as a host would."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(environment_root), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "vibepy_core.describe"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def described_apps(result: subprocess.CompletedProcess[str]) -> list[DescribedApp]:
    """Everything the environment declared, read as the type the command writes."""
    entries: list[object] = json.loads(result.stdout)
    return [DescribedApp.model_validate(entry) for entry in entries]


def described_app(result: subprocess.CompletedProcess[str], app_id: str) -> DescribedApp:
    """One App out of everything the environment declares.

    The environment declares more than one App, so a test names the one it is
    about rather than asserting how many there are.
    """
    described = described_apps(result)
    found = [entry for entry in described if entry.description.app_id == app_id]
    assert found, f"{app_id} was not described: {[entry.description.app_id for entry in described]}"
    return found[0]


@pytest.mark.integration
def test_the_command_writes_a_description_of_every_declared_app(tmp_path: Path) -> None:
    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    todo = described_app(result, "todo-app")
    assert todo.description.version == "0.0.0"
    assert sorted(properties(todo.description.config_schema)) == ["db_key", "db_path"]
    assert [tool.name for tool in todo.description.tools] == [
        "create_todo",
        "list_todos",
        "complete_todo",
    ]
    assert [page.route for page in todo.description.pages] == ["/todos"]
    assert described_app(result, "notes-app").description.pages == []


@pytest.mark.integration
def test_a_distribution_declaring_no_app_describes_nothing(tmp_path: Path) -> None:
    before = {entry.description.app_id for entry in described_apps(run_describe(tmp_path))}
    dist_info = tmp_path / "plain-1.0.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: plain\nVersion: 1.0.0\n", encoding="utf-8"
    )

    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    assert {entry.description.app_id for entry in described_apps(result)} == before


@pytest.mark.integration
def test_an_unloadable_declaration_fails_with_the_framework_code(tmp_path: Path) -> None:
    write_distribution(
        tmp_path,
        distribution="broken-app",
        version="0.1.0",
        entries=[("broken", "no_such_module_anywhere:app")],
    )

    result = run_describe(tmp_path)

    assert result.returncode == 1
    reported = json.loads(result.stderr)
    assert reported["code"] == "package.entrypoint_unloadable"
    assert reported["category"] == "declaration"
    assert set(reported) == {"code", "category", "message", "details"}


@pytest.mark.integration
def test_a_description_says_which_declaration_it_describes(tmp_path: Path) -> None:
    """A reader joins two answers about one environment on identity, so the
    command reports the identity of what it described."""
    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    described = described_app(result, "todo-app")
    assert described.app_name == "todo-app"
    assert described.distribution == "vibepy-todo"
    assert described.distribution_version == "0.1.0"
