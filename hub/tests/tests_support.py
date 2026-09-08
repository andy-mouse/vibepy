"""What more than one Hub test needs."""

from contextlib import AbstractAsyncContextManager
from pathlib import Path

from vibepy.app.composition import tool_runtime_for
from vibepy.tool import ToolRuntime
from vibepy_hub.entry import APP, HUB_APP
from vibepy_hub.internals import HubDeps

REPO = Path(__file__).resolve().parents[2]
SAMPLES = REPO / "samples"


def hub(root: Path, /) -> AbstractAsyncContextManager[ToolRuntime[HubDeps]]:
    """One Hub window over a temporary root."""
    return tool_runtime_for(HUB_APP, APP.lifespan, config={"root": str(root)})


def write_project(folder: Path, *, name: str, declares: bool) -> None:
    """A project file like the one an App's own repository carries."""
    folder.mkdir(parents=True)
    declaration = '\n[project.entry-points."vibepy.apps"]\ndemo = "demo.entry:APP"\n'
    (folder / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "1.2.3"\n' + (declaration if declares else ""),
        encoding="utf-8",
    )
