"""A Hub Tool handler does no blocking work, and cannot start doing it again.

`docs/architecture/runtime.md` puts blocking calls behind `asyncio.to_thread`.
Two guards, because a blocking call arrives two ways:

- through an *import*, whether of a blocking module or of one that merely holds
  a blocking function, as `vibepy_core.app.package` holds `discover_apps`. Both
  are closed by what a Tool module may import at all. A denylist cannot do this:
  it stops the modules someone thought to name, and `discover_apps` is what
  arrives when nobody thought to name one.
- through a blocking *method* called on a value whose type is declared
  elsewhere, which is the shape the original defect took and which no import
  rule can see.

Each guard has a test that it can fail. A guard that cannot fail is not a guard.

`import-linter` is the ecosystem's tool for import contracts and does not
express this one: its contracts are `forbidden` (a denylist), `protected` (an
allowlist of importers, which is the other direction), `independence`, `layers`
and `acyclic_siblings`
(<https://import-linter.readthedocs.io/en/v2.7/contract_types.html>). None says
"this module imports only these".
"""

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src" / "vibepy_studio"
TOOLS = (_SRC / "operating" / "tools", _SRC / "authoring" / "tools")

ALLOWED_IMPORTS = frozenset(
    {
        "collections.abc",
        "logging",
        "packaging.utils",
        "packaging.version",
        "pathlib",
        "vibepy_core.app.config",
        "vibepy_core.app.group",
        "vibepy_core.errors",
        "vibepy_core.invoke",
        "vibepy_core.tool",
        "vibepy_studio.operating.internals",
        "vibepy_studio.operating.models",
        "vibepy_studio.models",
        "asyncio",
        "json",
        "importlib.metadata",
        "pydantic",
        "vibepy_studio.authoring.internals",
        "vibepy_studio.authoring.models",
        "vibepy_studio.internals",
    }
)
"""What a Tool module may import: a closed list, not a filtered one.

`docs/architecture.md` puts an App's filesystem, process and metadata work in
its internals, and `AGENTS.md` has a handler reach them through its ToolContext.
So this list admits only modules that cannot carry a blocking call into a
handler: the standard library's own non-blocking parts, pure parsing and
modelling libraries, the framework's Tool and error vocabulary, a framework
module holding one constant and nothing else, `vibepy_core.app.config`, which
holds `environment_for` and nothing blocking, Studio's own models, and the two
roles' internals packages -- of which the shared one,
`vibepy_studio.internals`, exports only async operations and pure functions
over text already read.

`vibepy_core` itself is not on the list: its root package re-exports
`discover_apps`, `describe_app` and `load_app`, all blocking, so a bare
`vibepy_core` import would defeat the guard. Neither is
`vibepy_core.app.package`, which holds them.

Widening this is a decision about the architecture, which is why it is spelled
out and not derived: what earns a place is a module with nothing to block on,
and a module that has something is made to stop having it instead.
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
        if module not in ALLOWED_IMPORTS
        and not module.startswith("vibepy_studio.operating.tools.")
        and not module.startswith("vibepy_studio.authoring.tools.")
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


_MODULES = sorted(
    (directory.parent.name, path) for directory in TOOLS for path in directory.glob("*.py")
)


@pytest.mark.parametrize(
    ("role", "module"), _MODULES, ids=[f"{role}/{path.name}" for role, path in _MODULES]
)
def test_a_tool_module_imports_only_what_a_handler_may_reach(role: str, module: Path) -> None:
    assert unreachable(module.read_text(encoding="utf-8")) == set()


@pytest.mark.parametrize(
    ("role", "module"), _MODULES, ids=[f"{role}/{path.name}" for role, path in _MODULES]
)
def test_a_tool_module_makes_no_blocking_call(role: str, module: Path) -> None:
    assert blocking_calls(module.read_text(encoding="utf-8")) == []


def test_the_import_surface_sees_a_module_a_handler_may_not_reach() -> None:
    """The route `discover_apps` took: a blocking function behind a name that
    says nothing about blocking."""
    assert unreachable("from vibepy_core.app.package import discover_apps\n") == {
        "vibepy_core.app.package"
    }


def test_the_call_guard_sees_a_blocking_method() -> None:
    assert blocking_calls("async def h(p):\n    return p.is_dir()\n") == ["is_dir"]


def test_the_import_surface_sees_vibepy_core_itself_as_unreachable() -> None:
    """The route a widened guard would have missed: `vibepy_core`'s root
    re-exports `discover_apps`, a blocking function, under a bare import."""
    assert unreachable("from vibepy_core import discover_apps\n") != set()
