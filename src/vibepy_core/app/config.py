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
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, JsonValue, SecretStr
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


class ConfigFieldType(StrEnum):
    """What a configuration field holds, as much of it as a form needs.

    Derived from the declared annotation rather than from the projected schema,
    so a reader learns a field is a secret without reading JSON Schema.
    """

    STRING = "string"
    PATH = "path"
    INTEGER = "integer"
    SECRET = "secret"
    OTHER = "other"


class ConfigFieldDescription(BaseModel):
    """One field an App declares: its name, what it holds, and whether it is required."""

    name: str
    type: ConfigFieldType
    required: bool


_FIELD_TYPES: Mapping[type, ConfigFieldType] = {
    SecretStr: ConfigFieldType.SECRET,
    Path: ConfigFieldType.PATH,
    int: ConfigFieldType.INTEGER,
    str: ConfigFieldType.STRING,
}
"""The annotations a reader of a declaration recognises. Anything else is `OTHER`."""


def config_fields_of(model: type[AppConfig], /) -> list[ConfigFieldDescription]:
    """Describe every field a configuration model declares, in declaration order."""
    return [
        ConfigFieldDescription(
            name=name,
            type=_FIELD_TYPES.get(field.annotation, ConfigFieldType.OTHER)
            if isinstance(field.annotation, type)
            else ConfigFieldType.OTHER,
            required=field.is_required(),
        )
        for name, field in model.model_fields.items()
    ]


def environment_for(config: Mapping[str, JsonValue], /) -> dict[str, str]:
    """Render held configuration values into the variables a window reads.

    The inverse of the library's decoding: a string verbatim, anything else as
    JSON, which is how pydantic-settings reads a complex field.
    """
    return {
        f"{ENV_PREFIX}{name.upper()}": value if isinstance(value, str) else json.dumps(value)
        for name, value in config.items()
    }
