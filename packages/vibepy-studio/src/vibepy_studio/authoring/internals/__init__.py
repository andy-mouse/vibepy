"""Authoring's support for finding a project and running inside its environment.

Every operation exported here is `async` or pure: a Tool module awaits one, and
never wraps one itself (`docs/architecture/runtime.md`).
"""

from vibepy_studio.authoring.internals.framework import framework_version
from vibepy_studio.authoring.internals.projects import declared_name, locate, python
from vibepy_studio.authoring.internals.typechecking import TypecheckFailed, typecheck

__all__ = [
    "TypecheckFailed",
    "declared_name",
    "framework_version",
    "locate",
    "python",
    "typecheck",
]
