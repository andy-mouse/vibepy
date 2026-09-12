"""Who is invoking. Asserted by a host, threaded by the framework, never derived here."""

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Principal:
    """One caller: an identity and the roles its host asserts for it."""

    id: str
    roles: frozenset[str] = frozenset()
