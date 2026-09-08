"""What a registered folder offers, read without building anything."""

from pathlib import Path

from tests_support import write_project
from vibepy_hub.sources import candidates


def test_a_declaring_folder_is_an_installable_candidate(tmp_path: Path) -> None:
    write_project(tmp_path / "demo", name="demo-app", declares=True)

    found = candidates(tmp_path)

    assert [(row.name, row.version, row.declares_app) for row in found] == [
        ("demo-app", "1.2.3", True)
    ]


def test_a_folder_without_a_declaration_is_still_offered(tmp_path: Path) -> None:
    write_project(tmp_path / "plain", name="plain", declares=False)

    assert [row.declares_app for row in candidates(tmp_path)] == [False]


def test_a_folder_without_a_project_file_is_not_a_candidate(tmp_path: Path) -> None:
    (tmp_path / "notes").mkdir()

    assert candidates(tmp_path) == ()


def test_candidates_are_ordered_by_folder_name(tmp_path: Path) -> None:
    write_project(tmp_path / "zulu", name="zulu", declares=True)
    write_project(tmp_path / "alpha", name="alpha", declares=True)

    assert [row.folder.name for row in candidates(tmp_path)] == ["alpha", "zulu"]
