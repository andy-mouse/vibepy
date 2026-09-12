"""Reading what an environment declares, through the framework's own command."""

import sys

import pytest

from vibepy_studio.internals.describing import DescribeFailed, describe
from vibepy_studio.internals.processes import NotRunnable


@pytest.mark.integration
async def test_the_running_environment_describes_its_apps_with_their_tools() -> None:
    described = await describe([sys.executable])
    todo = next(entry for entry in described if entry.app_name == "todo-app")
    assert todo.distribution == "vibepy-todo"
    assert sorted(tool.name for tool in todo.description.tools) == [
        "complete_todo",
        "create_todo",
        "list_todos",
    ]
    assert (
        "properties"
        in next(t for t in todo.description.tools if t.name == "create_todo").input_schema
    )
    assert [page.route for page in todo.description.pages] == ["/todos"]


async def test_a_python_that_is_not_there_is_not_runnable() -> None:
    with pytest.raises(NotRunnable):
        await describe(["no-such-python"])


@pytest.mark.integration
async def test_a_command_that_exits_without_a_report_fails_to_describe() -> None:
    with pytest.raises(DescribeFailed) as failed:
        await describe([sys.executable, "-S", "-c", "import sys; sys.exit(2)", "--"])
    assert failed.value.reported is None
