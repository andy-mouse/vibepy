# M8-M9 Configuration and the App Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An App declares what it requires of its host, a channel validates that declaration before it acquires anything, and an installed package can be discovered from its metadata and described from inside its own environment.

**Architecture:** `AppDefinition` gains a second type parameter and a `config: type[ConfigT]` field, so what an App requires is a readable type rather than code hidden in a lifespan. `Lifespan` takes that validated model as its only argument, and both window functions validate a raw mapping against the declaration before entering the lifespan, so no App ever sees an unvalidated value. `src/vibepy/app/entrypoint.py` adds `AppEntrypoint` — the composition root as a value — and the description types it projects to; `src/vibepy/app/package.py` reads `vibepy.apps` entry points out of distribution metadata without importing anything, and loads one when asked; `src/vibepy/describe.py` is the `python -m` command that does the loading inside the App's own interpreter.

**Tech Stack:** Python 3.12, Pydantic v2 (`model_validate`, `model_json_schema`, `SecretStr`), `importlib.metadata` (`distributions`, `EntryPoint`), pytest with `pytest-asyncio` in `asyncio_mode = "auto"`, ruff, pyright strict, uv.

## Global Constraints

- Spec: `docs/milestones/M8-M9/spec.md`. Implement it exactly; build nothing beyond it.
- Neither `Any` nor `cast` appears anywhere in `src/` or `tests/`.
- Optional and configuration parameters are keyword-only.
- Framework exceptions derive from `VibepyError`. Exception types are the contract, message strings are not.
- Exhaustive branches over typed unions end with `else: assert_never(value)`.
- Filesystem paths are `pathlib.Path`, never strings, in every signature this plan adds.
- Standard `logging` only, `getLogger(__name__)` per module. No `print` — except `src/vibepy/describe.py`, whose entire contract is writing JSON to standard output; it uses `sys.stdout.write`.
- Tests verify public contracts, not internals.
- `make lint typecheck test` passes at the end of every task.
- Line length 100 (`ruff`), lint rules `E, F, I, UP, B, ASYNC, RUF`.
- A pre-commit hook runs ruff and pyright on commit; a failing hook means the commit did not happen.
- Do not edit `docs/roadmap.md`.
- No new dependency is added. Everything used here is the standard library or an existing dependency.
- Nothing under `src/vibepy/tool/` or `src/vibepy/page/` may import `mcp` or `nicegui`. The existing test enforcing this stays green.

## Verified facts

Checked on this repository's interpreter (CPython 3.12.13, pydantic 2.x, pyright strict, uv 0.12.1). Do not redesign around a remembered API.

- A `dist-info` directory containing only `METADATA` and `entry_points.txt` is enough for `distributions(path=[dir])` to yield it. `dist.name`, `dist.version` and `dist.entry_points.select(group=...)` then read `.name`, `.value`, `.module`, `.attr` **without importing the providing module** — verified by asserting the module is absent from `sys.modules` afterwards.
- The same directory placed on `PYTHONPATH` is found by plain `entry_points(group=...)` in a subprocess, and `EntryPoint.load()` there returns the declared object.
- `EntryPoint.load()` raises `ModuleNotFoundError` when the module is missing and `AttributeError` when the attribute is missing. Catch `(ImportError, AttributeError)`: `ModuleNotFoundError` is a subclass of `ImportError`.
- `ValidationError.errors()` entries carry `loc` as a tuple, so `".".join(str(part) for part in entry["loc"])` is the field path. A missing required field yields `loc == ("db_path",)` and `type == "missing"`.
- `SecretStr` masks itself in both `repr()` and `str()` of the enclosing model (`api_token=SecretStr('**********')`), and `get_secret_value()` returns the real value. Its JSON schema is `{"format": "password", "title": ..., "type": "string", "writeOnly": True}`.
- A `BaseModel` subclass with no fields validates `{}` and ignores unknown keys, which is what `NoConfig` needs.
- Under pyright strict, `AppDefinition[Store, Cfg]` is **not** assignable to `AppDefinition[object, BaseModel]`: `DepsT` is inferred contravariant because it reaches a handler parameter. Do not write an erased parameter type. `isinstance(value, AppEntrypoint)` on a value annotated `object` narrows cleanly under strict and needs no Protocol.
- `uv tool install` creates one virtual environment per tool under `uv tool dir` (`~/.local/share/uv/tools/<tool>/`), each with its own `bin/`, its own `lib/python3.X/site-packages/` carrying that tool's `.dist-info`, and `pyvenv.cfg` recording `include-system-site-packages = false`.

---

### Task 1: The configuration error

The smallest deliverable: one exception and its category, with nothing depending on it yet.

**Files:**
- Modify: `src/vibepy/errors.py`
- Modify: `src/vibepy/__init__.py`
- Test: `tests/test_errors.py`

**Interfaces:**
- Consumes: `VibepyError`, `ErrorCategory`, `to_error_info` — already present.
- Produces: `AppConfigInvalidError(app_id: str, fields: Sequence[str])` with `code = "config.invalid"`, `details() -> {"app_id": ..., "fields": "a, b"}`. Task 2 raises it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_errors.py`:

```python
def test_invalid_configuration_is_a_caller_failure_naming_its_fields() -> None:
    info = to_error_info(AppConfigInvalidError("todo-app", ["db_path", "limits.max"]))

    assert info.code == "config.invalid"
    assert info.category is ErrorCategory.CALLER
    assert info.details == {"app_id": "todo-app", "fields": "db_path, limits.max"}
```

Add `AppConfigInvalidError` to that file's `from vibepy.errors import (...)` block.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_errors.py -k configuration -v`
Expected: FAIL with `ImportError: cannot import name 'AppConfigInvalidError'`.

- [ ] **Step 3: Implement the exception**

In `src/vibepy/errors.py`, after `PageRouteConflictError`:

```python
class AppConfigInvalidError(VibepyError):
    """Raw configuration did not satisfy the App's declared configuration model."""

    code = "config.invalid"

    def __init__(self, app_id: str, fields: Sequence[str]) -> None:
        super().__init__(f"Configuration for App {app_id!r} failed validation")
        self.app_id = app_id
        self.fields = tuple(fields)

    def details(self) -> Mapping[str, str]:
        return {"app_id": self.app_id, "fields": ", ".join(self.fields)}
```

Add `from collections.abc import Mapping, Sequence` to the imports, and the category entry:

```python
    AppConfigInvalidError.code: ErrorCategory.CALLER,
```

- [ ] **Step 4: Export it**

In `src/vibepy/__init__.py`, add `AppConfigInvalidError` to the `from vibepy.errors import (...)` block and to `__all__`, keeping `__all__` alphabetically sorted. Update the expected list in `tests/test_package.py` to match.

- [ ] **Step 5: Run the whole suite**

Run: `make lint typecheck test`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/vibepy/errors.py src/vibepy/__init__.py tests/test_errors.py tests/test_package.py
git commit -m "Give invalid configuration a code of its own"
```

---

### Task 2: Configuration is declared, and validated before the window opens

The breaking change, landed atomically: the declaration, the lifespan signature, both window functions, the MCP adapter's builder, and every call site in the suite.

**Files:**
- Modify: `src/vibepy/app/model.py`
- Modify: `src/vibepy/app/composition.py`
- Modify: `src/vibepy/app/__init__.py`
- Modify: `src/vibepy/adapters/mcp/server.py:65-67` (signature and its call to `tool_runtime_for`)
- Modify: `src/vibepy/__init__.py`
- Test: `tests/test_app_config.py` (create)
- Modify: `tests/lifecycle.py`, `tests/todo_fixture.py`, `tests/test_app_composition.py`, `tests/test_mcp_adapter.py`, `tests/test_nicegui_adapter.py`, `tests/test_dual_channel.py`, `tests/test_execution_semantics.py`, `tests/test_package.py`

**Interfaces:**
- Consumes: `AppConfigInvalidError` from Task 1.
- Produces, for Tasks 3-6:
  - `NoConfig()` — a `BaseModel` with no fields.
  - `AppDefinition[DepsT, ConfigT: BaseModel]` with fields `app_id`, `name`, `version`, `config: type[ConfigT]`, `tools`, `pages`, in that order.
  - `type Lifespan[DepsT, ConfigT] = Callable[[ConfigT], AbstractAsyncContextManager[DepsT]]`.
  - `tool_runtime_for(definition, lifespan, /, *, config: Mapping[str, object])` and `page_runtime_for(...)` with the same shape.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_config.py`:

```python
"""Configuration is a declaration, and a window validates it before acquiring anything."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from pydantic import BaseModel, SecretStr

from vibepy.app import AppDefinition, NoConfig, tool_runtime_for
from vibepy.errors import AppConfigInvalidError


class StoreConfig(BaseModel):
    db_path: Path
    api_token: SecretStr


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

    assert sorted(schema["properties"]) == ["api_token", "db_path"]
    assert schema["properties"]["api_token"]["writeOnly"] is True
```

`model_json_schema()` returns a `dict`, so these subscripts type-check. The description
dataclasses of Task 3 type their schemas as `Mapping[str, object]`, which does not — Task 3
carries the helper that reads those.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_app_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'NoConfig' from 'vibepy.app'`.

- [ ] **Step 3: Declare configuration on the definition**

Rewrite `src/vibepy/app/model.py`:

```python
"""Declaration of an App. A value: it holds no resource and no runtime state."""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from vibepy.page.model import Page
from vibepy.tool.runtime import Tool


class NoConfig(BaseModel):
    """The configuration of an App that requires nothing of its host.

    Declared explicitly rather than defaulted, so that one validation path serves
    every App and the framework never guesses that an App needs nothing.
    """


@dataclass(frozen=True)
class AppDefinition[DepsT, ConfigT: BaseModel]:
    """Everything a channel needs to know about an App without running it.

    ``DepsT`` is the app's own type for its application-scoped resource. The
    definition declares that its Tools require one of that type; it does not
    declare where one comes from. An entrypoint supplies that at composition
    time, and the type checker rejects a mismatch at that one site. See
    `docs/decisions/ADR-021-a-declaration-holds-no-resource-factory.md`.

    ``config`` is the opposite kind of type: one the framework validates against
    and projects. It is what this App requires of its host, and it is readable
    without acquiring anything.
    """

    app_id: str
    name: str
    version: str
    config: type[ConfigT]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
```

- [ ] **Step 4: Validate at the window boundary**

In `src/vibepy/app/composition.py`, change the alias, add the validation helper, and thread the keyword through both window functions:

```python
type Lifespan[DepsT, ConfigT] = Callable[[ConfigT], AbstractAsyncContextManager[DepsT]]
"""A factory returning the app's resource for the life of one window.

It receives the App's validated configuration and nothing else. What precedes the
``yield`` runs as the window opens and what follows runs as it closes.
"""


def _validated[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT], raw: Mapping[str, object], /
) -> ConfigT:
    """Validate raw configuration against what the App declared.

    Raised before a lifespan is entered, so a window that cannot run acquires
    nothing.
    """
    try:
        return definition.config.model_validate(dict(raw))
    except ValidationError as error:
        fields = [".".join(str(part) for part in entry["loc"]) for entry in error.errors()]
        raise AppConfigInvalidError(definition.app_id, fields) from error


@asynccontextmanager
async def tool_runtime_for[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> AsyncGenerator[ToolRuntime[DepsT]]:
    """The Agent channel's window: one ToolRuntime over one acquired resource."""
    registry = tool_registry_for(definition)
    validated = _validated(definition, config)
    async with lifespan(validated) as dependencies:
        yield ToolRuntime(app_id=definition.app_id, registry=registry, dependencies=dependencies)


@asynccontextmanager
async def page_runtime_for[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> AsyncGenerator[PageRuntime]:
    """The Web channel's window: one PageRuntime over that same invocation path.

    A Page reaches Tools through ToolInvoker, which ToolRuntime satisfies, so the
    Web channel gets the canonical invocation path without seeing the runtime.
    """
    registry = page_registry_for(definition)
    async with tool_runtime_for(definition, lifespan, config=config) as tools:
        yield PageRuntime(registry=registry, tools=tools)
```

Add `from collections.abc import Mapping`, `from pydantic import BaseModel, ValidationError` and `from vibepy.errors import AppConfigInvalidError` to that module's imports. Leave `tool_registry_for` and `page_registry_for` unchanged apart from their type parameters becoming `[DepsT, ConfigT: BaseModel]`.

- [ ] **Step 5: Export `NoConfig`**

Add `NoConfig` to `src/vibepy/app/__init__.py`'s import block and `__all__`, and to `src/vibepy/__init__.py`'s import block and `__all__`. Update the expected list in `tests/test_package.py`.

- [ ] **Step 6: Thread the keyword through the MCP adapter**

In `src/vibepy/adapters/mcp/server.py`, change the signature to

```python
def build_mcp_server[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> Server[ToolRuntime[DepsT]]:
```

and pass `config=config` where it calls `tool_runtime_for`. Add the `Mapping` and `BaseModel` imports. `register_pages` in `src/vibepy/adapters/nicegui/web.py` reads declarations only; change its type parameters to `[DepsT, ConfigT: BaseModel]` and nothing else.

- [ ] **Step 7: Rewire every call site in the suite**

Mechanical, and the type checker finds each one. Apply exactly these:

- `tests/lifecycle.py`: `async def no_dependencies(_config: NoConfig) -> AsyncGenerator[None]`, importing `NoConfig` from `vibepy.app`.
- `tests/todo_fixture.py`: add `class TodoConfig(BaseModel): db_path: Path`; give `TodoStore.__init__` a `db_path: Path` parameter it stores on `self.db_path` and nothing else reads; change `todo_lifespan` to `async def todo_lifespan(config: TodoConfig) -> AsyncGenerator[TodoStore]: yield TodoStore(config.db_path)`; declare `config=TodoConfig` in `TODO_APP` and annotate it `AppDefinition[TodoStore, TodoConfig]`; add `TODO_CONFIG: dict[str, object] = {"db_path": "/tmp/vibepy-todo.db"}` for tests to pass as `config=`.
- `tests/test_app_composition.py`: `journal_definition` declares `config=NoConfig` and returns `AppDefinition[Journal, NoConfig]`; every `journal_lifespan(log)` becomes a one-argument lifespan; `lambda: FailingAcquire(log)` becomes `lambda _config: FailingAcquire(log)`; every `tool_runtime_for(...)`/`page_runtime_for(...)` call gains `config={}`.
- `tests/test_mcp_adapter.py`, `tests/test_nicegui_adapter.py`: every definition declares `config=NoConfig`; every call gains `config={}`, except the Todo cases, which pass `config=TODO_CONFIG`.
- `tests/test_dual_channel.py`, `tests/test_execution_semantics.py`: the `RENDEZVOUS` definition and the local lifespans take `NoConfig`; every window and `build_mcp_server` call gains `config={}`. The barrier and the divergence assertions are untouched.

- [ ] **Step 8: Run the whole suite**

Run: `make lint typecheck test`
Expected: all green, including `tests/test_app_config.py`.

- [ ] **Step 9: Commit**

```bash
git add src tests
git commit -m "Declare an App's configuration and validate it before the window"
```

---

### Task 3: The entrypoint is a value, and it describes itself

**Files:**
- Create: `src/vibepy/app/entrypoint.py`
- Modify: `src/vibepy/app/__init__.py`, `src/vibepy/__init__.py`
- Test: `tests/test_app_entrypoint.py` (create)
- Modify: `tests/todo_fixture.py`, `tests/test_package.py`

**Interfaces:**
- Consumes: `AppDefinition`, `Lifespan`, `NoConfig` from Task 2.
- Produces, for Tasks 5 and 6:
  - `AppEntrypoint[DepsT, ConfigT: BaseModel]` with fields `definition` and `lifespan`, and `describe() -> AppDescription`.
  - `AppDescription(app_id, name, version, config_schema, tools, pages)`, `ToolDescription(name, description, input_schema, output_schema)`, `PageDescription(name, route, title)` — all frozen, all schemas `Mapping[str, object]`, both sequences `tuple[..., ...]`.
  - `tests/todo_fixture.py` exports `TODO_ENTRYPOINT: AppEntrypoint[TodoStore, TodoConfig]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_entrypoint.py`:

```python
"""An entrypoint is a value, and describing it requires no resource."""

from collections.abc import Mapping, Sequence

from tests.todo_fixture import TODO_ENTRYPOINT


def properties(schema: Mapping[str, object], /) -> Sequence[str]:
    """The property names of a JSON schema typed as a plain mapping.

    A description carries `Mapping[str, object]`, so a subscript yields `object`
    and cannot be sorted. Narrowing here keeps every assertion below readable.
    """
    section = schema["properties"]
    assert isinstance(section, dict)
    return sorted(str(key) for key in section)


def test_a_description_carries_the_declared_identity() -> None:
    description = TODO_ENTRYPOINT.describe()

    assert description.app_id == "todo-app"
    assert description.name == "Todo"
    assert description.version == "0.0.0"


def test_a_description_carries_the_configuration_schema() -> None:
    description = TODO_ENTRYPOINT.describe()

    assert properties(description.config_schema) == ["db_path"]


def test_a_description_carries_every_tool_with_both_schemas() -> None:
    description = TODO_ENTRYPOINT.describe()

    assert [tool.name for tool in description.tools] == ["create_todo", "list_todos"]
    create = description.tools[0]
    assert create.description == "Create a todo"
    assert properties(create.input_schema) == ["title"]
    assert properties(create.output_schema) == ["done", "id", "title"]


def test_a_description_carries_every_page_route() -> None:
    description = TODO_ENTRYPOINT.describe()

    assert [(page.name, page.route, page.title) for page in description.pages] == [
        ("todos", "/todos", "Todos")
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_app_entrypoint.py -v`
Expected: FAIL with `ImportError: cannot import name 'TODO_ENTRYPOINT'`.

- [ ] **Step 3: Implement the entrypoint and the description**

Create `src/vibepy/app/entrypoint.py`:

```python
"""The composition root as a value, and the projection a reader gets from it.

A declaration holds no factory, so the pairing of a definition with a lifespan
needs an object of its own. That object is what a package names, and it is not a
declaration. See
`docs/decisions/ADR-021-a-declaration-holds-no-resource-factory.md`.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel

from vibepy.app.composition import Lifespan
from vibepy.app.model import AppDefinition


@dataclass(frozen=True)
class ToolDescription:
    """One Tool, as a reader that cannot import the App sees it."""

    name: str
    description: str
    input_schema: Mapping[str, object]
    output_schema: Mapping[str, object]


@dataclass(frozen=True)
class PageDescription:
    """One Page, as a reader that cannot import the App sees it."""

    name: str
    route: str
    title: str


@dataclass(frozen=True)
class AppDescription:
    """One App's declarations, carrying no type parameter and no resource.

    This is what crosses a process boundary, which is why every schema is a plain
    mapping and nothing here is generic.
    """

    app_id: str
    name: str
    version: str
    config_schema: Mapping[str, object]
    tools: tuple[ToolDescription, ...]
    pages: tuple[PageDescription, ...]


@dataclass(frozen=True)
class AppEntrypoint[DepsT, ConfigT: BaseModel]:
    """What a package names: one definition and the lifespan that resources it."""

    definition: AppDefinition[DepsT, ConfigT]
    lifespan: Lifespan[DepsT, ConfigT]

    def describe(self) -> AppDescription:
        """Project the declarations. Reads no configuration and enters no lifespan."""
        return AppDescription(
            app_id=self.definition.app_id,
            name=self.definition.name,
            version=self.definition.version,
            config_schema=self.definition.config.model_json_schema(),
            tools=tuple(
                ToolDescription(
                    name=tool.definition.name,
                    description=tool.definition.description,
                    input_schema=tool.definition.input_model.model_json_schema(),
                    output_schema=tool.definition.output_model.model_json_schema(),
                )
                for tool in self.definition.tools
            ),
            pages=tuple(
                PageDescription(
                    name=page.definition.name,
                    route=page.definition.route,
                    title=page.definition.title,
                )
                for page in self.definition.pages
            ),
        )
```

- [ ] **Step 4: Give the Todo fixture an entrypoint**

Add `AppEntrypoint` to `tests/todo_fixture.py`'s `from vibepy.app import ...` line, then append
at the end of the file:

```python
TODO_ENTRYPOINT: AppEntrypoint[TodoStore, TodoConfig] = AppEntrypoint(
    definition=TODO_APP, lifespan=todo_lifespan
)
```

- [ ] **Step 5: Export the new names**

Add `AppDescription`, `AppEntrypoint`, `PageDescription`, `ToolDescription` to `src/vibepy/app/__init__.py` and `src/vibepy/__init__.py`, keeping `__all__` sorted, and update `tests/test_package.py`.

- [ ] **Step 6: Run the whole suite**

Run: `make lint typecheck test`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src tests
git commit -m "Name the composition root and let it describe itself"
```

---

### Task 4: Discovery reads metadata and imports nothing

**Files:**
- Create: `src/vibepy/app/package.py`
- Modify: `src/vibepy/app/__init__.py`, `src/vibepy/__init__.py`
- Test: `tests/test_app_package.py` (create), `tests/test_app_isolation.py` (create)
- Modify: `tests/test_package.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces, for Task 5 and Task 6:
  - `APP_GROUP = "vibepy.apps"`.
  - `AppRef(app_name, distribution, distribution_version, module, attr)` — frozen, all `str`.
  - `discover_apps(*, path: Sequence[Path] | None = None) -> tuple[AppRef, ...]`, ordered by `(app_name, distribution)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_package.py`:

```python
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
    (dist_info / "entry_points.txt").write_text(
        f"[vibepy.apps]\n{declared}\n", encoding="utf-8"
    )


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
```

Create `tests/test_app_isolation.py`:

```python
"""The invariant, proven rather than assumed: inspection imports nothing."""

import sys
from pathlib import Path

from tests.test_app_package import write_distribution, write_module

from vibepy.app import discover_apps


def test_discovery_does_not_import_the_app_it_finds(tmp_path: Path) -> None:
    write_distribution(
        tmp_path,
        distribution="untouched-app",
        version="0.1.0",
        entries=[("untouched", "untouched_app.entry:app")],
    )
    write_module(tmp_path, package="untouched_app", attr="app")

    refs = discover_apps(path=[tmp_path])

    assert [ref.app_name for ref in refs] == ["untouched"]
    assert "untouched_app" not in sys.modules
    assert "untouched_app.entry" not in sys.modules
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_app_package.py tests/test_app_isolation.py -v`
Expected: FAIL with `ImportError: cannot import name 'discover_apps' from 'vibepy.app'`.

- [ ] **Step 3: Implement discovery**

Create `src/vibepy/app/package.py`:

```python
"""Reading what an installed distribution declares, without importing it.

Entry point metadata is written to ``entry_points.txt`` in a distribution's
``dist-info`` at build time and is read from there, so a reader learns what an
environment offers without executing any of it. Only ``EntryPoint.load`` imports,
and this module's discovery never calls it.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import distributions
from pathlib import Path

logger = logging.getLogger(__name__)

APP_GROUP = "vibepy.apps"
"""The entry point group an App declares itself in.

A group name is metadata read as a string and imports nothing, so it claims no
distribution name on any index.
"""


@dataclass(frozen=True)
class AppRef:
    """Where an App is declared. Carries no imported object and no declaration."""

    app_name: str
    distribution: str
    distribution_version: str
    module: str
    attr: str


def discover_apps(*, path: Sequence[Path] | None = None) -> tuple[AppRef, ...]:
    """Every App declared in an environment, ordered and without importing one.

    ``path`` is forwarded to the distribution finder, so an environment other
    than the running interpreter's can be enumerated. That is what lets a host
    inspect an App it must not import.
    """
    found = distributions() if path is None else distributions(path=[str(entry) for entry in path])
    refs = [
        AppRef(
            app_name=entry.name,
            distribution=dist.name,
            distribution_version=dist.version,
            module=entry.module,
            attr=entry.attr,
        )
        for dist in found
        for entry in dist.entry_points.select(group=APP_GROUP)
    ]
    logger.debug("discovered %d App declaration(s)", len(refs))
    return tuple(sorted(refs, key=lambda ref: (ref.app_name, ref.distribution)))
```

- [ ] **Step 4: Export the new names**

Add `APP_GROUP`, `AppRef`, `discover_apps` to `src/vibepy/app/__init__.py` and `src/vibepy/__init__.py`, keeping `__all__` sorted, and update `tests/test_package.py`.

- [ ] **Step 5: Run the whole suite**

Run: `make lint typecheck test`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src tests
git commit -m "Discover an App from metadata without importing it"
```

---

### Task 5: Loading one reference, with the two failures distinguished

**Files:**
- Modify: `src/vibepy/app/package.py`
- Modify: `src/vibepy/errors.py`, `src/vibepy/__init__.py`, `src/vibepy/app/__init__.py`
- Test: `tests/test_app_package.py`, `tests/test_errors.py`
- Modify: `tests/test_package.py`

**Interfaces:**
- Consumes: `AppRef`, `APP_GROUP` from Task 4; `AppEntrypoint`, `AppDescription` from Task 3.
- Produces, for Task 6: `describe_app(ref: AppRef, /) -> AppDescription`; `AppEntrypointUnloadableError(app_name, reference)` with code `package.entrypoint_unloadable`; `AppEntrypointInvalidError(app_name, reference, found)` with code `package.entrypoint_invalid`. Both are `declaration` failures.

- [ ] **Step 1: Write the failing tests**

Add these imports to the top of `tests/test_app_package.py`, merged into its existing import
block so that ruff's import ordering is satisfied and no import sits below a definition:

```python
import pytest

from tests.todo_fixture import TODO_ENTRYPOINT
from vibepy.app import AppRef, describe_app
from vibepy.errors import AppEntrypointInvalidError, AppEntrypointUnloadableError
```

Then append these tests to the end of the file:

```python
def test_a_declared_entrypoint_is_loaded_and_described() -> None:
    ref = AppRef(
        app_name="todo",
        distribution="tests",
        distribution_version="0.0.0",
        module="tests.todo_fixture",
        attr="TODO_ENTRYPOINT",
    )

    assert describe_app(ref) == TODO_ENTRYPOINT.describe()


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
        module="tests.todo_fixture",
        attr="NOT_DECLARED",
    )

    with pytest.raises(AppEntrypointUnloadableError):
        describe_app(ref)


def test_an_object_that_is_not_an_entrypoint_is_rejected() -> None:
    ref = AppRef(
        app_name="wrong",
        distribution="wrong",
        distribution_version="0.0.0",
        module="tests.todo_fixture",
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
```

Create `tests/impostor_fixture.py`:

```python
"""An object that looks describable and is not an App entrypoint."""


class Impostor:
    def describe(self) -> str:
        return "not an AppDescription"


IMPOSTOR = Impostor()
```

Append to `tests/test_errors.py`, adding both exception names to that file's existing
`from vibepy.errors import (...)` block:

```python
def test_an_unloadable_entrypoint_is_a_declaration_failure() -> None:
    info = to_error_info(AppEntrypointUnloadableError("todo", "todo_app.entry:app"))

    assert info.code == "package.entrypoint_unloadable"
    assert info.category is ErrorCategory.DECLARATION
    assert info.details == {"app_name": "todo", "reference": "todo_app.entry:app"}


def test_an_entrypoint_of_the_wrong_type_is_a_declaration_failure() -> None:
    info = to_error_info(AppEntrypointInvalidError("todo", "todo_app.entry:app", "AppDefinition"))

    assert info.code == "package.entrypoint_invalid"
    assert info.category is ErrorCategory.DECLARATION
    assert info.details == {
        "app_name": "todo",
        "reference": "todo_app.entry:app",
        "found": "AppDefinition",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_app_package.py tests/test_errors.py -v`
Expected: FAIL with `ImportError: cannot import name 'describe_app'`.

- [ ] **Step 3: Implement the two exceptions**

In `src/vibepy/errors.py`, after `AppConfigInvalidError`:

```python
class AppEntrypointUnloadableError(VibepyError):
    """A declared entrypoint could not be resolved: no such module, or no such attribute."""

    code = "package.entrypoint_unloadable"

    def __init__(self, app_name: str, reference: str) -> None:
        super().__init__(f"Entrypoint {reference!r} declared by App {app_name!r} did not load")
        self.app_name = app_name
        self.reference = reference

    def details(self) -> Mapping[str, str]:
        return {"app_name": self.app_name, "reference": self.reference}


class AppEntrypointInvalidError(VibepyError):
    """A declared entrypoint resolved to something other than an AppEntrypoint."""

    code = "package.entrypoint_invalid"

    def __init__(self, app_name: str, reference: str, found: str) -> None:
        super().__init__(
            f"Entrypoint {reference!r} declared by App {app_name!r} resolved to {found}"
        )
        self.app_name = app_name
        self.reference = reference
        self.found = found

    def details(self) -> Mapping[str, str]:
        return {"app_name": self.app_name, "reference": self.reference, "found": self.found}
```

And two category entries:

```python
    AppEntrypointUnloadableError.code: ErrorCategory.DECLARATION,
    AppEntrypointInvalidError.code: ErrorCategory.DECLARATION,
```

- [ ] **Step 4: Implement loading**

Append to `src/vibepy/app/package.py`:

```python
def describe_app(ref: AppRef, /) -> AppDescription:
    """Load one declared entrypoint and project it.

    This imports, so it belongs in the App's own environment. A host that cannot
    import an App runs it there instead: see `src/vibepy/describe.py`.
    """
    reference = f"{ref.module}:{ref.attr}"
    entry = EntryPoint(name=ref.app_name, value=reference, group=APP_GROUP)
    try:
        loaded: object = entry.load()
    except (ImportError, AttributeError) as error:
        raise AppEntrypointUnloadableError(ref.app_name, reference) from error
    if not isinstance(loaded, AppEntrypoint):
        raise AppEntrypointInvalidError(ref.app_name, reference, type(loaded).__name__)
    return loaded.describe()
```

Add `EntryPoint` to the `importlib.metadata` import, and import `AppDescription` and `AppEntrypoint` from `vibepy.app.entrypoint` plus the two exceptions from `vibepy.errors`.

- [ ] **Step 5: Export and run**

Add `describe_app` to `src/vibepy/app/__init__.py` and `src/vibepy/__init__.py`, add `AppEntrypointInvalidError` and `AppEntrypointUnloadableError` to the root exports, keep `__all__` sorted, update `tests/test_package.py`.

Run: `make lint typecheck test`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src tests
git commit -m "Load a declared entrypoint and distinguish how it can fail"
```

---

### Task 6: The self-description command

**Files:**
- Create: `src/vibepy/describe.py`
- Test: `tests/test_describe_command.py` (create), `tests/test_app_isolation.py` (extend)

**Interfaces:**
- Consumes: `discover_apps`, `describe_app` from Tasks 4-5.
- Produces: `python -m vibepy.describe` writing a JSON array to standard output, one object per App, with keys `app_id`, `name`, `version`, `config_schema`, `tools`, `pages`. Exit code 0 when every declared App describes, 1 when any raises, with the framework's normalized error written to standard error.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_describe_command.py`:

```python
"""The command that describes an App from inside its own environment."""

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.test_app_package import write_distribution

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_describe(environment_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the command with an extra environment on the path, as a host would."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(environment_root), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "vibepy.describe"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def declare_todo(root: Path) -> None:
    write_distribution(
        root,
        distribution="todo-fixture-app",
        version="9.9.9",
        entries=[("todo", "tests.todo_fixture:TODO_ENTRYPOINT")],
    )


def test_the_command_writes_a_description_of_every_declared_app(tmp_path: Path) -> None:
    declare_todo(tmp_path)

    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    described = json.loads(result.stdout)
    assert len(described) == 1
    assert described[0]["app_id"] == "todo-app"
    assert described[0]["version"] == "0.0.0"
    assert sorted(described[0]["config_schema"]["properties"]) == ["db_path"]
    assert [tool["name"] for tool in described[0]["tools"]] == ["create_todo", "list_todos"]
    assert [page["route"] for page in described[0]["pages"]] == ["/todos"]


def test_an_environment_declaring_no_app_describes_nothing(tmp_path: Path) -> None:
    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_an_unloadable_declaration_fails_with_the_framework_code(tmp_path: Path) -> None:
    write_distribution(
        tmp_path,
        distribution="broken-app",
        version="0.1.0",
        entries=[("broken", "no_such_module_anywhere:app")],
    )

    result = run_describe(tmp_path)

    assert result.returncode == 1
    assert "package.entrypoint_unloadable" in result.stderr
```

Append to `tests/test_app_isolation.py`:

```python
def test_a_description_is_obtained_without_this_process_loading_the_app(tmp_path: Path) -> None:
    declare_todo(tmp_path)

    result = run_describe(tmp_path)

    assert result.returncode == 0, result.stderr
    described = json.loads(result.stdout)
    assert described[0]["app_id"] == "todo-app"
```

Add `import json` and `from tests.test_describe_command import declare_todo, run_describe` to
that file's imports. The claim is that the loading happened in another interpreter, which the
subprocess boundary establishes; asserting on this process's `sys.modules` would prove nothing,
because the suite imports the Todo fixture for its own tests.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_describe_command.py -v`
Expected: FAIL with a non-zero exit and `No module named vibepy.describe` in stderr.

- [ ] **Step 3: Implement the command**

Create `src/vibepy/describe.py`:

```python
"""Describe every App declared in this interpreter's environment, as JSON.

A host cannot import an App: each App is installed into an environment of its own,
and importing one would put that App's dependencies in the host's process. So the
host runs this module with that environment's interpreter and reads the result.
"""

import json
import logging
import sys
from dataclasses import asdict

from vibepy.app.package import describe_app, discover_apps
from vibepy.errors import VibepyError, to_error_info

logger = logging.getLogger(__name__)


def main() -> int:
    """Write one JSON object per declared App to standard output."""
    try:
        described = [asdict(describe_app(ref)) for ref in discover_apps()]
    except VibepyError as error:
        info = to_error_info(error)
        sys.stderr.write(json.dumps({"code": info.code, "message": info.message}) + "\n")
        return 1
    sys.stdout.write(json.dumps(described) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`asdict` turns the frozen description dataclasses into nested dictionaries, and every leaf is already JSON-compatible: the schemas are Pydantic's own `dict` output and the rest are strings.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_describe_command.py tests/test_app_isolation.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `make lint typecheck test`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src tests
git commit -m "Describe an App from inside its own environment"
```

---

### Task 7: The documents

Code is done; this task makes the repository's documents true again. One role per document, and the same fact is not stated twice.

**Files:**
- Create: `docs/decisions/ADR-022-configuration-is-a-declaration.md`
- Create: `docs/decisions/ADR-023-a-package-points-at-its-app-through-an-entry-point.md`
- Create: `docs/architecture/packaging.md`
- Modify: `docs/architecture/app-model.md`, `docs/architecture/runtime.md`, `docs/architecture/lifecycle.md`, `docs/architecture/errors.md`, `docs/architecture.md`, `AGENTS.md`

**Interfaces:**
- Consumes: everything Tasks 1-6 built. No code changes.
- Produces: no code.

- [ ] **Step 1: Write ADR-022**

Nygard format, `Status: Accepted`. Context: configuration is today read inside a lifespan, which is a callable and not a readable declaration, so nothing can answer what an App requires without running it, and a missing value fails outside the error model. Decision: `AppDefinition` declares `config: type[ConfigT]`, the declaration is required and an App requiring nothing declares `NoConfig`, a window validates a raw mapping against it before entering the lifespan, and the origin of that mapping is left to the installation model. Consequences: one validation path rather than two; a rejected window acquires nothing; secrets separate by type through `SecretStr` and not by storage; and **no per-invocation resource scope is introduced** — the question `docs/architecture/app-model.md` left to M8 is answered "no", because no milestone requires one and it would be a second dependency mechanism beside `ToolContext`. Cite `docs/milestones/M8-M9/spec.md`'s sources for the Pydantic behaviour.

- [ ] **Step 2: Write ADR-023**

Nygard format, `Status: Accepted`. Context: nothing connects an installed distribution to the App inside it; ADR-010 deferred the executable entrypoint to this layer; a host cannot import an App because `uv tool install` gives each tool its own environment and ADR-017 gives each channel its own process. Decision: an App declares itself in the `vibepy.apps` entry point group; inspection reads metadata without importing; loading happens in the App's own interpreter through `python -m vibepy.describe`. Consequences: no manifest format is invented; the group name claims no distribution name on any index; pytest and pluggy are the precedent for the declaration and the counter-example for in-process loading; one group is defined and M19 adds others by declaring them; and the isolation invariant is recorded with its enforcement boundary — the framework guarantees that it imports no App into its caller and that description runs under the App's interpreter, while one-environment-per-App is a requirement on the installation model that packaging cannot enforce, satisfied by `uv tool install`, required of M10's Hub and hardened by M17. Cite the entry points specification, `importlib.metadata`, the core metadata specification's statement that installers ignore `Obsoletes-Dist`, the pytest and pluggy pages, and the uv documentation.

- [ ] **Step 3: Write `docs/architecture/packaging.md`**

The sole owner of: the `vibepy.apps` group and what an App writes in its `pyproject.toml`; `AppEntrypoint` as the composition root's value; the inspection/loading split with `AppRef`, `discover_apps`, `describe_app` and `AppDescription`; the self-description command and why a host uses it; and the isolation invariant's three parts with their enforcement boundary. It states no fact that `app-model.md` already owns — link instead.

- [ ] **Step 4: Update the architecture documents**

- `app-model.md`: `AppDefinition` gains `config` in the code block and a paragraph on what it declares; the "A future version may add an optional config model" sentence is replaced by the fact; the running-window signatures gain the `config` keyword; the "There is no per-invocation *resource* scope" paragraph is rewritten to state the decision and cite ADR-022 rather than defer to M8; the invariants list gains the configuration declaration; a link to `packaging.md` replaces the "A future distribution layer may introduce a package" sentence.
- `runtime.md`: one sentence in "Dependency ownership" saying a window validates configuration before it acquires anything, citing ADR-022.
- `lifecycle.md`: the `configure` step in "Package lifecycle" gains the sentence saying who validates and when, and links `packaging.md`.
- `errors.md`: three rows in the code table and, if the message needs it, one sentence in the categories discussion. No new category.
- `architecture.md`: link `packaging.md`.
- `AGENTS.md`: two invariants, worded as the spec's Documentation section states them.

- [ ] **Step 5: Verify the documents against the code**

Run: `make lint typecheck test`
Expected: all green — no code changed, so this is a regression check.

Re-read each new document beside the code it describes and check every signature, name and code string letter by letter. A document that misnames a field is worse than no document.

- [ ] **Step 6: Commit**

```bash
git add docs AGENTS.md
git commit -m "Record the configuration and packaging decisions"
```

---

## Done

- `make lint typecheck test` passes.
- The six acceptance criteria in `docs/milestones/M8-M9/spec.md` each have a test naming them.
- Then, and only then, use `superpowers:finishing-a-development-branch`: the milestone folder is promoted and deleted on integration, and the merge into `main` is `--no-ff`.
