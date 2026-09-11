"""A package declares its App in standard metadata, and reading that imports nothing."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from todo_app.entry import APP
from vibepy_core.app import AppRef, describe_app, discover_apps, load_app
from vibepy_core.errors import (
    AppEntrypointInvalidError,
    AppEntrypointUnloadableError,
    AppNotDeclaredError,
)


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


def test_a_declared_entrypoint_is_loaded_and_described() -> None:
    ref = AppRef(
        app_name="todo",
        distribution="tests",
        distribution_version="0.0.0",
        module="todo_app.entry",
        attr="APP",
    )

    assert describe_app(ref) == APP.describe()


def test_a_missing_module_is_reported_as_unloadable() -> None:
    ref = AppRef(
        app_name="ghost",
        distribution="ghost",
        distribution_version="0.0.0",
        module="no_such_module_anywhere",
        attr="app",
    )

    with pytest.raises(AppEntrypointUnloadableError) as raised:
        describe_app(ref)

    assert raised.value.code == "package.entrypoint_unloadable"
    assert raised.value.reference == "no_such_module_anywhere:app"


def test_a_missing_attribute_is_reported_as_unloadable() -> None:
    ref = AppRef(
        app_name="ghost",
        distribution="ghost",
        distribution_version="0.0.0",
        module="todo_app.entry",
        attr="NOT_DECLARED",
    )

    with pytest.raises(AppEntrypointUnloadableError):
        describe_app(ref)


def test_an_object_that_is_not_an_entrypoint_is_rejected() -> None:
    ref = AppRef(
        app_name="wrong",
        distribution="wrong",
        distribution_version="0.0.0",
        module="todo_app.entry",
        attr="TODO_APP",
    )

    with pytest.raises(AppEntrypointInvalidError) as raised:
        describe_app(ref)

    assert raised.value.code == "package.entrypoint_invalid"


def test_an_object_merely_carrying_a_describe_attribute_is_rejected() -> None:
    ref = AppRef(
        app_name="impostor",
        distribution="impostor",
        distribution_version="0.0.0",
        module="tests.impostor_fixture",
        attr="IMPOSTOR",
    )

    with pytest.raises(AppEntrypointInvalidError):
        describe_app(ref)


def test_load_app_returns_the_declared_entrypoint() -> None:
    loaded = load_app("todo-app")
    assert loaded.definition.app_id == "todo-app"


def test_load_app_refuses_an_app_this_environment_does_not_declare() -> None:
    with pytest.raises(AppNotDeclaredError) as raised:
        load_app("no-such-app")
    assert raised.value.details() == {"app_name": "no-such-app"}


def test_load_app_reports_an_entrypoint_that_will_not_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_distribution(
        tmp_path,
        distribution="ghost-app",
        version="0.1",
        entries=[("ghost", "ghost_app.entry:APP")],
    )
    monkeypatch.syspath_prepend(str(tmp_path))  # pyright: ignore[reportUnknownMemberType]
    with pytest.raises(AppEntrypointUnloadableError):
        load_app("ghost")


def test_load_app_reports_an_entrypoint_that_is_not_an_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_distribution(
        tmp_path,
        distribution="impostor-app",
        version="0.1",
        entries=[("impostor", "impostor_fixture:IMPOSTOR")],
    )
    monkeypatch.syspath_prepend(str(tmp_path))  # pyright: ignore[reportUnknownMemberType]
    with pytest.raises(AppEntrypointInvalidError):
        load_app("impostor")
