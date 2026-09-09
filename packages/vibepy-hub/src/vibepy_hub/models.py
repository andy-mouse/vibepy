"""What the Hub's Tools take and return.

A diagnostic is plain fields because an output model is revalidated, so no
exception instance and no live object can travel in one. It carries a category
because a caller reads that to learn whether a different call could succeed. See
`docs/decisions/ADR-007-framework-guarantees-tool-output.md` and
`docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md`.

The Hub's own codes, until CR3 gives the Hub a document to carry them:

| Code | Category |
| --- | --- |
| `hub.candidate_absent` | caller |
| `hub.install_failed` | execution |
| `hub.no_app_declared` | declaration |
| `hub.multiple_apps_declared` | declaration |
| `hub.declaration_missing` | declaration |
| `hub.facts_unreadable` | execution |
| `hub.source_unreadable` | caller |
| `hub.not_installed` | caller |
| `hub.no_web_channel` | caller |
| `hub.already_running` | caller |
| `hub.not_running` | caller |
| `hub.start_failed` | execution |
"""

from pathlib import Path
from typing import Annotated

from packaging.utils import canonicalize_name
from pydantic import AfterValidator, BaseModel

from vibepy_core.errors import ErrorCategory


class Diagnostic(BaseModel):
    """An expected, actionable failure, in the form a channel can render."""

    code: str
    category: ErrorCategory
    message: str
    details: dict[str, str] = {}


class Empty(BaseModel):
    """The input of a Tool that takes nothing."""


class SourcePath(BaseModel):
    path: Path


class CandidateRow(BaseModel):
    folder: Path
    name: str
    version: str | None
    declares_app: bool


class SourceListing(BaseModel):
    sources: list[Path]
    candidates: list[CandidateRow]
    diagnostic: Diagnostic | None = None


class AppFacts(BaseModel):
    """What an App declares, read from its environment after installation."""

    app_id: str
    name: str
    version: str
    config_schema: dict[str, object] = {}
    has_pages: bool = False
    purelib: Path | None = None
    declared_name: str = ""
    """The name the App declares itself under, which a folder's need not match."""


_SEPARATORS = frozenset("/\\:\x00")


def _one_segment(value: str) -> str:
    """An App name addresses one environment and cannot address its neighbours.

    Every Hub Tool is on the Agent channel (ADR-024), so an App name is a
    model-controlled string that reaches the file system. Refusing it here is
    what makes the channel answer `tool.input_invalid` rather than the Hub grow
    a diagnostic of its own.

    What survives the gate is canonicalized, because an App is addressed by its
    distribution name and the specification compares two of those by
    normalizing them. The gate runs first: normalization does not remove a
    separator.
    """
    if value in {"", ".", ".."} or _SEPARATORS & set(value):
        raise ValueError("an App name is one path segment")
    return str(canonicalize_name(value))


AppNameField = Annotated[str, AfterValidator(_one_segment)]
"""The name a Tool takes for an App. Every Tool input carrying one uses it.

An output model keeps a plain `str`: an output model is revalidated, so
constraining one would turn an environment directory this Hub did not create
into a Tool failure rather than a row.
"""


class AppName(BaseModel):
    app_name: AppNameField


class AppRow(BaseModel):
    """One App as the control plane sees it.

    `state` is `available`, `installed` or `running`. It is a string because an
    output model round-trips through JSON and the set is the Hub's to publish.
    """

    app_name: str
    name: str | None = None
    version: str | None = None
    state: str
    url: str | None = None
    configured: bool = False
    has_pages: bool = False
    diagnostic: Diagnostic | None = None


class AppListing(BaseModel):
    apps: list[AppRow]


class Installation(BaseModel):
    app: AppRow
    diagnostic: Diagnostic | None = None


class ConfigureRequest(BaseModel):
    app_name: AppNameField
    values: dict[str, object] = {}


SET = "set"
"""What a stored secret reads as once it has one. Never the value itself."""


class HeldConfig(BaseModel):
    """What the Hub holds for one App.

    A secret's value is stored but never handed back: `values` reports it as
    `set`, the way `SecretStr` reports itself as masked. `secret_fields` names
    which fields those are.
    """

    app_name: str
    values: dict[str, object]
    secret_fields: list[str]
    diagnostic: Diagnostic | None = None


class StartRequest(BaseModel):
    """An App to start, with the secret values its declaration requires."""

    app_name: AppNameField
    secrets: dict[str, object] = {}


class RunningApp(BaseModel):
    app_name: str
    url: str | None = None
    state: str
    diagnostic: Diagnostic | None = None
