"""Authoring's support for finding a project and running inside its environment.

Every operation exported here is `async` or pure: a Tool module awaits one, and
never wraps one itself (`docs/architecture/runtime.md`).
"""

from vibepy_studio.authoring.internals.framework import framework_version
from vibepy_studio.authoring.internals.projects import declared_name, locate, python

__all__ = ["declared_name", "framework_version", "locate", "python"]
