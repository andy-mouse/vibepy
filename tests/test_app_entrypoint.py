"""An entrypoint is a value, and describing it requires no resource."""

from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import BaseModel, Field, JsonValue, SecretStr, computed_field

from lifecycle import no_dependencies
from todo_app.entry import APP
from vibepy_core.app import (
    AppConfig,
    AppDefinition,
    AppEntrypoint,
    ConfigFieldType,
    NoConfig,
)
from vibepy_core.channel import Channel
from vibepy_core.tool import Tool, ToolContext, ToolDefinition


def entrypoint_with_config[ConfigT: AppConfig](
    config: type[ConfigT], /
) -> AppEntrypoint[None, ConfigT]:
    """An entrypoint over a definition declaring nothing but `config`."""

    @asynccontextmanager
    async def nothing(_config: ConfigT) -> AsyncGenerator[None]:
        yield None

    definition: AppDefinition[None, ConfigT] = AppDefinition(
        app_id="configured",
        name="Configured",
        version="0.0.0",
        config=config,
        tools=[],
        pages=[],
    )
    return AppEntrypoint(definition=definition, lifespan=nothing)


def entrypoint_with[InputT: BaseModel, OutputT: BaseModel](
    definition: ToolDefinition[InputT, OutputT], /
) -> AppEntrypoint[None, NoConfig]:
    """An entrypoint over one Tool definition. `describe` never invokes it."""

    async def unreachable(_ctx: ToolContext[None], _payload: InputT, /) -> OutputT:
        raise NotImplementedError

    app_definition: AppDefinition[None, NoConfig] = AppDefinition(
        app_id="described",
        name="Described",
        version="0.0.0",
        config=NoConfig,
        tools=[Tool(definition=definition, handler=unreachable)],
        pages=[],
    )
    return AppEntrypoint(definition=app_definition, lifespan=no_dependencies)


def properties(schema: Mapping[str, JsonValue], /) -> Sequence[str]:
    """The property names of a JSON schema, which is a nested JSON object."""
    section = schema["properties"]
    assert isinstance(section, Mapping)
    return sorted(section)


def test_a_description_carries_the_declared_identity() -> None:
    """Described against the definition it was built from, not against
    literals: what is under test is that `describe` projects a declaration
    faithfully, and an App that renames itself is not a failure of that."""
    description = APP.describe()

    assert description.app_id == APP.definition.app_id
    assert description.name == APP.definition.name
    assert description.version == APP.definition.version


def test_a_description_carries_the_configuration_schema() -> None:
    """The schema is the config model's own, so the fields are asked of it."""
    description = APP.describe()

    assert properties(description.config_schema) == sorted(APP.definition.config.model_fields)


def test_a_description_carries_every_tool_with_both_schemas() -> None:
    description = APP.describe()

    assert [tool.name for tool in description.tools] == [
        "create_todo",
        "list_todos",
        "complete_todo",
    ]
    create = description.tools[0]
    assert create.description == "Create a todo"
    assert properties(create.input_schema) == ["title"]
    assert properties(create.output_schema) == ["done", "id", "title"]


def test_a_description_carries_every_page_route() -> None:
    description = APP.describe()

    assert [(page.name, page.route, page.title) for page in description.pages] == [
        ("todos", "/todos", "Todos")
    ]


class Wanted(BaseModel):
    """An output model whose serialized shape is not its validated shape."""

    width: int = Field(serialization_alias="widthPx")

    @computed_field
    @property
    def doubled(self) -> int:
        return self.width * 2


def test_a_description_publishes_the_schema_its_output_is_serialized_to() -> None:
    """The second surface that publishes a Tool's schemas, held to the same rule.

    `describe` and the Agent channel's projection both ask the declaration, so
    ADR-007's requirement that a published schema and the value it describes
    cannot diverge is guarded on both rather than on one.
    """

    async def measure(_ctx: ToolContext[None], _payload: Wanted) -> Wanted:
        return Wanted(width=2)

    definition: AppDefinition[None, NoConfig] = AppDefinition(
        app_id="measuring",
        name="Measuring",
        version="0.0.0",
        config=NoConfig,
        tools=[
            Tool(
                definition=ToolDefinition(
                    name="measure",
                    description="Carries a computed member under an alias",
                    input_model=Wanted,
                    output_model=Wanted,
                    read_only=True,
                ),
                handler=measure,
            )
        ],
        pages=[],
    )

    described = AppEntrypoint(definition=definition, lifespan=no_dependencies).describe()

    published = described.tools[0]
    assert properties(published.output_schema) == sorted(
        Wanted(width=2).model_dump(by_alias=True, mode="json")
    )
    assert properties(published.output_schema) == ["doubled", "widthPx"]
    assert properties(published.input_schema) == ["width"]


def test_a_description_derives_its_configuration_fields_from_the_types() -> None:
    class Config(AppConfig):
        root: Path
        token: SecretStr
        port: int = 8080
        note: str | None = None

    described = entrypoint_with_config(Config).describe()

    fields = {f.name: (f.type, f.required) for f in described.config_fields}
    assert fields == {
        "root": (ConfigFieldType.PATH, True),
        "token": (ConfigFieldType.SECRET, True),
        "port": (ConfigFieldType.INTEGER, False),
        "note": (ConfigFieldType.OTHER, False),
    }


def test_a_description_carries_a_tools_side_effects_exposure_and_roles() -> None:
    described = entrypoint_with(
        ToolDefinition(
            name="approve",
            description="Approve",
            input_model=Wanted,
            output_model=Wanted,
            read_only=True,
            channels=frozenset({Channel.AGENT}),
            required_roles=frozenset({"manager"}),
        )
    ).describe()

    tool = described.tools[0]
    assert (tool.read_only, tool.channels, tool.required_roles) == (
        True,
        [Channel.AGENT],
        ["manager"],
    )
