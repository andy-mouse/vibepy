"""A Hub Tool handler does no blocking work, and cannot start doing it again.

`docs/architecture/runtime.md` puts blocking calls behind `asyncio.to_thread`.
Three guards, because one blocking call can arrive by three routes and no single
mechanism sees all three:

- an *import* of a blocking module -- ruff's `banned-api`, checked here so that
  a rule that stops matching is noticed;
- a blocking function reached through a module that is not itself named for
  blocking, as `discover_apps` is -- closed by what a Tool module may import at
  all, rather than by naming each such function as it is discovered;
- a blocking *method* called on a value whose type is declared elsewhere, which
  is the shape the original defect took and which no import rule can see.

Each guard has a test that it can fail. A guard that cannot fail is not a guard.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "src" / "vibepy_hub" / "tools"
REPO = TOOLS.parents[3]

ALLOWED_IMPORTS = frozenset(
    {
        "collections.abc",
        "logging",
        "packaging.utils",
        "vibepy_core.errors",
        "vibepy_core.tool",
        "vibepy_hub.internals",
        "vibepy_hub.models",
    }
)
"""What a Tool module may import.

`docs/architecture.md` puts an App's filesystem, process and metadata work in
its internals, and `AGENTS.md` has a handler reach them through its ToolContext.
So the surface is closed rather than filtered: a blocking function cannot arrive
here, because the module holding it is not on this list. Widening it is a
decision about the architecture, which is why it is spelled out and not derived.
"""

BLOCKING_METHODS = frozenset(
    {
        "chmod",
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
"""Blocking calls a value carries with it, which the import guards cannot see."""


def unreachable(source: str, /) -> set[str]:
    """Every module this source imports that a Tool handler may not reach.

    A Tool module may import its siblings: that is how `tools/__init__.py`
    assembles the package, and a sibling is held to this same rule.
    """
    return {
        module
        for module in imported(source)
        if module not in ALLOWED_IMPORTS and not module.startswith("vibepy_hub.tools.")
    }


def imported(source: str, /) -> set[str]:
    """Every module this source imports, by the name it imports it from."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
    return found


def blocking_calls(source: str, /) -> list[str]:
    """Every blocking call this source makes, by the name it calls."""
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
        if name in BLOCKING_METHODS:
            found.append(name)
    return found


def ruff_codes(pretend_to_be: Path, /) -> set[str]:
    """Every rule ruff reports for one blocking import at that path.

    `--stdin-filename` is how ruff is told which configuration and which
    per-file rules apply to text it reads
    (<https://docs.astral.sh/ruff/configuration/>), so this asks the real
    configuration about a path under `tools/` without writing a file there.
    """
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
        cwd=REPO,
    )
    return {
        word for line in finished.stdout.splitlines() for word in line.split() if word.isupper()
    }


@pytest.mark.parametrize("module", sorted(TOOLS.glob("*.py")), ids=lambda path: path.name)
def test_a_tool_module_imports_only_what_a_handler_may_reach(module: Path) -> None:
    assert unreachable(module.read_text(encoding="utf-8")) == set()


@pytest.mark.parametrize("module", sorted(TOOLS.glob("*.py")), ids=lambda path: path.name)
def test_a_tool_module_makes_no_blocking_call(module: Path) -> None:
    assert blocking_calls(module.read_text(encoding="utf-8")) == []


def test_the_import_ban_fires_for_a_tool_module() -> None:
    assert "TID251" in ruff_codes(TOOLS / "_probe.py")
    assert "TID251" not in ruff_codes(TOOLS.parent / "internals" / "_probe.py")


def test_the_import_surface_sees_a_module_a_handler_may_not_reach() -> None:
    """The route `discover_apps` took: a blocking function behind a name that
    says nothing about blocking."""
    assert unreachable("from vibepy_core.app.package import discover_apps\n") == {
        "vibepy_core.app.package"
    }


def test_the_call_guard_sees_a_blocking_method() -> None:
    assert blocking_calls("async def h(p):\n    return p.is_dir()\n") == ["is_dir"]
