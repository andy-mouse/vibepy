"""What a folder of wheels offers, read without installing any of them."""

from pathlib import Path

from tests_support import write_wheel
from vibepy_studio.consumption.internals import candidates, readable


async def test_each_wheel_is_a_candidate_named_by_its_distribution(tmp_path: Path) -> None:
    write_wheel(tmp_path, name="Zulu_App", version="1.2.3", declares=True)
    write_wheel(tmp_path, name="alpha-app", version="0.1.0", declares=False)

    found = await candidates(tmp_path)

    assert [(row.name, row.version, row.declares_app) for row in found] == [
        ("alpha-app", "0.1.0", False),
        ("zulu-app", "1.2.3", True),
    ]
    assert all(row.wheel.parent == tmp_path for row in found)


async def test_of_several_versions_the_highest_is_the_candidate(tmp_path: Path) -> None:
    """A wheelhouse keeps old versions; that is not a diagnostic."""
    write_wheel(tmp_path, name="demo", version="1.9.0", declares=True)
    write_wheel(tmp_path, name="demo", version="1.10.0", declares=True)
    write_wheel(tmp_path, name="demo", version="1.2.0", declares=True)

    found = await candidates(tmp_path)

    assert [(row.name, row.version) for row in found] == [("demo", "1.10.0")]


async def test_a_file_that_is_not_a_wheel_is_not_a_candidate(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("not a wheel", encoding="utf-8")
    (tmp_path / "demo.whl").write_bytes(b"not a zip")
    (tmp_path / "sub").mkdir()
    write_wheel(tmp_path / "sub", name="nested", version="1.0.0", declares=True)

    assert await candidates(tmp_path) == ()


async def test_an_absent_folder_offers_nothing_and_is_not_readable(tmp_path: Path) -> None:
    gone = tmp_path / "gone"

    assert await candidates(gone) == ()
    assert await readable(gone) is False
