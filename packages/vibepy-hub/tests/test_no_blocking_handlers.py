"""A Hub Tool handler does no blocking work, and cannot start doing it again.

`docs/architecture/runtime.md` puts blocking calls behind `asyncio.to_thread`,
and the Hub's own ruff configuration refuses an import of a blocking module
from `tools/`. Two things neither reaches: a blocking method called on a value
whose type is declared elsewhere, and a blocking function reached through a
module that is not itself a blocking one -- `discover_apps` scans a directory
and arrives from `vibepy_core`. Both are what this asserts.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

BLOCKING = frozenset(
    {
        "chmod",
        "discover_apps",
        "exists",
        "glob",
        "is_dir",
        "is_file",
        "iterdir",
        "mkdir",
        "open",
        "read_bytes",
        "read_text",
        "rmdir",
        "rmtree",
        "stat",
        "unlink",
        "write_bytes",
        "write_text",
    }
)

TOOLS = Path(__file__).resolve().parents[1] / "src" / "vibepy_hub" / "tools"


def blocking_calls(source: str, /) -> list[str]:
    """Every blocking call this module makes, by the name it calls."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        name = (
            called.attr
            if isinstance(called, ast.Attribute)
            else called.id
            if isinstance(called, ast.Name)
            else ""
        )
        if name in BLOCKING:
            found.append(name)
    return found


@pytest.mark.parametrize("module", sorted(TOOLS.glob("*.py")), ids=lambda path: path.name)
def test_a_tool_module_makes_no_blocking_call(module: Path) -> None:
    assert blocking_calls(module.read_text(encoding="utf-8")) == []


def test_the_guard_sees_a_blocking_call() -> None:
    """A guard that cannot fail is not a guard."""
    assert blocking_calls("async def h(p):\n    return p.is_dir()\n") == ["is_dir"]


def test_the_import_ban_fires_for_a_tool_module() -> None:
    """The other guard, asserted the same way: a ban nothing exercises is a ban
    that can stop matching without anyone noticing.

    `--stdin-filename` is how ruff is told which configuration and which
    per-file rules apply to text it reads
    (<https://docs.astral.sh/ruff/configuration/>), so this asks the real
    configuration about a path under `tools/` without writing a file there.
    """
    banned = _ruff_codes(TOOLS / "_probe.py")
    allowed = _ruff_codes(TOOLS.parent / "internals" / "_probe.py")

    assert "TID251" in banned
    assert "TID251" not in allowed


def _ruff_codes(pretend_to_be: Path, /) -> set[str]:
    """Every rule ruff reports for one blocking import at that path."""
    finished = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--output-format",
            "concise",
            "--stdin-filename",
            str(pretend_to_be),
            "-",
        ],
        input="import shutil\n\nshutil.rmtree\n",
        capture_output=True,
        text=True,
        check=False,
        cwd=TOOLS.parents[3],
    )
    return {
        word for line in finished.stdout.splitlines() for word in line.split() if word.isupper()
    }
