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
