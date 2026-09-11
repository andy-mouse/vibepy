"""Reading what an App declares of its configuration, and holding values against it.

Studio never imports an App, so what it knows about configuration is what
`describe` wrote: the fields the declaration's own types were projected into.
Reading them is the App's answer, not a second reading of its JSON Schema.
"""

import logging
from collections.abc import Mapping, Sequence

from vibepy_core.app import ConfigFieldDescription, ConfigFieldType
from vibepy_studio.operating.models import AppFacts

logger = logging.getLogger(__name__)


def config_fields(facts: AppFacts, /) -> tuple[ConfigFieldDescription, ...]:
    """Return every field the App declared, as it described them."""
    return tuple(facts.described.config_fields)


def secret_fields(facts: AppFacts, /) -> tuple[str, ...]:
    """Return the fields the App declared as secret."""
    return tuple(
        field.name
        for field in facts.described.config_fields
        if field.type is ConfigFieldType.SECRET
    )


def held_secrets(values: Mapping[str, object], secrets: Sequence[str], /) -> tuple[str, ...]:
    """Return the declared secrets this App has a value for."""
    return tuple(name for name in secrets if values.get(name) not in (None, ""))


def without_secrets(values: Mapping[str, object], secrets: Sequence[str], /) -> dict[str, object]:
    """Return the held values a channel may see: every field that is not a secret."""
    return {name: value for name, value in values.items() if name not in secrets}


def is_configured(facts: AppFacts, held: Mapping[str, object], /) -> bool:
    """Whether every field an App declared as required has a value."""
    return all(
        held.get(field.name) not in (None, "")
        for field in facts.described.config_fields
        if field.required
    )
