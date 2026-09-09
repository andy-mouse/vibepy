# CR1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the seven framework and Hub defects CR1 owns, and add the guards that would have caught them.

**Architecture:** Each task is one finding from `docs/milestones/CR1/spec.md`, fixed at its cause rather than at its symptom. Tasks 1 to 3 touch `src/vibepy_core/errors.py` and must run in order; the rest are independent. No task adds a decision — each applies ADR-007, ADR-012, ADR-019 or `docs/architecture/errors.md`, cited in the spec's `Sources` table.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, NiceGUI (`nicegui.testing.User`), MCP SDK, uv workspace.

## Global Constraints

- A change is done when `make lint typecheck test` passes.
- `Any` and `cast` are not acceptable in the public API. Use `Protocol`, `TypedDict`, dataclass or `TypeVar`.
- Optional and configuration parameters are keyword-only.
- Filesystem paths are `pathlib.Path`, never strings.
- Framework exceptions derive from `VibepyError`. Exception types are the contract, not message strings.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- Tests verify public contracts, not internals.
- Baseline is 153 collected tests. Only Task 4 removes one; every other task adds.
- The framework runs on macOS and Windows: no POSIX-only path assumption.
- Documentation is updated only where a task makes it false. No `Accepted` ADR changes.

---

### Task 1: `to_error_info` describes any exception (I15)

`to_error_info` promises to describe any exception and raises on two: a bare `VibepyError`, whose `code` is an unassigned `ClassVar`, and an App's own subclass of the exported base, whose code no category table names. The MCP adapter calls it inside an `except Exception` that exists so an App defect cannot become a protocol error, so the `KeyError` escaping that clause is that protocol error.

**Files:**
- Modify: `src/vibepy_core/errors.py:207-224` (`to_error_info`)
- Test: `tests/test_errors.py`, `tests/test_mcp_adapter.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `to_error_info(error: Exception, /) -> ErrorInfo` — signature unchanged. Behaviour: an exception whose `code` the framework does not map is reported as `code="app.unhandled"`, `category=ErrorCategory.EXECUTION`, `details={}`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_errors.py`:

```python
def test_the_bare_base_is_described_rather_than_classified() -> None:
    info = to_error_info(VibepyError("boom"))

    assert info.code == UNHANDLED_CODE
    assert info.category is ErrorCategory.EXECUTION
    assert info.message == "boom"
    assert info.details == {}


def test_an_app_subclass_of_the_public_base_is_described() -> None:
    class AppOwnError(VibepyError):
        code = "app.something_specific"

        def details(self) -> Mapping[str, str]:
            return {"where": "the app"}

    info = to_error_info(AppOwnError("no good"))

    assert info.code == UNHANDLED_CODE
    assert info.category is ErrorCategory.EXECUTION
    assert info.message == "no good"
    assert info.details == {}


def test_an_exception_carrying_a_framework_code_it_does_not_own_is_described() -> None:
    class Impostor(Exception):
        code = "tool.not_found"

    info = to_error_info(Impostor("pretending"))

    assert info.code == UNHANDLED_CODE
    assert info.category is ErrorCategory.EXECUTION
```

The third test pins that classification reads the framework's own hierarchy and not any attribute named `code`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_errors.py -k "described or impostor" -v`
Expected: the first two FAIL with `AttributeError` and `KeyError`; the third FAILS because `Impostor` is classified as `tool.not_found`/`caller`.

- [ ] **Step 3: Make the unmapped case fall through**

Replace `to_error_info` in `src/vibepy_core/errors.py`:

```python
def to_error_info(error: Exception, /) -> ErrorInfo:
    """Describe any exception in the channel-neutral form.

    Normalizing is not wrapping. The exception itself still propagates untouched;
    this is called only where a channel must render an answer.

    A code this table does not map is not classified, whatever raised it: an App
    may subclass the exported base, and `docs/architecture/errors.md` says an
    exception raised by an App's own code is described rather than classified.
    The catalogue test is what guarantees no framework exception takes that path.
    """
    if isinstance(error, VibepyError):
        code = getattr(error, "code", None)
        category = _CATEGORIES.get(code) if isinstance(code, str) else None
        if code is not None and category is not None:
            return ErrorInfo(
                code=code,
                category=category,
                message=str(error),
                details=error.details(),
            )
    return ErrorInfo(
        code=UNHANDLED_CODE,
        category=ErrorCategory.EXECUTION,
        message=str(error),
        details={},
    )
```

- [ ] **Step 4: Run the error suite**

Run: `uv run pytest tests/test_errors.py -v`
Expected: PASS, including the existing catalogue tests that walk every subclass.

- [ ] **Step 5: Write the adapter test that made this critical**

Add to `tests/test_mcp_adapter.py`, after `test_a_raising_handler_is_reported_inside_the_result`. The file already has `server_for`, `_payload`, `EmptyInput` and `Todo`; use them rather than adding a second helper for a job one already does:

```python
class AppOwnError(VibepyError):
    """An App's own subclass of the exported base, carrying its own code."""

    code = "app.its_own"


async def test_an_app_defined_error_answers_with_a_result_not_a_protocol_error() -> None:
    async def raises(_ctx: ToolContext[None], _payload: EmptyInput) -> Todo:
        raise AppOwnError("the app's own failure")

    tools = [
        Tool(
            definition=ToolDefinition(
                name="app_error",
                description="Raises an App-defined subclass of the public base",
                input_model=EmptyInput,
                output_model=Todo,
            ),
            handler=raises,
        )
    ]

    async with server_for(tools) as server, Client(server) as client:
        result = await client.call_tool("app_error", {})

    assert result.is_error is True
    payload = _payload(result)
    assert payload["code"] == UNHANDLED_CODE
    assert payload["category"] == ErrorCategory.EXECUTION.value
    assert payload["details"] == {}
```

Add `VibepyError` to the file's existing import from `vibepy_core.errors`, which already names `UNHANDLED_CODE` and `ErrorCategory`.

- [ ] **Step 6: Run it**

Run: `uv run pytest tests/test_mcp_adapter.py -v`
Expected: PASS. Before Step 3 this test would have failed with the `KeyError` escaping `call_tool`.

- [ ] **Step 7: Verify and commit**

Run: `make lint typecheck test`
Expected: all pass. The suite grows by the four tests this task added and loses none.

```bash
git add src/vibepy_core/errors.py tests/test_errors.py tests/test_mcp_adapter.py
git commit -m "Describe an exception whose code the framework does not map

to_error_info promised to describe any exception and raised on a bare
VibepyError and on an App's own subclass of the exported base. The MCP
adapter calls it inside the except clause that exists so an App defect
cannot become a protocol error, so the KeyError was that protocol error.

errors.md already rules on it: an exception raised by an App's own code is
described, not classified. Classification now reads the framework's own
hierarchy and its own table, and everything else falls through to
app.unhandled."
```

---

### Task 2: `AppNotDeclaredError` joins the hierarchy (I1)

`AppNotDeclared` derives from `Exception`, so it carries no code, no category and no row in `errors.md`. `test_errors.py` walks `VibepyError.__subclasses__()`, so the catalogue test that enforces ADR-019 is blind to the one exception outside the rule. The same function writes a code-and-message JSON object for every other failure and prose for this one.

**Files:**
- Modify: `src/vibepy_core/errors.py` (new class after `AppEntrypointInvalidError`, new `_CATEGORIES` row)
- Modify: `src/vibepy_core/serve.py:37-38` (delete the class), `:65` (raise the new one), `:99-102` (report it as JSON)
- Modify: `src/vibepy_core/__init__.py` (import and `__all__`)
- Modify: `docs/architecture/errors.md` (one row)
- Test: `tests/test_errors.py`, `tests/test_package.py`, `tests/test_serve_command.py`

**Interfaces:**
- Consumes: Task 1's `to_error_info`.
- Produces: `AppNotDeclaredError(app_name: str)`, `code = "package.app_not_declared"`, `details() -> {"app_name": ...}`, category `ErrorCategory.CALLER`, exported from `vibepy_core`.

- [ ] **Step 1: Write the failing tests**

Add the row to `CASES` in `tests/test_errors.py`, which is what makes the catalogue tests cover it:

```python
    (
        AppNotDeclaredError("absent"),
        "package.app_not_declared",
        ErrorCategory.CALLER,
        {"app_name": "absent"},
    ),
```

Add `AppNotDeclaredError` to that file's import from `vibepy_core.errors`, and to the expected `__all__` list in `tests/test_package.py` in alphabetical position — it sorts directly before `"AppRef"`.

Replace `test_an_unknown_app_name_fails_with_a_message` in `tests/test_serve_command.py`:

```python
def test_an_unknown_app_name_fails_with_the_framework_code() -> None:
    finished = subprocess.run(
        [sys.executable, "-m", "vibepy_core.serve", "absent", "--port", str(free_port())],
        input=b"{}",
        capture_output=True,
        check=False,
        env=child_environment(),
    )

    assert finished.returncode == 1
    written = json.loads(finished.stderr.decode())
    assert written["code"] == "package.app_not_declared"
    assert "absent" in written["message"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_errors.py tests/test_package.py tests/test_serve_command.py -v`
Expected: FAIL — `ImportError: cannot import name 'AppNotDeclaredError'`.

- [ ] **Step 3: Add the exception and map its category**

In `src/vibepy_core/errors.py`, after `AppEntrypointInvalidError`:

```python
class AppNotDeclaredError(VibepyError):
    """No App of that name is declared in this environment."""

    code = "package.app_not_declared"

    def __init__(self, app_name: str) -> None:
        super().__init__(f"No App named {app_name!r} is declared in this environment")
        self.app_name = app_name

    def details(self) -> Mapping[str, str]:
        return {"app_name": self.app_name}
```

Add to `_CATEGORIES`, keeping the table's existing order of declaration:

```python
    AppNotDeclaredError.code: ErrorCategory.CALLER,
```

`caller` because `errors.md` defines it as the call itself being wrong where a different call may succeed, which naming an App this environment does not declare is. `declaration` describes an App declaring something the framework rejects, and here nothing was declared.

- [ ] **Step 4: Raise and report it from `serve`**

In `src/vibepy_core/serve.py`: delete the local `class AppNotDeclared`, add `AppNotDeclaredError` to the existing import from `vibepy_core.errors`, and change the raise at the end of `_entrypoint`:

```python
    raise AppNotDeclaredError(app_name)
```

In `main`, fold the two `except` clauses into one, because all three failures now report the same way:

```python
    try:
        entrypoint = _entrypoint(str(parsed.app_name))
    except (
        AppNotDeclaredError,
        AppEntrypointUnloadableError,
        AppEntrypointInvalidError,
    ) as error:
        info = to_error_info(error)
        sys.stderr.write(json.dumps({"code": info.code, "message": info.message}) + "\n")
        return 1
```

Update `main`'s docstring where it names the failures it exits 1 for, so it stops describing a prose branch that no longer exists.

- [ ] **Step 5: Export it**

In `src/vibepy_core/__init__.py`, add `AppNotDeclaredError` to the `from vibepy_core.errors import (...)` block and to `__all__`, both in alphabetical position.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_errors.py tests/test_package.py tests/test_serve_command.py -v`
Expected: PASS. `test_every_framework_error_is_covered_here` passes without being edited to name the new class, which is the acceptance criterion.

- [ ] **Step 7: Document the code**

Add one row to the code table in `docs/architecture/errors.md`, after `package.entrypoint_invalid`:

```markdown
| `package.app_not_declared` | caller | `AppNotDeclaredError` |
```

Change nothing else in that file.

- [ ] **Step 8: Verify and commit**

Run: `make lint typecheck test`
Expected: all pass. `CASES` gained one row, so the three tests parametrized over it each gained a case, and `test_serve_command.py` replaced one test with one test.

```bash
git add src/vibepy_core/errors.py src/vibepy_core/serve.py src/vibepy_core/__init__.py \
        docs/architecture/errors.md tests/test_errors.py tests/test_package.py \
        tests/test_serve_command.py
git commit -m "Bring AppNotDeclared into the exception hierarchy

It derived from Exception, so it had no code, no category and no row in
errors.md, and the catalogue test that walks VibepyError.__subclasses__()
could not see the one exception standing outside the rule it enforces.

ADR-019 requires an added exception to declare a code and map a category.
package.app_not_declared is caller: naming an App this environment does not
declare is a call a different call succeeds at. serve now reports it the way
it already reported every other failure."
```

---

### Task 3: A duplicate Page name is refused (I6)

Registration validates route format and route uniqueness and not name uniqueness, while the registry the renderer resolves through replaces by name. Two Pages with one name and two routes therefore register both routes and render the second handler from each, with no diagnostic. ADR-012 exists because a silent replacement is unacceptable.

The refusal goes where a declaration becomes a registry, not in the adapter: `page-model.md` places a check by the model that owns the field, `route` and `title` are the Web channel adapter's, and `name` is the identifier the framework addresses a Page by. Refusing in `page_registry_for` also fails before the window opens, so no route exists to leave behind.

**Files:**
- Modify: `src/vibepy_core/errors.py` (new class after `PageRouteConflictError`, new `_CATEGORIES` row)
- Modify: `src/vibepy_core/app/composition.py:46-53` (`page_registry_for`)
- Modify: `src/vibepy_core/__init__.py` (import and `__all__`)
- Modify: `docs/architecture/errors.md` (one row), `docs/architecture/page-model.md` (one sentence)
- Test: `tests/test_errors.py`, `tests/test_package.py`, `tests/test_app_composition.py`

**Interfaces:**
- Consumes: Task 1's `to_error_info`, Task 2's `_CATEGORIES` layout.
- Produces: `PageNameConflictError(page_name: str, route: str, conflicting_route: str)`, `code = "page.name_conflict"`, `details() -> {"page_name", "route", "conflicting_route"}`, category `ErrorCategory.DECLARATION`, exported from `vibepy_core`. `page_registry_for` raises it.

- [ ] **Step 1: Write the failing tests**

Add the `CASES` row to `tests/test_errors.py` and the import, mirroring Task 2:

```python
    (
        PageNameConflictError("todos", "/todos", "/todo-list"),
        "page.name_conflict",
        ErrorCategory.DECLARATION,
        {"page_name": "todos", "route": "/todos", "conflicting_route": "/todo-list"},
    ),
```

Add `"PageNameConflictError"` to the expected `__all__` in `tests/test_package.py`; it sorts directly before `"PageNotFoundError"`.

Add to `tests/test_app_composition.py`, which is where the window's contracts are tested:

```python
def two_pages_named(name: str, routes: tuple[str, str]) -> AppDefinition[None, NoConfig]:
    """One App declaring two Pages under one name, on two routes."""

    async def render(_ctx: PageContext) -> None:
        return None

    return AppDefinition(
        app_id="collides",
        name="Collides",
        version="0.0.0",
        config=NoConfig,
        tools=[],
        pages=[
            Page(
                definition=PageDefinition(name=name, route=route, title=route),
                handler=render,
            )
            for route in routes
        ],
    )


async def test_two_pages_declaring_one_name_do_not_open_a_window() -> None:
    definition = two_pages_named("todos", ("/todos", "/todo-list"))

    with pytest.raises(PageNameConflictError) as error:
        async with page_runtime_for(definition, no_dependencies, config={}):
            raise AssertionError("the window must not open")

    assert error.value.page_name == "todos"
    assert {error.value.route, error.value.conflicting_route} == {"/todos", "/todo-list"}
```

`no_dependencies` comes from `tests/lifecycle.py`; import it and `PageNameConflictError` at the top of the file.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_errors.py tests/test_app_composition.py tests/test_package.py -v`
Expected: FAIL — `ImportError: cannot import name 'PageNameConflictError'`.

- [ ] **Step 3: Add the exception**

In `src/vibepy_core/errors.py`, after `PageRouteConflictError`:

```python
class PageNameConflictError(VibepyError):
    """Two Pages declared the same name."""

    code = "page.name_conflict"

    def __init__(self, page_name: str, route: str, conflicting_route: str) -> None:
        super().__init__(
            f"Pages at {route!r} and {conflicting_route!r} both declare the name {page_name!r}"
        )
        self.page_name = page_name
        self.route = route
        self.conflicting_route = conflicting_route

    def details(self) -> Mapping[str, str]:
        return {
            "page_name": self.page_name,
            "route": self.route,
            "conflicting_route": self.conflicting_route,
        }
```

Add to `_CATEGORIES` beside the other page codes:

```python
    PageNameConflictError.code: ErrorCategory.DECLARATION,
```

- [ ] **Step 4: Refuse the duplicate in `page_registry_for`**

Replace `page_registry_for` in `src/vibepy_core/app/composition.py`:

```python
def page_registry_for[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT], /
) -> PageRegistry:
    """Fill a PageRegistry from declarations. Reads no resource.

    A name declared twice is refused rather than replaced. The registry's own
    contract is that a re-registration replaces, and `page-model.md` places a
    check by the model that owns the field: a route belongs to the Web channel
    adapter, and a name is what the framework addresses a Page by.
    """
    registry = PageRegistry()
    claimed: dict[str, str] = {}
    for page in definition.pages:
        declared = page.definition
        owner = claimed.get(declared.name)
        if owner is not None:
            raise PageNameConflictError(declared.name, owner, declared.route)
        claimed[declared.name] = declared.route
        registry.register(page)
    return registry
```

Add `PageNameConflictError` to the module's import from `vibepy_core.errors`, which currently names `AppConfigInvalidError` only.

- [ ] **Step 5: Export it**

In `src/vibepy_core/__init__.py`, add `PageNameConflictError` to the errors import block and to `__all__`, in alphabetical position.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_errors.py tests/test_app_composition.py tests/test_package.py tests/test_nicegui_adapter.py -v`
Expected: PASS. The NiceGUI suite is included because it must be unaffected: route validation stays in the adapter and its two existing rejection tests still pass.

- [ ] **Step 7: Document it**

Add one row to the code table in `docs/architecture/errors.md`, after `page.route_conflict`:

```markdown
| `page.name_conflict` | declaration | `PageNameConflictError` |
```

In `docs/architecture/page-model.md`, in the `PageRegistry` section, leave "Registering a name twice replaces the earlier registration." exactly as it is — it is still the registry's contract — and add after it:

```markdown
A declaration carrying one name twice never reaches it: the window refuses such a declaration
where it builds the registry, because `name` is what the framework addresses a Page by while a
route is the Web channel adapter's.
```

- [ ] **Step 8: Verify and commit**

Run: `make lint typecheck test`
Expected: all pass. One composition test and one `CASES` row are added.

```bash
git add src/vibepy_core/errors.py src/vibepy_core/app/composition.py \
        src/vibepy_core/__init__.py docs/architecture/errors.md \
        docs/architecture/page-model.md tests/test_errors.py \
        tests/test_app_composition.py tests/test_package.py
git commit -m "Refuse a declaration carrying one Page name twice

Registration checked route format and route uniqueness and not name
uniqueness, while the registry the renderer resolves through replaces by
name, so two Pages with one name and two routes served the second handler
from both routes with no diagnostic.

ADR-012's consequence is that such a collision fails loudly. The check goes
where a declaration becomes a registry rather than in the adapter, because
page-model.md places a check by the model that owns the field: a route is
the adapter's and a name is the framework's. It therefore fails before the
window opens, so no route is left behind."
```

---

### Task 4: `PageRegistry.definitions()` is deleted (I5)

The method has no caller, and ADR-012's amendment records that `register_pages` has always enumerated the declaration and never took a `PageRegistry` — so the docstring promising that a Web channel adapter projects these into routes was never true.

**Partly superseded by ADR-027, taken after this plan was written.** This task said the Agent channel is not touched, because `ToolRegistry.definitions()` had a caller and the architecture documents described that enumeration as staying. That answered the criterion's `used` branch and left the cause in place: the adapter built a lookup table to enumerate a list it already held. ADR-027 has both channels enumerate the declaration, so `ToolRegistry.definitions()` is deleted too and `tool_registry_for` refuses a duplicate Tool name. Do this task as written — it is still the Page half — and read `docs/decisions/ADR-027-a-channel-enumerates-declarations-from-the-declaration.md` for the Tool half, which no task below covers.

**Files:**
- Modify: `src/vibepy_core/page/registry.py:26-32` (delete the method), `:3-4` (drop the now-unused import)
- Modify: `docs/architecture/page-model.md` (delete one paragraph)
- Test: `tests/test_page_core.py:92-116`

**Interfaces:**
- Consumes: nothing.
- Produces: `PageRegistry` with `register` and `resolve` only. No caller in this repository is affected.

- [ ] **Step 1: Delete the test whose subject is going, and trim the one that keeps its subject**

In `tests/test_page_core.py`, delete `test_definitions_enumerates_every_registered_page` entirely. In `test_registering_a_name_twice_replaces_the_earlier_page`, delete only the final assertion:

```python
    assert registry.definitions() == (replacement.definition,)
```

The `resolve` assertion above it stays: replacement is still the registry's contract, and `page-model.md` still states it.

- [ ] **Step 2: Run the suite to see it fail on the method still existing**

Run: `uv run pytest tests/test_page_core.py -v`
Expected: PASS — the tests pass because the method is still there. This step is the confirmation that nothing else in the suite reads it, so proceed only if the run is green.

Run: `uv run grep -rn "definitions()" tests/ src/ packages/ 2>/dev/null || grep -rn "definitions()" tests src packages`
Expected: matches only in `tool/` and `tests/test_tool_core.py`, `tests/test_mcp_adapter.py` — no remaining `PageRegistry` caller.

- [ ] **Step 3: Delete the method**

In `src/vibepy_core/page/registry.py`, delete `definitions()` and change the import to name only what is used:

```python
from vibepy_core.page.model import Page
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_page_core.py tests/test_nicegui_adapter.py -v`
Expected: PASS.

- [ ] **Step 5: Delete the paragraph that described it**

In `docs/architecture/page-model.md`, in the `PageRegistry` section, delete:

```markdown
The registry also enumerates its declarations, because a Web channel adapter projects every
PageDefinition into a route.
```

Leave the surrounding sentences, including the one Task 3 added.

- [ ] **Step 6: Verify and commit**

Run: `make lint typecheck test`
Expected: all pass, with exactly one test fewer than after Task 3 — the deleted one.

```bash
git add src/vibepy_core/page/registry.py docs/architecture/page-model.md tests/test_page_core.py
git commit -m "Delete PageRegistry.definitions()

It had no caller, and ADR-012's amendment records that register_pages has
always enumerated the declaration and never took a PageRegistry, so the
method's docstring — that a Web channel adapter projects these into routes —
was false on arrival. page-model.md carried the same claim and loses it.

The Agent channel is untouched by this commit. ADR-027, taken later, brings it
to the same shape."
```

---

### Task 5: The Agent channel publishes the serialization schema (D1)

The adapter publishes `model_json_schema()`, Pydantic's validation schema, and sends `model_dump(mode="json")`, a serialization dump. For an output model with a `computed_field` the payload carries a member the published schema does not describe, which ADR-007's first consequence says cannot happen. No output model in this repository has one, so the defect is latent and the fix is one argument.

**Files:**
- Modify: `src/vibepy_core/adapters/mcp/projection.py:14-21`
- Test: `tests/test_mcp_adapter.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `to_mcp_tool(definition)` — signature unchanged. `output_schema` is the model's serialization schema; `input_schema` stays its validation schema.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mcp_adapter.py`:

```python
class Measured(BaseModel):
    """An output model whose serialization schema differs from its validation one."""

    width: int

    @computed_field
    @property
    def doubled(self) -> int:
        return self.width * 2


def test_the_published_output_schema_describes_every_member_the_payload_carries() -> None:
    definition = ToolDefinition(
        name="measure",
        description="Returns a computed member",
        input_model=Measured,
        output_model=Measured,
    )

    projected = to_mcp_tool(definition)

    assert projected.output_schema is not None
    assert "doubled" in projected.output_schema["properties"]
    assert set(Measured(width=2).model_dump(by_alias=True, mode="json")) <= set(
        projected.output_schema["properties"]
    )


def test_the_published_input_schema_describes_what_is_validated() -> None:
    definition = ToolDefinition(
        name="measure",
        description="Returns a computed member",
        input_model=Measured,
        output_model=Measured,
    )

    projected = to_mcp_tool(definition)

    assert "doubled" not in projected.input_schema["properties"]
```

Import `computed_field` from `pydantic` at the top of the file. The second test pins the asymmetry: a computed member is produced, never accepted, so the input schema must stay the validation schema.

- [ ] **Step 2: Run them to verify the first fails**

Run: `uv run pytest tests/test_mcp_adapter.py -k "published" -v`
Expected: the output-schema test FAILS — `doubled` is absent from a validation-mode schema. The input-schema test PASSES already, and must keep passing.

- [ ] **Step 3: Publish the serialization schema**

In `src/vibepy_core/adapters/mcp/projection.py`:

```python
def to_mcp_tool(definition: ToolDefinition[BaseModel, BaseModel]) -> types.Tool:
    """Project one declaration. Only fields with a source in ToolDefinition are set.

    The output schema is the model's serialization schema, because the payload is
    a serialization dump: ADR-007 requires that the published schema and the
    returned value cannot diverge. The input schema stays the validation schema,
    because an argument mapping is validated against it.
    """
    return types.Tool(
        name=definition.name,
        description=definition.description,
        input_schema=definition.input_model.model_json_schema(),
        output_schema=definition.output_model.model_json_schema(mode="serialization"),
    )
```

- [ ] **Step 4: Run them**

Run: `uv run pytest tests/test_mcp_adapter.py -v`
Expected: PASS, including the existing schema and nested-model tests.

- [ ] **Step 5: Verify and commit**

Run: `make lint typecheck test`
Expected: all pass. Two projection tests are added.

```bash
git add src/vibepy_core/adapters/mcp/projection.py tests/test_mcp_adapter.py
git commit -m "Publish the schema the payload is serialized against

The adapter published a validation schema and sent a serialization dump, so
an output model with a computed_field would carry a member the published
schema does not describe. ADR-007's first consequence is that the published
schema and the returned value cannot diverge silently, and the MCP
specification requires a structured result to conform to the declared schema.

No output model in this repository has such a member, which is why the gap
was latent. The input schema stays the validation schema: a computed member
is produced, never accepted."
```

---

### Task 6: A Hub App name cannot leave the environments root (C1)

`AppName.app_name` is an unconstrained `str`, `environment()` is a bare `root / "envs" / name` join, and `remove_app` calls `shutil.rmtree` on the result. ADR-024 exposes every Hub Tool on the Agent channel, so this is a model-controlled string reaching a recursive delete: `../../victim` escapes the root and an absolute name discards it.

Two gates, both reachable. The constrained field gives the Agent channel a `tool.input_invalid` answer at the boundary; `environment()` is the guarantee, because the three input models are not its only callers.

**Files:**
- Modify: `packages/vibepy-hub/src/vibepy_hub/models.py` (validator, then `AppName`, `ConfigureRequest`, `StartRequest`)
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/installer.py:28-40` (new exception, `environment`)
- Modify: `packages/vibepy-hub/src/vibepy_hub/internals/__init__.py` (export)
- Test: `packages/vibepy-hub/tests/test_installation.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `AppNameInvalid(app_name: str)` in `vibepy_hub.internals.installer`, exported from `vibepy_hub.internals`. `environment(root: Path, app_name: str, /) -> Path` raises it; its return value for a valid name is unchanged, the unresolved `root / "envs" / app_name`.

- [ ] **Step 1: Write the failing tests**

Add to `packages/vibepy-hub/tests/test_installation.py`:

```python
async def test_a_traversing_app_name_deletes_nothing(tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")

    async with hub(tmp_path / "hub") as tools:
        with pytest.raises(ToolInputValidationError):
            await tools.invoke("remove_app", {"app_name": "../../victim"})

    assert (victim / "keep.txt").is_file()


async def test_an_absolute_app_name_is_refused(tmp_path: Path) -> None:
    async with hub(tmp_path / "hub") as tools:
        with pytest.raises(ToolInputValidationError):
            await tools.invoke("remove_app", {"app_name": str(tmp_path / "victim")})


@pytest.mark.parametrize("name", ["../../victim", "..", ".", "", "a/b", "a\\b"])
def test_environment_refuses_a_name_that_is_not_one_segment(tmp_path: Path, name: str) -> None:
    with pytest.raises(AppNameInvalid):
        environment(tmp_path, name)


def test_environment_answers_for_a_plain_name(tmp_path: Path) -> None:
    assert environment(tmp_path, "todo") == tmp_path / "envs" / "todo"
```

Import `pytest`, `ToolInputValidationError` from `vibepy_core.errors`, and `AppNameInvalid` and `environment` from `vibepy_hub.internals`. `hub` and `environment` may already be imported in this file — check before adding.

The first test asserts on a real directory outside the root, so a regression deletes a file the test then cannot find.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/vibepy-hub/tests/test_installation.py -k "traversing or absolute or environment" -v`
Expected: FAIL — `ImportError` for `AppNameInvalid`. After adding only the import, the traversal test fails because `remove_app` accepts the name.

- [ ] **Step 3: Constrain the name at the model boundary**

In `packages/vibepy-hub/src/vibepy_hub/models.py`, add above `AppName`:

```python
_SEPARATORS = frozenset("/\\:\x00")


def _one_segment(value: str) -> str:
    """An App name addresses one directory and cannot address its neighbours."""
    if value in {"", ".", ".."} or _SEPARATORS & set(value):
        raise ValueError("an App name is one path segment")
    return value


AppNameField = Annotated[str, AfterValidator(_one_segment)]
"""The name a Tool takes for an App. Every Tool input carrying one uses it."""
```

Import `Annotated` from `typing` and `AfterValidator` from `pydantic`. Then change the three input models' field type from `str` to `AppNameField`: `AppName`, `ConfigureRequest`, `StartRequest`.

Leave `AppRow`, `HeldConfig` and `RunningApp` as `str`. An output model is revalidated, so constraining one would turn an environment directory the Hub did not create into a Tool failure rather than a row.

- [ ] **Step 4: Make `environment()` the guarantee**

In `packages/vibepy-hub/src/vibepy_hub/internals/installer.py`, add beside `InstallFailed`:

```python
class AppNameInvalid(Exception):
    """An App name does not address a directory inside this Hub's environments."""

    def __init__(self, app_name: str) -> None:
        super().__init__(f"App name {app_name!r} is not one path segment")
        self.app_name = app_name
```

and replace `environment`:

```python
def environment(root: Path, app_name: str, /) -> Path:
    """Where this Hub keeps one App's environment.

    The name is refused unless the join resolves to a direct child of the
    environments directory. A Tool input is already constrained to one segment;
    this is the guarantee, because a Tool input is not the only caller and the
    result reaches `shutil.rmtree`.
    """
    envs = root / "envs"
    candidate = envs / app_name
    if candidate.resolve().parent != envs.resolve():
        raise AppNameInvalid(app_name)
    return candidate
```

`Path.resolve()` is non-strict, so it answers for a directory that does not exist yet, and comparing resolved parents is correct on both platforms without enumerating separators a second time.

- [ ] **Step 5: Export the exception**

In `packages/vibepy-hub/src/vibepy_hub/internals/__init__.py`, add `AppNameInvalid` to the import from `vibepy_hub.internals.installer` and to `__all__`, both in alphabetical position.

- [ ] **Step 6: Run the Hub suite**

Run: `uv run pytest packages/vibepy-hub/tests -v`
Expected: PASS, including the existing install, configure, start, stop and remove tests. If one fails because it used a name with a separator, that name was addressing something outside the root and the test is asserting the defect — report it rather than relaxing the constraint.

- [ ] **Step 7: Verify and commit**

Run: `make lint typecheck test`
Expected: all pass. Three Hub tests are added, one of them parametrized over six names.

```bash
git add packages/vibepy-hub/src/vibepy_hub/models.py \
        packages/vibepy-hub/src/vibepy_hub/internals/installer.py \
        packages/vibepy-hub/src/vibepy_hub/internals/__init__.py \
        packages/vibepy-hub/tests/test_installation.py
git commit -m "Keep an App name inside the Hub's environments root

AppName.app_name was an unconstrained str, environment() a bare join, and
remove_app calls shutil.rmtree on the result. ADR-024 exposes every Hub Tool
on the Agent channel, so a model-controlled string reached a recursive
delete: '../../victim' escaped the root and an absolute name discarded it.

Two gates. The constrained field answers a bad name as tool.input_invalid at
the channel boundary, so the Hub grows no diagnostic for it. environment()
refuses a name whose join does not resolve to a direct child of the
environments directory, which is the guarantee: a Tool input is not its only
caller. Output models keep an unconstrained name, because an environment
directory the Hub did not create is a row and not a failure."
```

---

### Task 7: One guard covers both channel SDKs (I14)

No MCP type in the core Tool model and no Web type in the core Page model are the repository's two headline invariants, and both are true by reading and untested. The two AST guards that exist are duplicated in two files and scan `tool/`, `page/` and `app/` only — skipping `__init__.py`, `errors.py` and `describe.py`, and the package root is where an SDK import would reach every consumer.

**Files:**
- Create: `tests/test_channel_neutrality.py`
- Modify: `tests/test_mcp_adapter.py` (delete `_imported_module_names` and `test_the_core_packages_do_not_import_mcp`, and the `ast`/`Path` imports if nothing else uses them)
- Modify: `tests/test_nicegui_adapter.py` (delete the same two, and the `ast`/`Path` imports if nothing else uses them)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing importable. Two tests: a static scan of every core module, and a subprocess import check.

- [ ] **Step 1: Write the new guard**

Create `tests/test_channel_neutrality.py`:

```python
"""The two headline invariants, proven rather than read.

No MCP type reaches the core Tool model and no Web type reaches the core Page
model. `AGENTS.md` states both, and the package root is where an SDK import
would reach every consumer, so the scan covers every core module rather than
three packages.

A channel component is exempt because being one is its job: `adapters/` holds
the two adapters, and `serve.py` is the command `docs/architecture/packaging.md`
documents as the one that opens an App's Web channel.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parent.parent / "src" / "vibepy_core"
CHANNEL_SDKS = ("mcp", "nicegui")
CHANNEL_COMPONENTS = ("adapters", "serve.py")


def core_modules() -> list[Path]:
    """Every module of the core that is not a channel component."""
    return sorted(
        module
        for module in CORE.rglob("*.py")
        if not set(module.relative_to(CORE).parts) & set(CHANNEL_COMPONENTS)
    )


def imported_module_names(source: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_the_scan_reaches_the_package_root_and_the_error_model() -> None:
    """The guard is only worth what it covers."""
    covered = {module.relative_to(CORE).as_posix() for module in core_modules()}

    assert {"__init__.py", "errors.py", "describe.py", "tool/model.py", "page/model.py"} <= covered
    assert "serve.py" not in covered
    assert not any(name.startswith("adapters/") for name in covered)


@pytest.mark.parametrize("sdk", CHANNEL_SDKS)
def test_no_core_module_imports_a_channel_sdk(sdk: str) -> None:
    offenders = [
        module.relative_to(CORE).as_posix()
        for module in core_modules()
        for name in imported_module_names(module.read_text(encoding="utf-8"))
        if name == sdk or name.startswith(f"{sdk}.")
    ]

    assert offenders == []


def test_importing_the_core_loads_no_channel_sdk() -> None:
    """What a static scan cannot see: an SDK reached through another import."""
    probe = (
        "import json, sys; import vibepy_core; "
        "print(json.dumps(sorted({m.split('.')[0] for m in sys.modules} "
        f"& set({list(CHANNEL_SDKS)!r}))))"
    )
    finished = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr
    assert json.loads(finished.stdout) == []
```

The first test exists because a guard that silently stops covering a file is worse than no guard: it asserts what the scan reaches, so narrowing the scan fails too.

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_channel_neutrality.py -v`
Expected: PASS — all four. If `test_importing_the_core_loads_no_channel_sdk` fails, an SDK is reaching the package root transitively and that is the finding, not a test defect: report it.

- [ ] **Step 3: Prove it catches what the old guard missed**

Temporarily add `import mcp` to the top of `src/vibepy_core/errors.py`, then:

Run: `uv run pytest tests/test_channel_neutrality.py -v`
Expected: FAIL — both the `mcp` scan and the subprocess check. The old guards passed in exactly this state, which is I14.

Remove the temporary import and re-run to confirm green. Do not commit the temporary import.

- [ ] **Step 4: Delete the two duplicated guards**

In `tests/test_mcp_adapter.py`, delete `_imported_module_names` and `test_the_core_packages_do_not_import_mcp`. In `tests/test_nicegui_adapter.py`, delete `_imported_module_names` and `test_the_core_packages_do_not_import_nicegui`. In each file, delete the `import ast` and `from pathlib import Path` lines only if nothing else in that file uses them — check with `grep -n "ast\.\|Path" <file>` before deleting.

- [ ] **Step 5: Run the whole suite**

Run: `make lint typecheck test`
Expected: all pass. Two duplicated guards are gone and four tests replace them.

- [ ] **Step 6: Commit**

```bash
git add tests/test_channel_neutrality.py tests/test_mcp_adapter.py tests/test_nicegui_adapter.py
git commit -m "Guard the two headline invariants across every core module

No MCP type in the core Tool model and no Web type in the core Page model
were true by reading and untested. The two AST guards that existed were
duplicated in two files and scanned tool/, page/ and app/ only, skipping
__init__.py, errors.py and describe.py — and the package root is where an
SDK import reaches every consumer.

One guard replaces both. It scans every core module except the channel
components, adapters/ and the serve command, and it also imports vibepy_core
in a subprocess to catch an SDK reached through another import rather than
written in the file. A fourth test asserts what the scan covers, so
narrowing it later fails too."
```

---

### Task 8: The Web channel's error contract is tested (I20)

`errors.md` states that the Web channel translates nothing: a framework error or a handler exception raised during a render reaches NiceGUI, which renders it. M7's criterion was verified for the Agent channel only, so the channel that promises not to translate is the one never checked.

These two tests use `nicegui.testing.user_simulation` directly rather than the `user` fixture. The fixture fails a test when any `ERROR` record was logged during the call phase (`nicegui/testing/user_plugin.py:28-30`), and a render that raises is exactly what makes NiceGUI log one — the fixture's assertion is a convenience for tests that expect no failure, and it offers no opt-out. `user_simulation` is the context manager the fixture is built on and is exported from `nicegui.testing.__all__`, so this uses NiceGUI's own mechanism rather than working around it. It resets the same process-global route table, which is why every other test in the file requests the fixture.

**Files:**
- Modify: `tests/test_nicegui_adapter.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing importable.

- [ ] **Step 1: Write the tests**

Add to `tests/test_nicegui_adapter.py`, using the file's existing `web_definition` helper:

```python
class HandlersOwnError(Exception):
    """An exception an App's own Page handler raises."""


def boom_definition(handler: PageHandler) -> AppDefinition[None, NoConfig]:
    return web_definition(
        [
            Page(
                definition=PageDefinition(name="boom", route="/boom", title="Boom"),
                handler=handler,
            )
        ]
    )


async def test_a_framework_error_raised_in_a_render_is_not_translated() -> None:
    """The framework adds nothing: the exception type itself reaches the caller."""

    async def handler(ctx: PageContext) -> None:
        await ctx.tools.invoke("absent", {})

    definition = boom_definition(handler)

    async with user_simulation() as user:
        async with page_runtime_for(definition, no_dependencies, config={}) as pages:
            register_pages(definition, pages)

            with pytest.raises(ToolNotFoundError):
                await user.open("/boom")


async def test_an_app_exception_raised_in_a_render_is_not_translated() -> None:
    async def handler(_ctx: PageContext) -> None:
        raise HandlersOwnError("the app's own failure")

    definition = boom_definition(handler)

    async with user_simulation() as user:
        async with page_runtime_for(definition, no_dependencies, config={}) as pages:
            register_pages(definition, pages)

            with pytest.raises(HandlersOwnError):
                await user.open("/boom")
```

Add `user_simulation` to the file's existing import from `nicegui.testing`, `ToolNotFoundError` to its import from `vibepy_core.errors`, and `PageHandler` to its import from `vibepy_core.page`.

The first App declares no Tools, so `invoke` raises `ToolNotFoundError` from the canonical invocation path rather than from a fixture. The assertion in both is the exception type reaching the caller: no `ErrorInfo`, no code, no category, no payload of the framework's making. That is what translating nothing means.

- [ ] **Step 2: Run them**

Run: `uv run pytest tests/test_nicegui_adapter.py -k "not_translated" -v`
Expected: PASS, both, with no teardown error. A teardown failure reading `There were unexpected ERROR logs` means the `user` fixture was used instead of `user_simulation`.

- [ ] **Step 3: Verify and commit**

Run: `make lint typecheck test`
Expected: all pass. Two Web-channel tests are added.

```bash
git add tests/test_nicegui_adapter.py
git commit -m "Test that the Web channel translates nothing

errors.md states that a framework error or a handler exception raised during
a render reaches NiceGUI, which renders it. M7's criterion was verified for
the Agent channel only, so the channel that promises not to translate was
the one never checked.

Two renders behind a registered route: one raising a framework error through
the canonical invocation path, one raising the App's own exception. Both
assert the exception type reaches the caller, which is what adding no
translation means.

They drive nicegui.testing.user_simulation rather than the user fixture,
because that fixture fails a test on any ERROR log and a render that raises
logs one. user_simulation is what the fixture is built on and what
nicegui.testing exports, so the lower-level entry point is the library's own
and not a way around it."
```

---

## Final verification

- [ ] **Run the full check on a clean tree**

Run: `make lint typecheck test`
Expected: all pass. Compare the collected count against `git stash`ing the branch: it must be higher than 153 by exactly the tests this plan added, minus the three it deleted.

- [ ] **Check each acceptance criterion against a test, by name**

For each bullet in `docs/milestones/CR1/spec.md`, name the test that proves it and run it:

| Criterion | Test |
| --- | --- |
| an App name cannot address a directory outside the environments root | `test_a_traversing_app_name_deletes_nothing`, `test_an_absolute_app_name_is_refused`, `test_environment_refuses_a_name_that_is_not_one_segment` |
| `to_error_info` describes an App's subclass of the public base | `test_an_app_subclass_of_the_public_base_is_described`, `test_an_app_defined_error_answers_with_a_result_not_a_protocol_error` |
| every framework exception derives from the base and the catalogue sees it | `test_every_framework_error_is_covered_here`, unedited except for its `CASES` row |
| two Pages declaring one name fail at registration | `test_two_pages_declaring_one_name_do_not_open_a_window` |
| the published schema is the one the payload is serialized against | `test_the_published_output_schema_describes_every_member_the_payload_carries` |
| `PageRegistry.definitions()` and the second `ToolRegistry` are gone or used | both methods are deleted and a running App holds one `ToolRegistry`, per ADR-027; `test_two_tools_declaring_one_name_do_not_open_a_window` covers what enumerating the declaration made necessary |
| an MCP or NiceGUI import anywhere in the core fails a test | `test_no_core_module_imports_a_channel_sdk`, `test_importing_the_core_loads_no_channel_sdk` |

- [ ] **Confirm the documents changed only where CR1 made them false**

Run: `git diff main --stat -- docs/architecture`
Expected: `errors.md` (two rows), `page-model.md` (one paragraph deleted, one sentence added). No other architecture file, and no file under `docs/decisions/`.
