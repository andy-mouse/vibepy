"""The command that describes an App from inside its own environment."""

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.test_app_package import write_distribution

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_describe(environment_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the command with an extra environment on the path, as a host would."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(environment_root), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "vibepy.describe"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def declare_todo(root: Path) -> None:
    write_distribution(
        root,
        distribution="todo-fixture-app",
        version="9.9.9",
        entries=[("todo", "tests.todo_fixture:TODO_ENTRYPOINT")],
    )


def test_the_command_writes_a_description_of_every_declared_app(tmp_path: Path) -> None:
    declare_todo(tmp_path)

    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    described = json.loads(result.stdout)
    assert len(described) == 1
    assert described[0]["app_id"] == "todo-app"
    assert described[0]["version"] == "0.0.0"
    assert sorted(described[0]["config_schema"]["properties"]) == ["db_path"]
    assert [tool["name"] for tool in described[0]["tools"]] == ["create_todo", "list_todos"]
    assert [page["route"] for page in described[0]["pages"]] == ["/todos"]


def test_an_environment_declaring_no_app_describes_nothing(tmp_path: Path) -> None:
    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_an_unloadable_declaration_fails_with_the_framework_code(tmp_path: Path) -> None:
    write_distribution(
        tmp_path,
        distribution="broken-app",
        version="0.1.0",
        entries=[("broken", "no_such_module_anywhere:app")],
    )

    result = run_describe(tmp_path)

    assert result.returncode == 1
    assert "package.entrypoint_unloadable" in result.stderr
