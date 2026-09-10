"""The two headline invariants, where a linter cannot reach.

No MCP type reaches the core Tool model and no Web type reaches the core Page
model. The static half is `TID251` in `pyproject.toml`, which reads every core
module and exempts the two channel components; a rule a tool enforces is not
re-implemented as a test here.

What a static rule cannot see is an SDK reached through another import rather
than named in the file. That is behaviour, and it is what this checks.
`test_app_isolation.py` uses the same technique for the same reason.
"""

import json
import subprocess
import sys

import pytest

CHANNEL_SDKS = ("mcp", "nicegui")


@pytest.mark.integration
def test_importing_the_core_loads_no_channel_sdk() -> None:
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
