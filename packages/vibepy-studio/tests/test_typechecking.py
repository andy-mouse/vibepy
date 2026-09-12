"""The command Studio type-checks a project with."""

import importlib.metadata
import sys
from pathlib import PurePath

from vibepy_studio.authoring.internals.typechecking import command


def test_command_type_checks_project_against_its_interpreter() -> None:
    """`command` runs Studio's own pyright module, pointed at the project's interpreter."""
    assert command(PurePath("/p"), PurePath("/p/.venv/bin/python")) == [
        sys.executable,
        "-m",
        "pyright",
        "--outputjson",
        "--pythonpath",
        "/p/.venv/bin/python",
        "-p",
        "/p",
        "/p",
    ]


def test_studios_own_environment_provides_pyright() -> None:
    """pyright is a declared dependency of Studio, so it is installed alongside it."""
    importlib.metadata.version("pyright")
