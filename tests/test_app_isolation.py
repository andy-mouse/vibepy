"""The invariant, proven rather than assumed: inspection imports nothing."""

import sys
from pathlib import Path

from tests.test_app_package import write_distribution, write_module
from tests.test_describe_command import described_app, run_describe
from vibepy.app import discover_apps


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


def test_a_description_is_obtained_without_this_process_loading_the_app(tmp_path: Path) -> None:
    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    assert described_app(result, "todo-app")["name"] == "Todo"
