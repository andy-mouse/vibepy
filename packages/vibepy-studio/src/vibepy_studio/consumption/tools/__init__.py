"""The Hub's public operations, one module per lifecycle it manages.

Each Tool is one affordance of the control plane. The work they call — reading a
folder, running `uv`, holding a child process, reading and writing the state
file — is domain internals and is not published as a Tool.

Package installation and runtime are different lifecycles, and each has a module
of its own here.
"""

from collections.abc import Sequence

from vibepy_core.tool import Tool
from vibepy_studio.consumption.tools.configuration import (
    CONFIGURATION_TOOLS,
    configure_app,
    describe_config,
)
from vibepy_studio.consumption.tools.installation import (
    INSTALLATION_TOOLS,
    install_app,
    list_apps,
    remove_app,
    update_app,
)
from vibepy_studio.consumption.tools.packages import (
    PACKAGE_SOURCE_TOOLS,
    register_package_source,
    remove_package_source,
)
from vibepy_studio.consumption.tools.runtime import RUNTIME_TOOLS, start_app, stop_app
from vibepy_studio.internals import StudioDeps

HUB_TOOLS: Sequence[Tool[StudioDeps]] = [
    *PACKAGE_SOURCE_TOOLS,
    *INSTALLATION_TOOLS,
    *CONFIGURATION_TOOLS,
    *RUNTIME_TOOLS,
]

__all__ = [
    "HUB_TOOLS",
    "configure_app",
    "describe_config",
    "install_app",
    "list_apps",
    "register_package_source",
    "remove_app",
    "remove_package_source",
    "start_app",
    "stop_app",
    "update_app",
]
