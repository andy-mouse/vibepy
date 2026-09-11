"""A Hub Page reaches Hub Core only through Tool invocation, never by importing it directly.

`docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md` says "a Hub UI consumes those Tools as
any Page consumes Tools, so it cannot duplicate control-plane logic." This test holds that
boundary at the import level: no module under `vibepy_studio/pages/` may import
`vibepy_studio.consumption.internals`, `vibepy_studio.consumption.tools`, or
`vibepy_core.tool` — a Page's whole reach into Hub Core is `ctx.tools.invoke`.
"""

from pathlib import Path

import pytest

from test_no_blocking_handlers import imported

PAGES = Path(__file__).resolve().parents[1] / "src" / "vibepy_studio" / "pages"

FORBIDDEN_IMPORTS = frozenset(
    {
        "vibepy_studio.consumption.internals",
        "vibepy_studio.consumption.tools",
        "vibepy_core.tool",
    }
)
"""What a Page module may never import: Hub Core's internals, its Tool modules, and the
framework's Tool machinery. A Page reaches Hub Core only through `ctx.tools.invoke`."""


@pytest.mark.parametrize("module", sorted(PAGES.glob("*.py")), ids=lambda path: path.name)
def test_a_page_reaches_hub_core_only_through_tool_invocation(module: Path) -> None:
    assert imported(module.read_text(encoding="utf-8")) & FORBIDDEN_IMPORTS == set()
