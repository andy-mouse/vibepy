from pydantic import BaseModel

from vibepy.adapters.mcp import to_mcp_tool
from vibepy.tool import ToolDefinition


class CreateTodoInput(BaseModel):
    title: str


class EmptyInput(BaseModel):
    pass


class Todo(BaseModel):
    id: int
    title: str
    done: bool


class TodoList(BaseModel):
    todos: list[Todo]


def create_todo_definition() -> ToolDefinition[CreateTodoInput, Todo]:
    return ToolDefinition(
        name="create_todo",
        description="Create a todo",
        input_model=CreateTodoInput,
        output_model=Todo,
    )


def list_todos_definition() -> ToolDefinition[EmptyInput, TodoList]:
    return ToolDefinition(
        name="list_todos",
        description="List every todo",
        input_model=EmptyInput,
        output_model=TodoList,
    )


def test_projection_carries_the_declaration_over() -> None:
    projected = to_mcp_tool(create_todo_definition())

    assert projected.name == "create_todo"
    assert projected.description == "Create a todo"


def test_projected_schemas_are_derived_from_the_models() -> None:
    projected = to_mcp_tool(create_todo_definition())

    assert projected.input_schema == CreateTodoInput.model_json_schema()
    assert projected.output_schema == Todo.model_json_schema()


def test_a_nested_output_model_keeps_its_definitions() -> None:
    projected = to_mcp_tool(list_todos_definition())

    assert projected.output_schema == TodoList.model_json_schema()
    assert projected.output_schema is not None
    assert "$defs" in projected.output_schema
