"""The two headline invariants, proven rather than read.

No MCP type reaches the core Tool model and no Web type reaches the core Page
model. `AGENTS.md` states both, and the package root is where an SDK import
would reach every consumer, so the scan covers every core module rather than
three packages.

A channel component is exempt because being one is its job: `adapters/` holds
the two adapters, and `serve.py` is the command `docs/architecture/packaging.md`
documents as the one that opens an App's Web channel.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parent.parent / "src" / "vibepy_core"
CHANNEL_SDKS = ("mcp", "nicegui")
CHANNEL_COMPONENTS = frozenset({"adapters", "serve.py"})


def core_modules() -> list[Path]:
    """Every module of the core that is not a channel component."""
    return sorted(
        module
        for module in CORE.rglob("*.py")
        if not CHANNEL_COMPONENTS & set(module.relative_to(CORE).parts)
    )


def imported_module_names(source: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_the_scan_reaches_the_package_root_and_the_error_model() -> None:
    """A guard is worth what it covers, so what it covers is asserted too."""
    covered = {module.relative_to(CORE).as_posix() for module in core_modules()}

    assert {
        "__init__.py",
        "errors.py",
        "describe.py",
        "tool/model.py",
        "page/model.py",
        "app/model.py",
    } <= covered
    assert "serve.py" not in covered
    assert not any(name.startswith("adapters/") for name in covered)


@pytest.mark.parametrize("sdk", CHANNEL_SDKS)
def test_no_core_module_imports_a_channel_sdk(sdk: str) -> None:
    offenders = [
        module.relative_to(CORE).as_posix()
        for module in core_modules()
        for name in imported_module_names(module.read_text(encoding="utf-8"))
        if name == sdk or name.startswith(f"{sdk}.")
    ]

    assert offenders == []


def test_importing_the_core_loads_no_channel_sdk() -> None:
    """What a static scan cannot see: an SDK reached through another import."""
    probe = (
        "import json, sys; import vibepy_core; "
        "sys.stdout.write(json.dumps(sorted("
        "{module.split('.')[0] for module in sys.modules} "
        f"& set({list(CHANNEL_SDKS)!r}))))"
    )
    finished = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr
    assert json.loads(finished.stdout) == []
