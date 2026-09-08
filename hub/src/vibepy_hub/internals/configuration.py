"""Reading an App's projected configuration schema, and holding values against it.

The Hub never imports an App, so what it knows about configuration is the JSON
Schema the App's declaration projects. This module reads as much of that schema
as the control plane needs and nothing more.
"""

import logging
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ValidationError

from vibepy_hub.models import SET, AppFacts

logger = logging.getLogger(__name__)


class _SchemaField(BaseModel):
    """One property of a projected configuration schema, as the Hub reads it."""

    format: str | None = None


class _ConfigSchema(BaseModel):
    """As much of a JSON Schema as the control plane reads."""

    properties: dict[str, _SchemaField] = {}
    required: list[str] = []


def secret_fields(schema: Mapping[str, object], /) -> tuple[str, ...]:
    """The fields an App declared as secret, read from its projected schema.

    Pydantic projects `SecretStr` as `format: password`, so a Host tells a secret
    from an ordinary string without importing the App. See
    `docs/decisions/ADR-022-configuration-is-a-declaration.md`.
    """
    try:
        described = _ConfigSchema.model_validate(dict(schema))
    except ValidationError:
        logger.info("unreadable configuration schema")
        return ()
    return tuple(name for name, field in described.properties.items() if field.format == "password")


def masked(values: Mapping[str, object], secrets: Sequence[str], /) -> dict[str, object]:
    """The held values, with a stored secret reported as set rather than given."""
    return {
        name: (SET if name in secrets and value not in (None, "") else value)
        for name, value in values.items()
    }


def is_configured(facts: AppFacts, held: Mapping[str, object], /) -> bool:
    """Whether every field an App declared as required has a value."""
    required = _ConfigSchema.model_validate(dict(facts.config_schema)).required
    return all(held.get(name) not in (None, "") for name in required)
