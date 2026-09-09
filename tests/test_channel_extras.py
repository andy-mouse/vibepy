"""What an App's environment holds is what the channels it offers require.

The criterion is about an environment rather than a declaration, so this builds
one: `uv sync --package` resolves from `uv.lock`, and `UV_PROJECT_ENVIRONMENT`
sends it somewhere the repository's own environment is not. See
`docs/decisions/ADR-025-the-framework-implements-channel-neutrality-and-delegates-the-rest.md`.
"""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

WEB_TECHNOLOGY = ("nicegui", "fastapi")
"""What `[web]` carries and `[agent]` must not.

`uvicorn` is not in this tuple although the framework imports it in `serve.py`
and declares it in `[web]`: the MCP SDK requires it too — `uvicorn>=0.31.1;
sys_platform != 'emscripten'` in `mcp`'s own metadata — so an environment that
holds MCP holds uvicorn whatever this framework declares. What a library
requires of itself is that library's to state, and a project that reaches into
another's dependencies to remove it is manipulating a resolution rather than
declaring one.
"""


def distributions_in(environment: Path, /) -> set[str]:
    """The distribution names installed in one environment.

    Read from the `.dist-info` directories rather than by running a command in
    the environment, because the interpreter's own path differs between macOS
    and Windows and this needs neither.
    """
    return {
        metadata.name.split("-")[0].lower().replace("_", "-")
        for metadata in environment.rglob("*.dist-info")
    }


def sync(package: str, environment: Path, /) -> None:
    """Install one workspace member's own dependencies into one environment."""
    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = str(environment)
    subprocess.run(
        ["uv", "sync", "--package", package, "--no-dev", "--frozen"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_an_agent_only_apps_environment_holds_no_web_technology(tmp_path: Path) -> None:
    environment = tmp_path / "notes-env"
    sync("vibepy-notes", environment)

    installed = distributions_in(environment)

    assert "vibepy-notes" in installed
    assert "mcp" in installed
    assert [held for held in WEB_TECHNOLOGY if held in installed] == []
