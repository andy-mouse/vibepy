"""Configuration is a declaration, and a window validates it before acquiring anything."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from pydantic import BaseModel, SecretStr

from vibepy_core.app import AppConfig, AppDefinition, NoConfig, environment_for, tool_runtime_for
from vibepy_core.errors import AppConfigInvalidError


class Limits(BaseModel):
    per_page: int


class StoreConfig(AppConfig):
    db_path: Path
    api_token: SecretStr
    limits: Limits = Limits(per_page=10)


class Acquired:
    def __init__(self, config: StoreConfig) -> None:
        self.config = config


def entered_flags() -> list[str]:
    return []


def configured_definition() -> AppDefinition[Acquired, StoreConfig]:
    return AppDefinition(
        app_id="configured",
        name="Configured",
        version="0.0.0",
        config=StoreConfig,
        tools=[],
        pages=[],
    )


def unconfigured_definition() -> AppDefinition[None, NoConfig]:
    return AppDefinition(
        app_id="unconfigured",
        name="Unconfigured",
        version="0.0.0",
        config=NoConfig,
        tools=[],
        pages=[],
    )


def store_lifespan(entered: list[str]):
    @asynccontextmanager
    async def lifespan(config: StoreConfig) -> AsyncGenerator[Acquired]:
        entered.append("entered")
        yield Acquired(config)

    return lifespan


async def test_a_valid_mapping_reaches_the_lifespan_as_the_declared_model() -> None:
    entered = entered_flags()
    seen: list[StoreConfig] = []

    @asynccontextmanager
    async def lifespan(config: StoreConfig) -> AsyncGenerator[Acquired]:
        entered.append("entered")
        seen.append(config)
        yield Acquired(config)

    async with tool_runtime_for(
        configured_definition(),
        lifespan,
        config={"db_path": "/tmp/todo.db", "api_token": "shhh"},
    ):
        pass

    assert entered == ["entered"]
    assert seen[0].db_path == Path("/tmp/todo.db")
    assert seen[0].api_token.get_secret_value() == "shhh"


async def test_an_invalid_mapping_is_rejected_before_the_lifespan_is_entered() -> None:
    entered = entered_flags()

    with pytest.raises(AppConfigInvalidError) as raised:
        async with tool_runtime_for(
            configured_definition(),
            store_lifespan(entered),
            config={"api_token": "shhh"},
        ):
            pass

    assert entered == []
    assert raised.value.app_id == "configured"
    assert raised.value.fields == ("db_path",)


async def test_an_app_requiring_nothing_declares_the_empty_model() -> None:
    @asynccontextmanager
    async def lifespan(_config: NoConfig) -> AsyncGenerator[None]:
        yield None

    async with tool_runtime_for(unconfigured_definition(), lifespan, config={}) as tools:
        assert tools is not None


async def test_a_secret_is_not_disclosed_by_the_configuration_object() -> None:
    seen: list[StoreConfig] = []

    @asynccontextmanager
    async def lifespan(config: StoreConfig) -> AsyncGenerator[Acquired]:
        seen.append(config)
        yield Acquired(config)

    async with tool_runtime_for(
        configured_definition(),
        lifespan,
        config={"db_path": "/tmp/todo.db", "api_token": "shhh"},
    ):
        pass

    assert "shhh" not in repr(seen[0])
    assert "shhh" not in str(seen[0])


async def test_two_windows_over_one_definition_do_not_share_configuration() -> None:
    definition = configured_definition()
    seen: list[StoreConfig] = []

    @asynccontextmanager
    async def lifespan(config: StoreConfig) -> AsyncGenerator[Acquired]:
        seen.append(config)
        yield Acquired(config)

    async with tool_runtime_for(
        definition, lifespan, config={"db_path": "/tmp/one.db", "api_token": "a"}
    ):
        async with tool_runtime_for(
            definition, lifespan, config={"db_path": "/tmp/two.db", "api_token": "b"}
        ):
            pass

    assert [config.db_path for config in seen] == [Path("/tmp/one.db"), Path("/tmp/two.db")]


def test_the_declared_configuration_is_readable_without_running_anything() -> None:
    schema = configured_definition().config.model_json_schema()

    assert sorted(schema["properties"]) == ["api_token", "db_path", "limits"]
    assert schema["properties"]["api_token"]["writeOnly"] is True


async def test_a_window_reads_its_declaration_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBEPY_DB_PATH", "/tmp/env.db")
    monkeypatch.setenv("VIBEPY_API_TOKEN", "from-env")
    monkeypatch.setenv("VIBEPY_LIMITS", '{"per_page": 3}')
    monkeypatch.setenv("VIBEPY_OTHER", "not a field")
    seen: list[StoreConfig] = []

    @asynccontextmanager
    async def lifespan(config: StoreConfig) -> AsyncGenerator[Acquired]:
        seen.append(config)
        yield Acquired(config)

    async with tool_runtime_for(configured_definition(), lifespan, config={}):
        pass

    assert seen[0].db_path == Path("/tmp/env.db")
    assert seen[0].api_token.get_secret_value() == "from-env"
    assert seen[0].limits.per_page == 3


async def test_an_explicit_value_stands_above_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIBEPY_DB_PATH", "/tmp/env.db")
    monkeypatch.setenv("VIBEPY_API_TOKEN", "from-env")
    seen: list[StoreConfig] = []

    @asynccontextmanager
    async def lifespan(config: StoreConfig) -> AsyncGenerator[Acquired]:
        seen.append(config)
        yield Acquired(config)

    async with tool_runtime_for(
        configured_definition(), lifespan, config={"db_path": "/tmp/explicit.db"}
    ):
        pass

    assert seen[0].db_path == Path("/tmp/explicit.db")
    assert seen[0].api_token.get_secret_value() == "from-env"


async def test_a_value_for_an_undeclared_field_is_refused() -> None:
    entered = entered_flags()

    with pytest.raises(AppConfigInvalidError) as raised:
        async with tool_runtime_for(
            configured_definition(),
            store_lifespan(entered),
            config={"db_path": "/tmp/x.db", "api_token": "s", "db_pth": "typo"},
        ):
            pass

    assert entered == []
    assert raised.value.fields == ("db_pth",)


def test_environment_for_renders_what_a_window_reads() -> None:
    rendered = environment_for(
        {"db_path": "/tmp/x.db", "api_token": "s", "limits": {"per_page": 7}, "port": 8080}
    )

    assert rendered == {
        "VIBEPY_DB_PATH": "/tmp/x.db",
        "VIBEPY_API_TOKEN": "s",
        "VIBEPY_LIMITS": '{"per_page": 7}',
        "VIBEPY_PORT": "8080",
    }
