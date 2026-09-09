"""The decision records keep the shape AGENTS.md requires of them.

A retired record stays in the folder, because the log is append-only and later
records cite earlier ones. What must not happen is a document of current truth
resting on a record that no longer holds, which is how a reader ends up acting on
a decision that was withdrawn.
"""

import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
DECISIONS = REPOSITORY / "docs" / "decisions"

LIVE_STATUS = "Accepted"
RETIRED_PREFIXES = ("Deprecated", "Superseded by ")
PROPOSED_STATUS = "Proposed"

REFERENCE = re.compile(r"ADR-(\d{3})")


def _status(record: Path, /) -> str:
    for line in record.read_text(encoding="utf-8").splitlines():
        if line.startswith("Status:"):
            return line.removeprefix("Status:").strip()
    raise AssertionError(f"{record.name} declares no status")


def _records() -> dict[str, Path]:
    return {record.name[4:7]: record for record in sorted(DECISIONS.glob("ADR-*.md"))}


def _citing_documents() -> list[Path]:
    """Everything that may cite a record, other than the records themselves.

    A record cites another to supersede it, so the folder is excluded. So is
    `docs/milestones/`, which holds work in progress rather than current truth.
    """
    documents = [REPOSITORY / "AGENTS.md", REPOSITORY / "docs" / "architecture.md"]
    documents += sorted((REPOSITORY / "docs" / "architecture").rglob("*.md"))
    documents += sorted((REPOSITORY / "src").rglob("*.py"))
    return documents


def test_every_record_declares_a_status_the_format_allows() -> None:
    for number, record in _records().items():
        status = _status(record)
        allowed = status in {LIVE_STATUS, PROPOSED_STATUS} or status.startswith(RETIRED_PREFIXES)
        assert allowed, f"ADR-{number} declares an unknown status: {status!r}"


def test_a_superseding_record_names_one_that_exists() -> None:
    records = _records()
    for number, record in records.items():
        status = _status(record)
        if not status.startswith("Superseded by "):
            continue
        named = REFERENCE.findall(status)
        assert named, f"ADR-{number} is superseded by nothing it names"
        for successor in named:
            assert successor in records, f"ADR-{number} names a missing ADR-{successor}"


def test_no_document_of_current_truth_cites_a_retired_record() -> None:
    retired = {
        number
        for number, record in _records().items()
        if _status(record).startswith(RETIRED_PREFIXES)
    }
    for document in _citing_documents():
        cited = set(REFERENCE.findall(document.read_text(encoding="utf-8")))
        withdrawn = sorted(cited & retired)
        relative = document.relative_to(REPOSITORY)
        assert not withdrawn, f"{relative} cites retired ADR-{', ADR-'.join(withdrawn)}"
