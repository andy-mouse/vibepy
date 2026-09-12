"""An operating Page reaches the operating role's core only through Tool invocation, never by
importing it directly.

`docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md` says "a Hub UI consumes those Tools as
any Page consumes Tools, so it cannot duplicate control-plane logic." This test holds that
boundary at the import level: no module under `vibepy_studio/pages/` may import
`vibepy_studio.operating.internals`, `vibepy_studio.operating.tools`, or
`vibepy_core.tool` — a Page's whole reach into the operating role's core is `ctx.tools.invoke`.
"""

import ast
from pathlib import Path

import pytest

PAGES = Path(__file__).resolve().parents[1] / "src" / "vibepy_studio" / "operating" / "pages"

FORBIDDEN_IMPORTS = frozenset(
    {
        "vibepy_studio.operating.internals",
        "vibepy_studio.operating.tools",
        "vibepy_core.tool",
    }
)
"""What a Page module may never import: the operating role's core internals, its Tool modules, and
the framework's Tool machinery. A Page reaches the operating role's core only through
`ctx.tools.invoke`."""


def imported(source: str, /) -> set[str]:
    """Every module this source imports, by the name it imports it from."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
    return found


def test_the_import_surface_sees_a_forbidden_import() -> None:
    """A guard that cannot fail is not a guard."""
    assert imported("from vibepy_core.tool import Tool\n") & FORBIDDEN_IMPORTS != set()


@pytest.mark.parametrize("module", sorted(PAGES.glob("*.py")), ids=lambda path: path.name)
def test_a_page_reaches_hub_core_only_through_tool_invocation(module: Path) -> None:
    assert imported(module.read_text(encoding="utf-8")) & FORBIDDEN_IMPORTS == set()
