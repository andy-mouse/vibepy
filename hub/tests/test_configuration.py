"""The Hub holds an App's values, and never a secret."""

from pathlib import Path

from tests_support import SAMPLES, hub
from vibepy_hub.models import HeldConfig
from vibepy_hub.tools import secret_fields

SCHEMA: dict[str, object] = {
    "properties": {
        "api_base_url": {"type": "string"},
        "api_token": {"type": "string", "format": "password", "writeOnly": True},
    },
    "required": ["api_base_url", "api_token"],
}


def test_a_secret_field_is_recognised_from_the_schema() -> None:
    assert secret_fields(SCHEMA) == ("api_token",)


def test_a_schema_without_properties_declares_no_secret() -> None:
    assert secret_fields({}) == ()


async def test_values_are_held_for_an_installed_app(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(SAMPLES)})
        await tools.invoke("install_app", {"app_name": "todo"})
        held = await tools.invoke(
            "configure_app",
            {"app_name": "todo", "values": {"db_path": str(tmp_path / "todo.db")}},
        )

    assert isinstance(held, HeldConfig)
    assert held.diagnostic is None
    assert held.values == {"db_path": str(tmp_path / "todo.db")}
    assert held.required_secrets == []


async def test_configuring_an_app_that_is_not_installed_is_a_diagnostic(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        answered = await tools.invoke("configure_app", {"app_name": "todo", "values": {}})

    assert isinstance(answered, HeldConfig)
    assert answered.diagnostic is not None
    assert answered.diagnostic.code == "hub.not_installed"


async def test_a_declared_secret_is_never_stored(tmp_path: Path) -> None:
    root = tmp_path / "hub"

    async with hub(root) as tools:
        await tools.invoke("register_package_source", {"path": str(SAMPLES)})
        await tools.invoke("install_app", {"app_name": "notes"})
        held = await tools.invoke(
            "configure_app",
            {
                "app_name": "notes",
                "values": {"api_base_url": "https://notes.internal", "api_token": "s3cret"},
            },
        )

    assert isinstance(held, HeldConfig)
    assert held.values == {"api_base_url": "https://notes.internal"}
    assert held.required_secrets == ["api_token"]
    assert "s3cret" not in (root / "state.json").read_text(encoding="utf-8")
