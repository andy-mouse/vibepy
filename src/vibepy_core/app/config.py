"""What an App requires of its host, and where the values come from.

The declaration is a Pydantic settings model: instantiating it reads one
environment variable per field, `VIBEPY_<FIELD>`, and explicit keyword values
stand above the environment field by field. Both are pydantic-settings'
documented behaviour; the framework fixes the prefix here so that every
declaration reads the same variables wherever it is instantiated. See
`docs/decisions/ADR-033-configuration-reaches-a-process-through-the-environment.md`.
"""

import json
from collections.abc import Mapping

from pydantic import JsonValue
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "VIBEPY_"
"""Every configuration variable begins with this."""


class AppConfig(BaseSettings):
    """The base of every App's configuration model.

    Subclass it and declare fields. A window instantiates the subclass; nothing
    else needs to. Extra keys are refused, as `BaseSettings` does by default,
    so a misspelt field fails when the window opens rather than being dropped.
    """

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX)


class NoConfig(AppConfig):
    """The configuration of an App that requires nothing of its host.

    Declared explicitly rather than defaulted, so that one validation path serves
    every App and the framework never guesses that an App needs nothing.
    """


def environment_for(config: Mapping[str, JsonValue], /) -> dict[str, str]:
    """Render held configuration values into the variables a window reads.

    The inverse of the library's decoding: a string verbatim, anything else as
    JSON, which is how pydantic-settings reads a complex field.
    """
    return {
        f"{ENV_PREFIX}{name.upper()}": value if isinstance(value, str) else json.dumps(value)
        for name, value in config.items()
    }
