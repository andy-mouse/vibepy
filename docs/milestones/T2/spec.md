# T2 - The Todo fixture completes a todo

Date: 2026-09-11. A stage outside the roadmap: the roadmap's Apps section lists three Tools for
Todo and the fixture declares two.

## Acceptance criteria

- `fixtures/todo-app` declares `create_todo`, `list_todos`, `complete_todo`, in that order
- `complete_todo` marks one existing todo done and returns it; the change is visible to a later
  `list_todos` in another window over the same store
- an unknown id is the App's expected failure and travels as data (ADR-029): code
  `todo.not_found`, category `caller`, details carrying the id
- every test that names the Todo fixture's Tools names three

## Sources

| Contract | Source |
| --- | --- |
| Todo's Tools are `create_todo`, `list_todos`, `complete_todo` | `docs/roadmap.md`, Apps |
| an App's expected failure travels as data in its own output model, category required | `docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md` |
| blocking work behind `asyncio.to_thread`; the store's read-modify-write under its lock | `docs/architecture/runtime.md`, `fixtures/todo-app/src/todo_app/entry.py` (`TodoStore.create`) |
| the shape `tests/test_tool_core.py` has used for `complete_todo` since M1 | `tests/test_tool_core.py` |

## Design

In `fixtures/todo-app/src/todo_app/entry.py`:

```python
class CompleteTodoInput(BaseModel):
    id: int

class TodoDiagnostic(BaseModel):          # ADR-029's four fields; the App's own code
    code: str
    category: ErrorCategory
    message: str
    details: dict[str, str] = {}

class Completion(BaseModel):
    todo: Todo | None = None
    diagnostic: TodoDiagnostic | None = None
```

`TodoStore.complete(todo_id: int) -> Todo | None` is a read-modify-write under `_writing`, like
`create`; it returns the completed todo or `None` when no todo has that id. The handler wraps it
in `asyncio.to_thread` and answers `Completion(todo=...)` or
`Completion(diagnostic=TodoDiagnostic(code="todo.not_found", category=ErrorCategory.CALLER,
message=f"no todo has id {id}", details={"id": str(id)}))`. Tool description: "Mark a todo done".

The Page is unchanged: the human workflow it shows is add-and-list, and this stage adds a Tool,
not a workflow.

## Testing

- `tests/test_app_distributions.py` (subject: what the fixture Apps do, through their Tools): a
  todo created is completed and listed as done; completing an unknown id returns the diagnostic
  with code, category and details; `done` is `False` before and `True` after
- the six assertions that name the Tool list gain `complete_todo`: `tests/test_mcp_adapter.py`,
  `tests/test_app_entrypoint.py`, `tests/test_describe_command.py`,
  `packages/vibepy-studio/tests/test_inspect_app.py`, `packages/vibepy-studio/tests/test_describing.py`
  (sorted lists: `["complete_todo", "create_todo", "list_todos"]`), and any other found by the gate

## Out of scope

A Page control to complete a todo; the Notes and Timer fixtures; `docs/roadmap.md`.
