"""A Hub Tool handler does no blocking work, and cannot start doing it again.

`docs/architecture/runtime.md` puts blocking calls behind `asyncio.to_thread`,
and the Hub's own ruff configuration refuses an import of a blocking module
from `tools/`. What neither reaches is a blocking method called on a value whose
type is declared elsewhere, which is what this asserts.
"""

import ast
from pathlib import Path

import pytest

BLOCKING = frozenset(
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
