"""What the Hub's Tools take and return.

A diagnostic is plain fields because an output model is revalidated, so no
exception instance and no live object can travel in one. See
`docs/decisions/ADR-007-framework-guarantees-tool-output.md`.
"""

from pathlib import Path

from pydantic import BaseModel


class Diagnostic(BaseModel):
    """An expected, actionable failure, in the form a channel can render."""

    code: str
    message: str
    details: dict[str, str] = {}


class Empty(BaseModel):
    """The input of a Tool that takes nothing."""


class SourcePath(BaseModel):
    path: Path


class CandidateRow(BaseModel):
    folder: Path
    name: str | None
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


class AppName(BaseModel):
    app_name: str


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
    app_name: str
    values: dict[str, object] = {}


class HeldConfig(BaseModel):
    """What the Hub holds for one App, and what a start still needs.

    A secret is never held. `required_secrets` names the fields whose values a
    caller supplies at each start.
    """

    app_name: str
    values: dict[str, object]
    required_secrets: list[str]
    diagnostic: Diagnostic | None = None


class StartRequest(BaseModel):
    """An App to start, with the secret values its declaration requires."""

    app_name: str
    secrets: dict[str, object] = {}


class RunningApp(BaseModel):
    app_name: str
    url: str | None = None
    state: str
    diagnostic: Diagnostic | None = None
