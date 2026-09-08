"""A package declares its App in standard metadata, and reading that imports nothing."""

from collections.abc import Sequence
from pathlib import Path

from vibepy.app import discover_apps


def write_distribution(
    root: Path, *, distribution: str, version: str, entries: Sequence[tuple[str, str]]
) -> None:
    """Write the minimum a distribution needs to be discoverable: METADATA and entry points."""
    dist_info = root / f"{distribution.replace('-', '_')}-{version}.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {distribution}\nVersion: {version}\n", encoding="utf-8"
    )
    declared = "\n".join(f"{name} = {value}" for name, value in entries)
    (dist_info / "entry_points.txt").write_text(f"[vibepy.apps]\n{declared}\n", encoding="utf-8")


def write_module(root: Path, *, package: str, attr: str) -> None:
    module = root / package
    module.mkdir(parents=True)
    (module / "__init__.py").write_text("", encoding="utf-8")
    (module / "entry.py").write_text(f"{attr} = object()\n", encoding="utf-8")


def test_an_app_is_discovered_from_distribution_metadata(tmp_path: Path) -> None:
    write_distribution(
        tmp_path,
        distribution="demo-app",
        version="1.2.3",
        entries=[("demo", "demo_app.entry:app")],
    )

    refs = discover_apps(path=[tmp_path])

    assert len(refs) == 1
    assert refs[0].app_name == "demo"
    assert refs[0].distribution == "demo-app"
    assert refs[0].distribution_version == "1.2.3"
    assert refs[0].module == "demo_app.entry"
    assert refs[0].attr == "app"


def test_a_distribution_declaring_no_app_yields_nothing(tmp_path: Path) -> None:
    dist_info = tmp_path / "plain-1.0.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: plain\nVersion: 1.0.0\n", encoding="utf-8"
    )

    assert discover_apps(path=[tmp_path]) == ()


def test_discovery_is_ordered_by_app_name(tmp_path: Path) -> None:
    write_distribution(
        tmp_path,
        distribution="many-apps",
        version="1.0.0",
        entries=[("zulu", "many.entry:zulu"), ("alpha", "many.entry:alpha")],
    )

    assert [ref.app_name for ref in discover_apps(path=[tmp_path])] == ["alpha", "zulu"]
