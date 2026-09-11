"""Reading an App's projected configuration schema, and holding values against it.

The Hub never imports an App, so what it knows about configuration is the JSON
Schema the App's declaration projects. This module reads as much of that schema
as the control plane needs and nothing more.
"""

import logging
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ValidationError

from vibepy_hub.models import AppFacts, ConfigField

logger = logging.getLogger(__name__)


class _SchemaField(BaseModel):
    """One property of a projected configuration schema, as the Hub reads it."""

    format: str | None = None
    type: str | None = None


class _ConfigSchema(BaseModel):
    """As much of a JSON Schema as the control plane reads."""

    properties: dict[str, _SchemaField] = {}
    required: list[str] = []


def secret_fields(schema: Mapping[str, object], /) -> tuple[str, ...]:
    """Return the fields an App declared as secret, read from its projected schema.

    Pydantic projects `SecretStr` as `format: password`, so a Host tells a secret
    from an ordinary string without importing the App.
    """
    try:
        described = _ConfigSchema.model_validate(dict(schema))
    except ValidationError:
        logger.info("unreadable configuration schema")
        return ()
    return tuple(name for name, field in described.properties.items() if field.format == "password")


def held_secrets(values: Mapping[str, object], secrets: Sequence[str], /) -> tuple[str, ...]:
    """Return the declared secrets this App has a value for."""
    return tuple(name for name in secrets if values.get(name) not in (None, ""))


def without_secrets(values: Mapping[str, object], secrets: Sequence[str], /) -> dict[str, object]:
    """Return the held values a channel may see: every field that is not a secret."""
    return {name: value for name, value in values.items() if name not in secrets}


def config_fields(schema: Mapping[str, object], /) -> tuple[ConfigField, ...]:
    """Return every declared field with the type a form renders it as.

    Pydantic projects `SecretStr` as `format: password`, `Path` as
    `format: path` and `int` as `type: integer`; everything else a form
    treats as text, and what it does not recognise it says so rather than
    guessing.
    """
    try:
        described = _ConfigSchema.model_validate(dict(schema))
    except ValidationError:
        logger.info("unreadable configuration schema")
        return ()
    required = set(described.required)
    return tuple(
        ConfigField(name=name, type=_kind(field), required=name in required)
        for name, field in described.properties.items()
    )


def _kind(field: _SchemaField, /) -> str:
    if field.format == "password":
        return "secret"
    if field.format == "path":
        return "path"
    if field.type == "integer":
        return "integer"
    if field.type == "string":
        return "string"
    return "other"


def is_configured(facts: AppFacts, held: Mapping[str, object], /) -> bool:
    """Whether every field an App declared as required has a value."""
    required = _ConfigSchema.model_validate(dict(facts.config_schema)).required
    return all(held.get(name) not in (None, "") for name in required)
