"""What a started App is told about the world it runs in."""

import os
import sys
from pathlib import Path

import pytest

from tests_support import SAMPLES, hub
from vibepy_hub.installer import environment, interpreter, purelib
from vibepy_hub.processes import DESCRIBES_THIS_PROCESS, child_environment


def test_what_describes_this_process_is_not_passed_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIRTUAL_ENV", "/somewhere/else/.venv")
    monkeypatch.setenv("PYTHONPATH", "/somewhere/else")
    monkeypatch.setenv("HOME", "/home/someone")

    composed = child_environment()

    assert set(composed) & DESCRIBES_THIS_PROCESS == set()
    assert composed["HOME"] == "/home/someone"


def test_a_running_test_is_not_passed_on() -> None:
    assert "PYTEST_CURRENT_TEST" in os.environ
    assert "PYTEST_CURRENT_TEST" not in child_environment()


async def test_an_environment_reports_its_own_metadata_directory(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(SAMPLES)})
        await tools.invoke("install_app", {"app_name": "todo"})

    env = environment(root, "todo")
    reported = await purelib(env)

    assert reported.is_dir()
    assert (reported / "vibepy_todo-0.1.0.dist-info").is_dir()
    assert reported.is_relative_to(env)
    assert interpreter(env).is_file()
    assert reported != Path(sys.prefix)
