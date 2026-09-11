"""The name an App's declaration is filed under, and nothing else.

A module of its own because both ends of the declaration read it: `package`,
which enumerates an environment, and a host reading a wheel's `entry_points.txt`
without an environment at all. `package` imports `importlib.metadata` and
blocks; a reader that needs only the name must not have to.
"""

APP_GROUP = "vibepy.apps"
"""The entry point group an App declares itself in.

A group name is metadata read as a string and imports nothing, so it claims no
distribution name on any index.
"""
