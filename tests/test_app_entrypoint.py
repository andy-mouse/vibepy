"""An entrypoint is a value, and describing it requires no resource."""

from collections.abc import Mapping, Sequence

from pydantic import JsonValue

from todo_app.entry import APP


def properties(schema: Mapping[str, JsonValue], /) -> Sequence[str]:
    """The property names of a JSON schema, which is a nested JSON object."""
    section = schema["properties"]
    assert isinstance(section, Mapping)
    return sorted(section)


def test_a_description_carries_the_declared_identity() -> None:
    description = APP.describe()

    assert description.app_id == "todo-app"
    assert description.name == "Todo"
    assert description.version == "0.0.0"


def test_a_description_carries_the_configuration_schema() -> None:
    description = APP.describe()

    assert properties(description.config_schema) == ["db_path"]


def test_a_description_carries_every_tool_with_both_schemas() -> None:
    description = APP.describe()

    assert [tool.name for tool in description.tools] == ["create_todo", "list_todos"]
    create = description.tools[0]
    assert create.description == "Create a todo"
    assert properties(create.input_schema) == ["title"]
    assert properties(create.output_schema) == ["done", "id", "title"]


def test_a_description_carries_every_page_route() -> None:
    description = APP.describe()

    assert [(page.name, page.route, page.title) for page in description.pages] == [
        ("todos", "/todos", "Todos")
    ]
