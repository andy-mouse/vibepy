"""The invariant, proven rather than assumed: inspection imports nothing."""

import sys
from pathlib import Path

import pytest

from test_app_package import write_distribution, write_module
from test_describe_command import described_app, run_describe
from vibepy_core.app import discover_apps


def test_discovery_does_not_import_the_app_it_finds(tmp_path: Path) -> None:
    write_distribution(
        tmp_path,
        distribution="untouched-app",
        version="0.1.0",
        entries=[("untouched", "untouched_app.entry:app")],
    )
    write_module(tmp_path, package="untouched_app", attr="app")

    refs = discover_apps(path=[tmp_path])

    assert [ref.app_name for ref in refs] == ["untouched"]
    assert "untouched_app" not in sys.modules
    assert "untouched_app.entry" not in sys.modules


@pytest.mark.integration
def test_a_description_is_obtained_without_this_process_loading_the_app(tmp_path: Path) -> None:
    """Describing imports, and the import happens on the far side of a process
    boundary. What proves it is that this process imported nothing.

    The claim is a delta rather than the absence of `todo_app` from
    `sys.modules`: the sample is a development dependency of this workspace and
    sibling tests import it, so its absence would say more about test order than
    about this command.
    """
    # The name is written out rather than read from `todo_app`, because
    # importing it to derive it is the thing this test forbids.
    before = set(sys.modules)

    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    assert described_app(result, "todo-app")["name"] == "Todo"
    assert set(sys.modules) == before
