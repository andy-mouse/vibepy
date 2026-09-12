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
from pydantic import AfterValidator, BaseModel, BeforeValidator, JsonValue

from vibepy_core.app import ConfigFieldDescription, DescribedApp
from vibepy_core.errors import ErrorInfo


def _a_named_folder(value: object) -> object:
    """Refuse an empty path before `Path` turns it into the working directory.

    `Path("")` is `.`, which is a directory that exists, so an empty string
    would register whatever folder the server happens to run in. Refusing it
    here is what makes the channel answer `tool.input_invalid`.
    """
    if isinstance(value, str) and not value.strip():
        raise ValueError("a package source is a folder path")
    return value


SourcePathField = Annotated[Path, BeforeValidator(_a_named_folder)]
"""The folder a Tool takes as the package source."""


class SourcePath(BaseModel):
    """A folder of wheels, as `register_package_source` takes it."""

    path: SourcePathField


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
    diagnostic: ErrorInfo | None = None


class AppFacts(BaseModel):
    """What an App declares, read from its environment after installation.

    The declaration is carried as the one shape `describe` writes, so nothing
    here restates a field the App already said. `write_facts` is the only
    writer and always states the whole description: a record without one is
    one this Hub did not write, and saying so as `hub.facts_unreadable` is
    truer than reporting the App it describes as no longer declared.
    """

    described: DescribedApp
    purelib: Path | None = None

    @property
    def has_pages(self) -> bool:
        """Whether the App declares a Web channel."""
        return bool(self.described.description.pages)


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
    """The version the source offers when newer than the installed one; `update_app` installs it."""
    state: str
    url: str | None = None
    configured: bool = False
    has_pages: bool = False
    diagnostic: ErrorInfo | None = None


class AppListing(BaseModel):
    """Every App the control plane knows of."""

    apps: list[AppRow]
    source: Path | None = None
    """The registered folder, said with the rows so one read draws the whole board."""

    diagnostic: ErrorInfo | None = None


class Installation(BaseModel):
    """One App, as `install_app` and `remove_app` answer with it."""

    app: AppRow
    diagnostic: ErrorInfo | None = None


class ConfigureRequest(BaseModel):
    """An App to configure, with the values to hold for it."""

    app_name: AppNameField
    values: dict[str, JsonValue] = {}


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
    diagnostic: ErrorInfo | None = None


class ConfigDescription(BaseModel):
    """What one App declares and what the Hub holds for it, in one answer.

    The read half of `configure_app`: `values` carries no secret and
    `secrets_set` names the secrets that have one, so the answer is safe to
    show and safe to send back.
    """

    app_name: str
    fields: list[ConfigFieldDescription] = []
    values: dict[str, object] = {}
    secrets_set: list[str] = []
    diagnostic: ErrorInfo | None = None


class StartRequest(BaseModel):
    """An App to start, with the secret values its declaration requires."""

    app_name: AppNameField
    secrets: dict[str, JsonValue] = {}


class RunningApp(BaseModel):
    """One App, as `start_app` and `stop_app` answer with it."""

    app_name: str
    url: str | None = None
    state: str
    diagnostic: ErrorInfo | None = None
