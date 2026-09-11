"""What the Hub's Tools take and return.

A diagnostic is plain fields because an output model is revalidated, so no
exception instance and no live object can travel in one. It carries a category
because a caller reads that to learn whether a different call could succeed.

The Hub's own codes:

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
| `hub.already_installed` | caller |
| `hub.up_to_date` | caller |
| `hub.no_address` | caller |
| `hub.no_web_channel` | caller |
| `hub.already_running` | caller |
| `hub.not_running` | caller |
| `hub.start_failed` | execution |

An installed App is reached at `http://<app>.localhost:<proxy port>`. The
hostname is the App's canonical distribution name and the port is the one the
Hub was configured with; the port the App itself serves on is allocated when
it is installed and does not leave the Hub.
"""

from pathlib import Path
from typing import Annotated

from packaging.utils import canonicalize_name
from pydantic import AfterValidator, BaseModel

from vibepy_core import ErrorCategory


class Diagnostic(BaseModel):
    """An expected, actionable failure, in the form a channel can render."""

    code: str
    category: ErrorCategory
    message: str
    details: dict[str, str] = {}


class Empty(BaseModel):
    """The input of a Tool that takes nothing."""


class SourcePath(BaseModel):
    """A folder of wheels, as `register_package_source` takes it."""

    path: Path


class CandidateRow(BaseModel):
    """One wheel the source offers: the highest version of one distribution."""

    wheel: Path
    name: str
    version: str
    declares_app: bool


class SourceListing(BaseModel):
    """The registered source, if any, and the candidates found in it."""

    source: Path | None
    candidates: list[CandidateRow]
    diagnostic: Diagnostic | None = None


class AppFacts(BaseModel):
    """What an App declares, read from its environment after installation."""

    app_id: str
    name: str
    version: str
    distribution_version: str
    """The version of the wheel that was installed, which is what an update changes.

    An App's own `version` is what its definition declares; the two need not agree,
    and only the distribution's is compared with what the source offers.
    """
    config_schema: dict[str, object] = {}
    has_pages: bool = False
    purelib: Path | None = None
    declared_name: str
    """The name the App declares itself under, which a folder's need not match."""
    distribution: str
    """The distribution that declared this App, which is what the Hub files it under.

    Required, with `declared_name`, because `write_facts` is the only writer and
    always states both. A record without them is one this Hub did not write, and
    saying so as `hub.facts_unreadable` is truer than reporting the App it
    describes as no longer declared.
    """


_SEPARATORS = frozenset("/\\:\x00")


def _one_segment(value: str) -> str:
    """Refuse `value` unless it names one path segment, then canonicalize it.

    What survives the gate is canonicalized, because an App is addressed by its
    distribution name and the specification compares two of those by
    normalizing them. The gate runs first: normalization does not remove a
    separator.
    """
    if value in {"", ".", ".."} or _SEPARATORS & set(value):
        # Every Hub Tool is on the Agent channel, so an App name is a
        # model-controlled string that reaches the file system. Refusing it
        # here is what makes the channel answer `tool.input_invalid` rather
        # than the Hub grow a diagnostic of its own.
        raise ValueError("an App name is one path segment")
    return str(canonicalize_name(value))


AppNameField = Annotated[str, AfterValidator(_one_segment)]
"""The name a Tool takes for an App. Every Tool input carrying one uses it.

An output model keeps a plain `str`: an output model is revalidated, so
constraining one would turn an environment directory this Hub did not create
into a Tool failure rather than a row.
"""


class AppName(BaseModel):
    """The input of a Tool that takes only an App name."""

    app_name: AppNameField


class AppRow(BaseModel):
    """One App as the control plane sees it.

    `state` is `available`, `installed` or `running`. It is a string because an
    output model round-trips through JSON and the set is the Hub's to publish.
    """

    app_name: str
    name: str | None = None
    version: str | None = None
    distribution_version: str | None = None
    """The installed or offered wheel's version. What the board shows and `update_app` compares."""
    available_version: str | None = None
    """The version the source offers when it is not the installed one; `update_app` installs it."""
    state: str
    url: str | None = None
    configured: bool = False
    has_pages: bool = False
    diagnostic: Diagnostic | None = None


class AppListing(BaseModel):
    """Every App the control plane knows of."""

    apps: list[AppRow]
    source: Path | None = None
    """The registered folder, said with the rows so one read draws the whole board."""

    diagnostic: Diagnostic | None = None


class Installation(BaseModel):
    """One App, as `install_app` and `remove_app` answer with it."""

    app: AppRow
    diagnostic: Diagnostic | None = None


class ConfigureRequest(BaseModel):
    """An App to configure, with the values to hold for it."""

    app_name: AppNameField
    values: dict[str, object] = {}


class HeldConfig(BaseModel):
    """What the Hub holds for one App.

    A secret's value is stored and handed back to no channel, so `values`
    carries only the fields that are not secrets. `secret_fields` names the
    fields an App declared as secret and `secrets_set` names those that have a
    value, said where a client cannot mistake it for a value. A client keeps a
    held secret by omitting the field.
    """

    app_name: str
    values: dict[str, object]
    secret_fields: list[str]
    secrets_set: list[str]
    diagnostic: Diagnostic | None = None


class ConfigField(BaseModel):
    """One field an App declares, as much of it as a form needs.

    `type` is `string`, `path`, `integer`, `secret` or `other`, read from the
    projected schema's `type` and `format`. A string because an output model
    round-trips through JSON and the set is the Hub's to publish.
    """

    name: str
    type: str
    required: bool


class ConfigDescription(BaseModel):
    """What one App declares and what the Hub holds for it, in one answer.

    The read half of `configure_app`: `values` carries no secret and
    `secrets_set` names the secrets that have one, so the answer is safe to
    show and safe to send back.
    """

    app_name: str
    fields: list[ConfigField] = []
    values: dict[str, object] = {}
    secrets_set: list[str] = []
    diagnostic: Diagnostic | None = None


class StartRequest(BaseModel):
    """An App to start, with the secret values its declaration requires."""

    app_name: AppNameField
    secrets: dict[str, object] = {}


class RunningApp(BaseModel):
    """One App, as `start_app` and `stop_app` answer with it."""

    app_name: str
    url: str | None = None
    state: str
    diagnostic: Diagnostic | None = None
