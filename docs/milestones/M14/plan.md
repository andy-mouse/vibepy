# M14 - Permissions and security: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Tool call carries a principal and a channel, and ToolRuntime refuses a call the declaration or the App's policy does not allow, before the handler and before input validation.

**Architecture:** `Principal` and `Channel` are new channel-neutral value types. `ToolDefinition` gains `read_only`, `channels`, `required_roles`; `ToolRuntime` holds the window's channel and takes a principal per `invoke`, running the framework's default policy and then the App's `policy` before building the `ToolContext`. Hosts (`serve`, `mcp`, `invoke`) decide the principal and pass it through the adapters; the MCP adapter filters discovery by `channels` and projects `read_only` as `readOnlyHint`. A new `expense-app` fixture proves the role gate through the `invoke` command.

**Tech Stack:** Python 3.12, pydantic 2, MCP Python SDK v2 (`mcp>=2.1`), NiceGUI 3, pytest + pytest-asyncio, uv workspace.

## Global Constraints

- Spec: `docs/milestones/M14/spec.md`. Acceptance criteria are the tests; `docs/roadmap.md` is never edited.
- `make lint typecheck test` must pass at the end; run it after each task where the task says so.
- No `Any`, no `cast` in the public API. Keyword-only optional parameters. Frozen dataclasses for in-process declarations; pydantic for data crossing a boundary.
- Exhaustive branches over `Channel` end with `else: assert_never(value)`.
- Standard `logging`, no `print`. Paths are `pathlib.Path`.
- Pre-production: no compatibility shims. Every construction site in the repository is updated in the same task that changes a signature.
- Tests verify public contracts. One file per subject. A test that cannot fail is deleted.
- Commit after each task; messages in the repository's style (a sentence saying what and why, no conventional-commit prefix). End with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Run tests with `uv run pytest <path> -q`; the whole gate with `make lint typecheck test`.
- Docstrings on public surfaces are written in the repository's voice at the end (Task 11), not mid-way; a new public symbol still gets a one-line docstring when created so `ruff` passes.

---

## File map

| File | Responsibility |
| --- | --- |
| `src/vibepy_core/principal.py` (new) | `Principal` |
| `src/vibepy_core/channel.py` (new) | `Channel` |
| `src/vibepy_core/tool/model.py` | `ToolDefinition` (+`read_only`, `channels`, `required_roles`), `ToolContext` (+`principal`, `channel`) |
| `src/vibepy_core/tool/policy.py` (new) | `AuthorizationRequest`, `ToolPolicy`, `default_policy` |
| `src/vibepy_core/tool/runtime.py` | `ToolRuntime(channel=…)`, `invoke(…, *, principal)`, policy steps |
| `src/vibepy_core/errors.py` | `ToolForbiddenError`, catalogue row |
| `src/vibepy_core/app/model.py` | `AppDefinition.policy` |
| `src/vibepy_core/app/composition.py` | `tool_runtime_for(…, channel=)`, `page_runtime_for` passes `Channel.WEB` |
| `src/vibepy_core/page/model.py` | `PrincipalToolInvoker` |
| `src/vibepy_core/page/runtime.py` | `render(name, *, principal)`, bound invoker |
| `src/vibepy_core/adapters/mcp/projection.py` | `readOnlyHint` |
| `src/vibepy_core/adapters/mcp/server.py` | channel filter, `principal=` |
| `src/vibepy_core/adapters/nicegui/web.py`, `application.py` | `principal=` through to `render` |
| `src/vibepy_core/serve.py`, `mcp.py`, `invoke.py` | hosts decide the principal |
| `src/vibepy_core/__init__.py`, `tool/__init__.py`, `page/__init__.py` | exports |
| `fixtures/expense-app/` (new) | the role-gated App |
| `fixtures/*/src/*/entry.py` | `read_only` on every Tool |
| `packages/vibepy-studio/src/vibepy_studio/{authoring,operating}/tools/*.py` | `read_only`, `channels` |
| `packages/vibepy-studio/src/vibepy_studio/authoring/tools/invocation.py` | forwards channel and principal |
| `tests/test_tool_authorization.py` (new) | the refusal contract |
| `docs/architecture/*.md`, `docs/decisions/ADR-034-…md` | documentation |

---

### Task 0: A shape that crosses a process boundary is one pydantic model, owned by core

Done first, so that every field M14 adds lands on a derived surface once, instead of on three hand-written copies that a later task would then remove.

**Files:**
- Modify: `src/vibepy_core/errors.py` (`ErrorInfo` → `BaseModel`; delete `_Report`, `_REPORT`; `report_line`, `read_report_line`), `src/vibepy_core/adapters/mcp/server.py` (`_payload`), `src/vibepy_core/app/entrypoint.py` (`ToolDescription`, `PageDescription`, `AppDescription` → `BaseModel`), `src/vibepy_core/app/package.py` (new `DescribedApp`), `src/vibepy_core/describe.py`, `src/vibepy_core/app/__init__.py`, `src/vibepy_core/__init__.py`
- Modify: `src/vibepy_core/app/config.py` (`ConfigFieldType`, `ConfigFieldDescription`, `config_fields_of`), `src/vibepy_core/adapters/nicegui/application.py` (`_report`), `src/vibepy_core/invoke.py` (`InvocationRequest`)
- Modify (Studio, delete the copies): `packages/vibepy-studio/src/vibepy_studio/models.py` (`Diagnostic`, `Described`, `DescribedTool`, `DescribedPage`, `diagnostic_of`), `internals/describing.py`, `operating/internals/configuration.py` (`_SchemaField`, `_ConfigSchema`, `_kind`), `authoring/models.py`, `operating/models.py`, `operating/pages/board.py`, `operating/pages/presentation.py`, `operating/tools/{configuration,installation,packages,runtime}.py`
- Test: `tests/test_errors.py`, `tests/test_describe_command.py`, `tests/test_app_entrypoint.py`, `packages/vibepy-studio/tests/test_installation.py`, `test_presentation.py`, `tests_support.py`

**Interfaces:**
- Produces:
  - `class ErrorInfo(BaseModel): code: str; category: ErrorCategory; message: str; details: dict[str, str] = {}` (frozen: `model_config = ConfigDict(frozen=True)`)
  - `report_line(info) -> str` = `info.model_dump_json() + "\n"`; `read_report_line(line) -> ErrorInfo | None` = `ErrorInfo.model_validate_json(line)` or `None` on `ValidationError`
  - `class ToolDescription(BaseModel): name, description, input_schema: dict[str, JsonValue], output_schema: dict[str, JsonValue]` (Task 2 adds `read_only`, `channels`, `required_roles`)
  - `class PageDescription(BaseModel): name, route, title`
  - `class ConfigFieldType(StrEnum): STRING="string"; PATH="path"; INTEGER="integer"; SECRET="secret"; OTHER="other"` and `class ConfigFieldDescription(BaseModel): name: str; type: ConfigFieldType; required: bool` (in `app/config.py`, with `config_fields_of(model: type[AppConfig]) -> list[ConfigFieldDescription]` deriving them: for each `name, field in model.model_fields.items()`, `type` from the annotation — `SecretStr` → SECRET, `Path` → PATH, `int` → INTEGER, `str` → STRING, else OTHER; `required = field.is_required()`)
  - `class AppDescription(BaseModel): app_id, name, version, config_schema: dict[str, JsonValue], config_fields: list[ConfigFieldDescription], tools: list[ToolDescription], pages: list[PageDescription]`
  - `class DescribedApp(AppDescription): app_name: str; distribution: str; distribution_version: str` — the `describe` command's per-App entry, in `vibepy_core/app/package.py` beside `AppRef`, built by `described(ref: AppRef) -> DescribedApp`
  - `class InvocationRequest(BaseModel): model_config = ConfigDict(extra="forbid"); input: dict[str, JsonValue] = {}` in `vibepy_core/invoke.py`, exported from `vibepy_core`; replaces `_Request`
  - Studio imports `ErrorInfo` where it had `Diagnostic`, `DescribedApp` where it had `Described`, `InvocationRequest` where it built `{"input": …}`; `AppFacts(described: DescribedApp, purelib: Path | None = None)` with `has_pages` a `@property` over `described.pages`.

- [ ] **Step 1: Write the failing tests**

`tests/test_nicegui_adapter.py` (or `tests/test_serve_command.py`, wherever the window-failure log is asserted today) — the logged line parses with `read_report_line` into the `ErrorInfo` of the failure.

`packages/vibepy-studio/tests/test_installation.py` — an installed App's facts carry its described Tools: `facts.described.tools[0].name == "create_todo"` for the Todo fixture.

`tests/test_errors.py` — add:
```python
def test_a_report_line_round_trips_as_the_same_error_info() -> None:
    info = to_error_info(ToolNotFoundError("x"))
    assert read_report_line(report_line(info)) == info


def test_a_line_naming_an_unknown_category_is_not_a_report() -> None:
    assert read_report_line('{"code": "a.b", "category": "weather", "message": "", "details": {}}') is None
```
Replace the existing test that reads an unknown category as `EXECUTION` (it asserted the tolerance this task removes) with the second test above. The positional construction at `tests/test_errors.py:294` becomes keyword construction.

`tests/test_app_entrypoint.py` — add:
```python
def test_a_description_derives_its_configuration_fields_from_the_types() -> None:
    class Config(AppConfig):
        root: Path
        token: SecretStr
        port: int = 8080
        note: str | None = None

    fields = {f.name: (f.type, f.required) for f in entrypoint_with_config(Config).describe().config_fields}
    assert fields == {
        "root": (ConfigFieldType.PATH, True),
        "token": (ConfigFieldType.SECRET, True),
        "port": (ConfigFieldType.INTEGER, False),
        "note": (ConfigFieldType.OTHER, False),
    }
```
(`entrypoint_with_config` builds an `AppEntrypoint` over a definition with that config; add it beside the file's existing helpers.)

`tests/test_describe_command.py` — replace the local `Described` TypedDict and `described_app` helper with `DescribedApp.model_validate` over each entry of `json.loads(result.stdout)`; assertions keep their meaning (`app_name`, `distribution`, `distribution_version`, `app_id`, tool names, page routes).

- [ ] **Step 2: Run** the three files — FAIL.

- [ ] **Step 3: Implement core**

`errors.py`:
```python
class ErrorInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    category: ErrorCategory
    message: str
    details: dict[str, str] = {}


def report_line(info: ErrorInfo, /) -> str:
    return info.model_dump_json() + "\n"


def read_report_line(line: str, /) -> ErrorInfo | None:
    try:
        return ErrorInfo.model_validate_json(line)
    except ValidationError:
        return None
```
Delete `_Report`, `_REPORT` and the `TypeAdapter` import. `to_error_info` passes `details=dict(error.details())`.

`adapters/mcp/server.py`: `_payload(error) -> dict[str, object]` returns `to_error_info(error).model_dump(mode="json")`.

`adapters/nicegui/application.py::_report`: `logger.error(to_error_info(failure).model_dump_json())`; drop the `json` import.

`invoke.py`: rename `_Request` to `InvocationRequest`, export it; nothing else changes here (Task 8 adds the arguments).

`app/entrypoint.py`: the three descriptions become `BaseModel`s with the fields above (`tuple[...]` → `list[...]`, `Mapping` → `dict`); `describe()` constructs them by keyword as today.

`app/package.py`:
```python
class DescribedApp(AppDescription):
    """One entry of what `describe` writes: the declaration's identity, and its description."""

    app_name: str
    distribution: str
    distribution_version: str


def described(ref: AppRef, /) -> DescribedApp:
    """Load one declared entrypoint and describe it with its identity."""
    description = _load(ref).describe()
    return DescribedApp(
        app_name=ref.app_name,
        distribution=ref.distribution,
        distribution_version=ref.distribution_version,
        **description.model_dump(),
    )
```
Keep `describe_app(ref) -> AppDescription` as it is (Studio and tests use it). `describe.py` writes `TypeAdapter(list[DescribedApp]).dump_json([described(ref) for ref in discover_apps()])` — one `TypeAdapter` for the list, which is the documented use. Export `DescribedApp`, `described` from `vibepy_core.app` and `vibepy_core`.

- [ ] **Step 4: Implement Studio**
- `internals/describing.py`: `_DESCRIBED = TypeAdapter(list[DescribedApp])`; every `Described` annotation → `DescribedApp`.
- `models.py`: delete `Diagnostic`, `Described`, `DescribedTool`, `DescribedPage`. `diagnostic_of(reported: ErrorInfo, /, **details) -> ErrorInfo` becomes `reported.model_copy(update={"details": {**details, **reported.details}})`; keep it only if a caller merges details, else delete and use the `ErrorInfo` directly.
- Every `Diagnostic(` construction (`authoring/models.py`, `operating/models.py`, `operating/tools/*`) → `ErrorInfo(`; every `Diagnostic` annotation → `ErrorInfo`; `board.py`/`presentation.py` read the same four fields.
- `authoring/models.py`: `AppInspection.apps: list[DescribedApp]`.
- `authoring/tools/invocation.py`: `stdin=InvocationRequest(input=payload.input).model_dump_json()`.
- `operating/models.py`: `AppFacts` becomes `described: DescribedApp`, `purelib: Path | None = None`, `@property has_pages -> bool: return bool(self.described.pages)`; delete the eight copied fields and their docstrings (the "only writer" rationale moves to the class docstring). `installer.py` builds `AppFacts(described=entry)`. The 25 reads `facts.app_id`, `facts.name`, `facts.version`, `facts.distribution_version`, `facts.config_schema`, `facts.declared_name`, `facts.distribution` in `operating/internals/configuration.py`, `operating/tools/{configuration,installation,runtime}.py` and Studio tests become `facts.described.app_id`, …, `facts.described.app_name`, `facts.described.distribution`. Existing `facts.json` files are not migrated: pre-production.
- `operating/internals/configuration.py`: delete `_SchemaField`, `_ConfigSchema`, `_kind`; `config_fields(...)`, `secret_fields(...)` and `is_configured` read `AppFacts.config_fields` (a `list[ConfigFieldDescription]` carried beside `config_schema`, filled from the `DescribedApp` Studio already reads) — `secret_fields` is `[f.name for f in fields if f.type is ConfigFieldType.SECRET]`. Delete Studio's `ConfigField`; `ConfigDescription.fields: list[ConfigFieldDescription]`. The board renders `field.type.value`.

- [ ] **Step 5: Run** `make lint typecheck test` — PASS. (Studio's integration tests exercise `describe` and the report path end to end.)
- [ ] **Step 6: Commit** — `A shape that crosses a process boundary is one pydantic model: ErrorInfo and the App description are written and read as the same type in core, and Studio's copies are gone`.

---

### Task 1: `Principal` and `Channel`

**Files:**
- Create: `src/vibepy_core/principal.py`, `src/vibepy_core/channel.py`
- Modify: `src/vibepy_core/__init__.py`
- Test: `tests/test_tool_core.py` (append)

**Interfaces:**
- Produces: `Principal(id: str, roles: frozenset[str] = frozenset())` frozen dataclass; `Channel(StrEnum)` with `WEB = "web"`, `AGENT = "agent"`. Both exported from `vibepy_core`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_tool_core.py`:

```python
from vibepy_core import Channel, Principal


def test_a_principal_is_an_id_and_a_set_of_roles() -> None:
    alice = Principal(id="alice", roles=frozenset({"manager"}))
    nobody = Principal(id="nobody")

    assert alice.roles == {"manager"}
    assert nobody.roles == frozenset()
    with pytest.raises(FrozenInstanceError):
        alice.id = "bob"  # pyright: ignore[reportAttributeAccessIssue]


def test_the_channels_are_a_closed_set() -> None:
    assert [channel.value for channel in Channel] == ["web", "agent"]
```

- [ ] **Step 2: Run** `uv run pytest tests/test_tool_core.py -q` — expect `ImportError` on `Channel, Principal`.

- [ ] **Step 3: Implement**

`src/vibepy_core/principal.py`:
```python
"""Who is invoking. Asserted by a host, threaded by the framework, never derived here."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """One caller: an identity and the roles its host asserts for it."""

    id: str
    roles: frozenset[str] = frozenset()
```

`src/vibepy_core/channel.py`:
```python
"""The channels an App is exposed through."""

from enum import StrEnum


class Channel(StrEnum):
    """One of the two first-class channels. Fixed when a window opens."""

    WEB = "web"
    AGENT = "agent"
```

`src/vibepy_core/__init__.py`: add `from vibepy_core.channel import Channel` and `from vibepy_core.principal import Principal`; add `"Channel"` and `"Principal"` to `__all__` in sorted position.

- [ ] **Step 4: Run** `uv run pytest tests/test_tool_core.py -q` — PASS.
- [ ] **Step 5: Commit** — `Principal and Channel: who is calling, and through which channel`.

---

### Task 2: `ToolDefinition` declares `read_only`, `channels`, `required_roles`

**Files:**
- Modify: `src/vibepy_core/tool/model.py`
- Modify (every `ToolDefinition(` call, adding `read_only=`): `fixtures/todo-app/src/todo_app/entry.py`, `fixtures/notes-app/src/notes_app/entry.py`, `fixtures/timer-app/src/timer_app/entry.py`, `packages/vibepy-studio/src/vibepy_studio/authoring/tools/inspection.py`, `packages/vibepy-studio/src/vibepy_studio/authoring/tools/invocation.py`, `packages/vibepy-studio/src/vibepy_studio/operating/tools/{configuration,installation,packages,runtime}.py`, every file under `tests/` and `packages/vibepy-studio/tests/` that constructs one (`grep -rn "ToolDefinition(" tests packages fixtures src`).
- Test: `tests/test_tool_core.py`

**Interfaces:**
- Produces: `ToolDefinition(..., read_only: bool, channels: frozenset[Channel] = frozenset(Channel), required_roles: frozenset[str] = frozenset())`. `read_only` is keyword, required.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_tool_core.py`:

```python
def test_a_tool_declares_its_side_effects_exposure_and_roles() -> None:
    definition = ToolDefinition(
        name="approve",
        description="Approve",
        input_model=EmptyInput,
        output_model=TodoList,
        read_only=False,
        channels=frozenset({Channel.WEB}),
        required_roles=frozenset({"manager"}),
    )

    assert definition.read_only is False
    assert definition.channels == {Channel.WEB}
    assert definition.required_roles == {"manager"}


def test_a_tool_is_exposed_on_both_channels_to_anyone_unless_it_says_otherwise() -> None:
    definition = list_todos_tool().definition

    assert definition.channels == frozenset(Channel)
    assert definition.required_roles == frozenset()


def test_read_only_has_no_default() -> None:
    with pytest.raises(TypeError):
        ToolDefinition(  # pyright: ignore[reportCallIssue]
            name="x", description="x", input_model=EmptyInput, output_model=TodoList
        )
```

- [ ] **Step 2: Run** `uv run pytest tests/test_tool_core.py -q` — FAIL (`unexpected keyword argument 'read_only'`).

- [ ] **Step 3: Implement** in `src/vibepy_core/tool/model.py`:

```python
from vibepy_core.channel import Channel
from vibepy_core.principal import Principal  # used in Task 4; import now is fine


@dataclass(frozen=True)
class ToolDefinition[InputT: BaseModel, OutputT: BaseModel]:
    """Static declaration of a Tool. Both models are required, and so is `read_only`."""

    name: str
    description: str
    input_model: type[InputT]
    output_model: type[OutputT]
    read_only: bool
    channels: frozenset[Channel] = frozenset(Channel)
    required_roles: frozenset[str] = frozenset()
```

(Leave `input_schema`/`output_schema` untouched. Remove the `Principal` import if pyright/ruff flags it unused; Task 4 adds it back.)

- [ ] **Step 4: Update every construction site.** For each `ToolDefinition(` add `read_only=True` for a Tool that reads and `read_only=False` for one that writes:

| Site | `read_only` |
| --- | --- |
| todo `create_todo`, `complete_todo` | False |
| todo `list_todos` | True |
| notes `measure_note` | True |
| timer `elapsed` | True |
| Studio `inspect_framework`, `inspect_app`, `list_apps`, `describe_config` | True |
| Studio `invoke_tool`, `install_app`, `remove_app`, `update_app`, `configure_app`, `start_app`, `stop_app`, `register_package_source`, `remove_package_source` | False |
| tests: any `create_*`/`complete_*`/`measure`/`rename`/`boom` style definitions | False unless the test's Tool only reads; when in doubt, False |

Do **not** set `channels` on Studio Tools yet (Task 9).

- [ ] **Step 5: Describe the new fields.** `ToolDescription` (core, `app/entrypoint.py`) gains `read_only: bool`, `channels: list[Channel]`, `required_roles: list[str]`; `describe()` fills them from the declaration (`sorted(definition.channels)`, `sorted(definition.required_roles)`). Test, in `tests/test_app_entrypoint.py`:

```python
def test_a_description_carries_a_tools_side_effects_exposure_and_roles() -> None:
    described = entrypoint_with(ToolDefinition(..., read_only=True, channels=frozenset({Channel.AGENT}), required_roles=frozenset({"manager"}))).describe()
    tool = described.tools[0]
    assert (tool.read_only, tool.channels, tool.required_roles) == (True, [Channel.AGENT], ["manager"])
```
(use the file's existing entrypoint-building helper for `entrypoint_with`). Because Task 0 made the description the one model both `describe` and Studio use, nothing else changes for these fields to reach an agent through `inspect_app`.

- [ ] **Step 6: Run** `uv run pytest -q -m "not integration"` then `uv run pyright` — PASS.
- [ ] **Step 7: Commit** — `A Tool declares whether it reads, where it is exposed and what roles it requires, and its description says so`.

---

### Task 3: `ToolForbiddenError`

**Files:**
- Modify: `src/vibepy_core/errors.py`, `src/vibepy_core/__init__.py`, `docs/architecture/errors.md`
- Test: `tests/test_errors.py`

**Interfaces:**
- Produces: `ToolForbiddenError(tool_name: str, *, principal: str, channel: str, reason: str)`; `code = "tool.forbidden"`; category `CALLER`; `details()` → `{"tool_name", "principal", "channel", "reason"}`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_errors.py`:

```python
from vibepy_core.errors import ToolForbiddenError


def test_a_forbidden_call_names_who_where_and_why() -> None:
    error = ToolForbiddenError(
        "approve_expense", principal="alice", channel="agent", reason="role_required"
    )
    info = to_error_info(error)

    assert info.code == "tool.forbidden"
    assert info.category is ErrorCategory.CALLER
    assert info.details == {
        "tool_name": "approve_expense",
        "principal": "alice",
        "channel": "agent",
        "reason": "role_required",
    }
```

- [ ] **Step 2: Run** `uv run pytest tests/test_errors.py -q` — FAIL (ImportError).

- [ ] **Step 3: Implement** in `src/vibepy_core/errors.py`, after `ToolOutputValidationError`:

```python
class ToolForbiddenError(VibepyError):
    """The caller may not invoke this Tool here: not exposed on the channel, a role missing, or refused by the App's policy."""

    code = "tool.forbidden"

    def __init__(self, tool_name: str, *, principal: str, channel: str, reason: str) -> None:
        """Record who was refused, where, and why."""
        super().__init__(
            f"{principal!r} may not invoke {tool_name!r} through the {channel} channel: {reason}"
        )
        self.tool_name = tool_name
        self.principal = principal
        self.channel = channel
        self.reason = reason

    def details(self) -> Mapping[str, str]:
        """Return the Tool, the principal id, the channel and the reason."""
        return {
            "tool_name": self.tool_name,
            "principal": self.principal,
            "channel": self.channel,
            "reason": self.reason,
        }
```

Add `ToolForbiddenError.code: ErrorCategory.CALLER,` to `ERROR_CATALOG` after `ToolOutputValidationError`. Export from `vibepy_core/__init__.py`.

In `docs/architecture/errors.md` add the row `| tool.forbidden | caller | ToolForbiddenError |` after `tool.output_invalid`.

- [ ] **Step 4: Run** `uv run pytest tests/test_errors.py -q` — PASS (the catalogue walk picks the class up automatically).
- [ ] **Step 5: Commit** — `tool.forbidden: a call the declaration or the App's policy refuses`.

---

### Task 4: ToolRuntime authorizes before it validates

**Files:**
- Create: `src/vibepy_core/tool/policy.py`, `tests/test_tool_authorization.py`
- Modify: `src/vibepy_core/tool/model.py` (`ToolContext`), `src/vibepy_core/tool/runtime.py`, `src/vibepy_core/tool/__init__.py`, `src/vibepy_core/__init__.py`, `src/vibepy_core/app/model.py`
- Modify (construction/invoke sites): `tests/test_tool_core.py`, `tests/test_execution_semantics.py`, `tests/test_dual_channel.py`, `tests/test_channel_neutrality.py`, `tests/test_page_core.py`, `tests/test_mcp_adapter.py`, `tests/test_nicegui_adapter.py`, and `src/vibepy_core/app/composition.py` (temporarily pass `channel=Channel.AGENT` and a placeholder principal where needed so the suite compiles; Task 5 finishes composition).

**Interfaces:**
- Produces:
  - `ToolContext(app_id, invocation_id, dependencies, principal: Principal, channel: Channel)`
  - `AuthorizationRequest(definition: ToolDefinition[BaseModel, BaseModel], principal: Principal, channel: Channel)` frozen dataclass
  - `class ToolPolicy(Protocol): def authorize(self, request: AuthorizationRequest, /) -> None`
  - `default_policy: ToolPolicy` (module-level instance of `_DefaultPolicy`)
  - `AppDefinition(..., policy: ToolPolicy | None = None)`
  - `ToolRuntime(*, app_id, registry, dependencies, channel: Channel, policy: ToolPolicy | None = None)`
  - `ToolRuntime.invoke(name, raw_input, /, *, principal: Principal) -> BaseModel`

- [ ] **Step 1: Write the failing tests** — `tests/test_tool_authorization.py`:

```python
"""The refusal contract: ToolRuntime authorizes before it validates, from the declaration."""

import pytest
from pydantic import BaseModel

from vibepy_core import Channel, Principal
from vibepy_core.errors import ToolForbiddenError
from vibepy_core.tool import (
    AuthorizationRequest,
    Tool,
    ToolContext,
    ToolDefinition,
    ToolRegistry,
    ToolRuntime,
)


class Amount(BaseModel):
    amount: int


class Receipt(BaseModel):
    amount: int
    by: str


class Recorder:
    def __init__(self) -> None:
        self.calls: list[ToolContext[object]] = []


async def approve(ctx: ToolContext[Recorder], payload: Amount) -> Receipt:
    ctx.dependencies.calls.append(ctx)
    return Receipt(amount=payload.amount, by=ctx.principal.id)


def approve_tool(
    *, channels: frozenset[Channel] = frozenset(Channel), roles: frozenset[str] = frozenset()
) -> Tool[Recorder]:
    return Tool(
        definition=ToolDefinition(
            name="approve",
            description="Approve an amount",
            input_model=Amount,
            output_model=Receipt,
            read_only=False,
            channels=channels,
            required_roles=roles,
        ),
        handler=approve,
    )


def runtime(tool: Tool[Recorder], *, channel: Channel, policy=None) -> tuple[ToolRuntime[Recorder], Recorder]:
    registry: ToolRegistry[Recorder] = ToolRegistry()
    registry.register(tool)
    recorder = Recorder()
    return (
        ToolRuntime(app_id="expense", registry=registry, dependencies=recorder, channel=channel, policy=policy),
        recorder,
    )


ALICE = Principal(id="alice")
MANAGER = Principal(id="bob", roles=frozenset({"manager"}))


async def test_a_tool_not_exposed_on_the_channel_is_refused_before_the_handler() -> None:
    run, recorder = runtime(approve_tool(channels=frozenset({Channel.WEB})), channel=Channel.AGENT)

    with pytest.raises(ToolForbiddenError) as refused:
        await run.invoke("approve", {"amount": 1}, principal=ALICE)

    assert refused.value.reason == "not_exposed"
    assert recorder.calls == []


async def test_a_role_gated_tool_refuses_a_principal_without_the_role() -> None:
    run, recorder = runtime(approve_tool(roles=frozenset({"manager"})), channel=Channel.AGENT)

    with pytest.raises(ToolForbiddenError) as refused:
        await run.invoke("approve", {"amount": 1}, principal=ALICE)

    assert refused.value.reason == "role_required"
    assert refused.value.details()["principal"] == "alice"
    assert recorder.calls == []


async def test_a_role_gated_tool_runs_for_a_principal_with_the_role() -> None:
    run, recorder = runtime(approve_tool(roles=frozenset({"manager"})), channel=Channel.AGENT)

    result = await run.invoke("approve", {"amount": 1}, principal=MANAGER)

    assert result == Receipt(amount=1, by="bob")
    assert len(recorder.calls) == 1


async def test_a_tool_requiring_no_role_runs_for_a_principal_with_none() -> None:
    run, _ = runtime(approve_tool(), channel=Channel.WEB)

    assert await run.invoke("approve", {"amount": 2}, principal=ALICE) == Receipt(amount=2, by="alice")


async def test_refusal_comes_before_input_validation() -> None:
    run, recorder = runtime(approve_tool(roles=frozenset({"manager"})), channel=Channel.AGENT)

    with pytest.raises(ToolForbiddenError):
        await run.invoke("approve", {"amount": "not a number"}, principal=ALICE)
    assert recorder.calls == []


class RefuseEveryone:
    def authorize(self, request: AuthorizationRequest, /) -> None:
        raise ToolForbiddenError(
            request.definition.name,
            principal=request.principal.id,
            channel=request.channel.value,
            reason="closed_for_audit",
        )


async def test_an_app_policy_may_refuse_with_its_own_reason() -> None:
    run, recorder = runtime(approve_tool(), channel=Channel.AGENT, policy=RefuseEveryone())

    with pytest.raises(ToolForbiddenError) as refused:
        await run.invoke("approve", {"amount": 1}, principal=MANAGER)

    assert refused.value.reason == "closed_for_audit"
    assert recorder.calls == []


class AdmitEveryone:
    def authorize(self, request: AuthorizationRequest, /) -> None:
        return None


async def test_an_app_policy_cannot_admit_what_the_declaration_refuses() -> None:
    run, recorder = runtime(
        approve_tool(roles=frozenset({"manager"})), channel=Channel.AGENT, policy=AdmitEveryone()
    )

    with pytest.raises(ToolForbiddenError) as refused:
        await run.invoke("approve", {"amount": 1}, principal=ALICE)

    assert refused.value.reason == "role_required"
    assert recorder.calls == []


async def test_the_context_carries_the_principal_and_the_channel() -> None:
    run, recorder = runtime(approve_tool(), channel=Channel.WEB)

    await run.invoke("approve", {"amount": 1}, principal=ALICE)

    ctx = recorder.calls[0]
    assert ctx.principal == ALICE
    assert ctx.channel is Channel.WEB
```

- [ ] **Step 2: Run** `uv run pytest tests/test_tool_authorization.py -q` — FAIL (ImportError `AuthorizationRequest`).

- [ ] **Step 3: Implement**

`src/vibepy_core/tool/policy.py`:
```python
"""Operation-level authorization: from the declaration, the principal and the channel, before input."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from vibepy_core.channel import Channel
from vibepy_core.errors import ToolForbiddenError
from vibepy_core.principal import Principal
from vibepy_core.tool.model import ToolDefinition


@dataclass(frozen=True)
class AuthorizationRequest:
    """One call as a policy sees it: the Tool declared, who is calling, and through which channel."""

    definition: ToolDefinition[BaseModel, BaseModel]
    principal: Principal
    channel: Channel


class ToolPolicy(Protocol):
    """Refuses a call by raising `ToolForbiddenError`; returns to allow it."""

    def authorize(self, request: AuthorizationRequest, /) -> None:
        """Raise `ToolForbiddenError` to refuse `request`."""
        ...


class _DefaultPolicy:
    """What every declaration says: exposed on this channel, and the roles it requires."""

    def authorize(self, request: AuthorizationRequest, /) -> None:
        definition = request.definition
        if request.channel not in definition.channels:
            raise ToolForbiddenError(
                definition.name,
                principal=request.principal.id,
                channel=request.channel.value,
                reason="not_exposed",
            )
        if definition.required_roles and not (definition.required_roles & request.principal.roles):
            raise ToolForbiddenError(
                definition.name,
                principal=request.principal.id,
                channel=request.channel.value,
                reason="role_required",
            )


default_policy: ToolPolicy = _DefaultPolicy()
"""The framework's policy. It always runs, and an App's policy runs after it."""
```

`src/vibepy_core/tool/model.py` — `ToolContext`:
```python
@dataclass(frozen=True)
class ToolContext[DepsT]:
    app_id: str
    invocation_id: str
    dependencies: DepsT
    principal: Principal
    channel: Channel
```
(imports: `from vibepy_core.channel import Channel`, `from vibepy_core.principal import Principal`.)

`src/vibepy_core/tool/runtime.py` — `ToolRuntime`:
```python
from vibepy_core.channel import Channel
from vibepy_core.principal import Principal
from vibepy_core.tool.policy import AuthorizationRequest, ToolPolicy, default_policy


class ToolRuntime[DepsT]:
    def __init__(
        self,
        *,
        app_id: str,
        registry: "ToolRegistry[DepsT]",
        dependencies: DepsT,
        channel: Channel,
        policy: ToolPolicy | None = None,
    ) -> None:
        self._app_id = app_id
        self._registry = registry
        self._dependencies = dependencies
        self._channel = channel
        self._policy = policy

    async def invoke(
        self, name: str, raw_input: Mapping[str, object], /, *, principal: Principal
    ) -> BaseModel:
        tool = self._registry.resolve(name)
        request = AuthorizationRequest(
            definition=tool.definition, principal=principal, channel=self._channel
        )
        default_policy.authorize(request)
        if self._policy is not None:
            self._policy.authorize(request)
        ctx = ToolContext(
            app_id=self._app_id,
            invocation_id=str(uuid4()),
            dependencies=self._dependencies,
            principal=principal,
            channel=self._channel,
        )
        return await tool.bound(ctx, raw_input)
```
Note `policy.py` imports `tool.model` and `runtime.py` imports `policy.py`; no cycle.

`src/vibepy_core/app/model.py`:
```python
from vibepy_core.tool.policy import ToolPolicy
...
    pages: Sequence[Page]
    policy: ToolPolicy | None = None
```

`src/vibepy_core/tool/__init__.py`: export `AuthorizationRequest`, `ToolPolicy`, `default_policy`. `src/vibepy_core/__init__.py`: export `AuthorizationRequest`, `ToolPolicy`.

- [ ] **Step 4: Update construction sites so the suite compiles.**
  - `src/vibepy_core/app/composition.py::tool_runtime_for`: add keyword `channel: Channel` and pass `channel=channel, policy=definition.policy` to `ToolRuntime`; `page_runtime_for` passes `channel=Channel.WEB`. Callers of `tool_runtime_for` (`build_mcp_server`, `invoke.py`, Studio `tests_support.studio`) pass `channel=Channel.AGENT` for now.
  - Every `ToolRuntime(` in tests: add `channel=Channel.AGENT` (or `WEB` where the test is the Web side).
  - Every `ToolContext(` in tests: add `principal=Principal(id="test"), channel=Channel.AGENT`.
  - Every direct `runtime.invoke(name, raw)` in tests and in `src/vibepy_core/adapters/mcp/server.py`, `src/vibepy_core/invoke.py`: add `principal=Principal(id="test")` (adapters: a placeholder `Principal(id="agent")` — Task 6 replaces it).
  - `tests/test_page_core.py::RecordingInvoker` stays as a `ToolInvoker` (Task 5 changes PageRuntime).
  - `tests/test_tool_core.py`: add the two `test_tool_context_*` fields; append:

```python
async def test_the_context_is_created_per_invocation_with_the_principal() -> None:
    runtime = ToolRuntime(app_id="todo", registry=build_registry(), dependencies=TodoStore(), channel=Channel.AGENT)
    todo = await runtime.invoke("create_todo", {"title": "milk"}, principal=Principal(id="alice"))
    assert isinstance(todo, Todo)
```
  (Replace or extend the existing invocation test rather than duplicating it.)

- [ ] **Step 5: Run** `uv run pytest tests/test_tool_authorization.py tests/test_tool_core.py -q` — PASS. `uv run pyright` will still fail: `ToolRuntime.invoke` no longer satisfies `ToolInvoker`, so `PageRuntime` and `page_runtime_for` do not typecheck until Task 5. That is expected; Tasks 4 and 5 are one commit.
- [ ] **Step 6: Do not commit yet.** Continue to Task 5.

---

### Task 5: Pages: the principal is bound per render

**Files:**
- Modify: `src/vibepy_core/page/model.py`, `src/vibepy_core/page/runtime.py`, `src/vibepy_core/page/__init__.py`, `src/vibepy_core/__init__.py`, `src/vibepy_core/app/composition.py`
- Test: `tests/test_page_core.py`, `tests/test_app_composition.py`, `tests/test_execution_semantics.py`, `tests/test_dual_channel.py`

**Interfaces:**
- Produces:
  - `class PrincipalToolInvoker(Protocol): def invoke(self, name: str, raw_input: Mapping[str, object], /, *, principal: Principal) -> Awaitable[BaseModel]`
  - `PageRuntime(*, registry: PageRegistry, tools: PrincipalToolInvoker)`
  - `PageRuntime.render(name: str, /, *, principal: Principal) -> None`
  - `PageContext.tools` is still a `ToolInvoker`, bound to that principal.
  - `tool_runtime_for(definition, lifespan, /, *, config, channel)`; `page_runtime_for(definition, lifespan, /, *, config)` (passes `Channel.WEB`).

- [ ] **Step 1: Write the failing tests** — in `tests/test_page_core.py` replace `RecordingInvoker` with:

```python
class RecordingInvoker:
    """A PrincipalToolInvoker that records calls instead of reaching a ToolRuntime."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object], Principal]] = []

    def invoke(
        self, name: str, raw_input: Mapping[str, object], /, *, principal: Principal
    ) -> Awaitable[BaseModel]:
        self.calls.append((name, raw_input, principal))
        raise AssertionError("this fixture records calls and never returns a result")
```
and add:
```python
async def test_render_binds_the_principal_into_the_pages_invoker() -> None:
    recorder = RecordingInvoker()

    async def handler(ctx: PageContext) -> None:
        with pytest.raises(AssertionError):
            await ctx.tools.invoke("list_todos", {})

    registry = PageRegistry()
    registry.register(Page(definition=todos_definition(), handler=handler))
    runtime = PageRuntime(registry=registry, tools=recorder)

    await runtime.render("todos", principal=Principal(id="alice"))

    assert recorder.calls == [("list_todos", {}, Principal(id="alice"))]
```
Update the tests that build a `PageContext` directly: construct it with a bound invoker via `PageRuntime`, or, where a test only needs *a* `ToolInvoker`, keep a tiny local class with the unchanged `ToolInvoker` signature. `test_page_context_exposes_nothing_but_its_tool_invoker` stays as is.

- [ ] **Step 2: Run** `uv run pytest tests/test_page_core.py -q` — FAIL (`render() got an unexpected keyword argument 'principal'`).

- [ ] **Step 3: Implement**

`src/vibepy_core/page/model.py` — add after `ToolInvoker`:
```python
from vibepy_core.principal import Principal


class PrincipalToolInvoker(Protocol):
    """What PageRuntime binds a ToolInvoker from: ToolRuntime.invoke's shape, principal included."""

    def invoke(
        self, name: str, raw_input: Mapping[str, object], /, *, principal: Principal
    ) -> Awaitable[BaseModel]:
        """Invoke `name` with `raw_input` as `principal` and return its validated result."""
        ...
```

`src/vibepy_core/page/runtime.py`:
```python
from collections.abc import Awaitable, Mapping

from pydantic import BaseModel

from vibepy_core.page.model import PageContext, PrincipalToolInvoker, ToolInvoker
from vibepy_core.page.registry import PageRegistry
from vibepy_core.principal import Principal


class _BoundInvoker:
    """A ToolInvoker that invokes as one principal. Built per render, never by a Page."""

    def __init__(self, tools: PrincipalToolInvoker, principal: Principal) -> None:
        self._tools = tools
        self._principal = principal

    def invoke(self, name: str, raw_input: Mapping[str, object], /) -> Awaitable[BaseModel]:
        return self._tools.invoke(name, raw_input, principal=self._principal)


class PageRuntime:
    def __init__(self, *, registry: PageRegistry, tools: PrincipalToolInvoker) -> None:
        self._registry = registry
        self._tools = tools

    async def render(self, name: str, /, *, principal: Principal) -> None:
        page = self._registry.resolve(name)
        bound: ToolInvoker = _BoundInvoker(self._tools, principal)
        ctx = PageContext(tools=bound)
        await page.handler(ctx)
```

`src/vibepy_core/page/__init__.py` and `src/vibepy_core/__init__.py`: export `PrincipalToolInvoker`.

`src/vibepy_core/app/composition.py`: finalize `tool_runtime_for(..., *, config, channel: Channel)` and `page_runtime_for` calling it with `channel=Channel.WEB`. Import `Channel`.

- [ ] **Step 4: Update sites.** `tests/test_execution_semantics.py`, `tests/test_dual_channel.py`, `tests/test_app_composition.py`: every `pages.render(name)` → `pages.render(name, principal=Principal(id="operator"))`; every `tool_runtime_for(...)` gets `channel=Channel.AGENT` (or `WEB` for the Web side of dual-channel). The NiceGUI adapter's `_builder` calls `render(name)` — give it a placeholder `principal=Principal(id="operator")` for now; Task 7 threads the real one.

- [ ] **Step 5: Run** `uv run pytest -q -m "not integration"`, `uv run pyright`, `uv run ruff check .` — PASS.
- [ ] **Step 6: Commit Tasks 4 and 5 together** — `ToolRuntime authorizes before it validates, and a Page invokes as the principal its render was given`.

---

### Task 6: The Agent channel: discovery filters by channel, projects `readOnlyHint`, and the host names the principal

**Files:**
- Modify: `src/vibepy_core/adapters/mcp/projection.py`, `src/vibepy_core/adapters/mcp/server.py`, `src/vibepy_core/mcp.py`
- Test: `tests/test_mcp_adapter.py`, `tests/test_channel_neutrality.py`

**Interfaces:**
- Produces: `build_mcp_server(definition, lifespan, /, *, config, principal: Principal) -> Server[ToolRuntime[DepsT]]`; `to_mcp_tool` sets `annotations=types.ToolAnnotations(read_only_hint=True)` iff `definition.read_only`, else `annotations=None`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_mcp_adapter.py` (reuse the file's `create_todo_definition`/`list_todos_definition`, now with `read_only=`; define the server fixture the way the file's existing tests do, adding `principal=Principal(id="agent")`):

```python
from vibepy_core import Channel, Principal
from vibepy_core.errors import ToolForbiddenError


def test_a_read_only_tool_is_projected_with_the_standard_hint() -> None:
    projected = to_mcp_tool(list_todos_definition())
    assert projected.annotations is not None
    assert projected.annotations.read_only_hint is True


def test_a_tool_that_writes_carries_no_annotation() -> None:
    assert to_mcp_tool(create_todo_definition()).annotations is None


def web_only_definition() -> ToolDefinition[EmptyInput, TodoList]:
    return ToolDefinition(
        name="board_only",
        description="For humans",
        input_model=EmptyInput,
        output_model=TodoList,
        read_only=True,
        channels=frozenset({Channel.WEB}),
    )


async def test_discovery_omits_a_tool_not_exposed_to_agents() -> None:
    server = build_server([list_todos_tool(), web_only_tool()])  # the file's helper, extended
    async with Client(server) as agent:
        listed = await agent.list_tools()
    assert [tool.name for tool in listed.tools] == ["list_todos"]


async def test_calling_a_hidden_tool_by_name_is_forbidden_not_unknown() -> None:
    server = build_server([list_todos_tool(), web_only_tool()])
    async with Client(server) as agent:
        refused = await agent.call_tool("board_only", {})
    assert refused.is_error is True
    payload = json.loads(refused.content[0].text)  # type: ignore[union-attr]
    assert payload["code"] == "tool.forbidden"
    assert payload["details"]["reason"] == "not_exposed"


async def test_the_hosts_principal_reaches_the_handler() -> None:
    seen: list[Principal] = []

    async def who(ctx: ToolContext[None], _payload: EmptyInput) -> TodoList:
        seen.append(ctx.principal)
        return TodoList(todos=[])

    server = build_server([Tool(definition=list_todos_definition(), handler=who)], principal=Principal(id="codex"))
    async with Client(server) as agent:
        await agent.call_tool("list_todos", {})
    assert seen == [Principal(id="codex")]
```
Adapt `build_server` (or whatever the file's existing helper is called; if none, add one wrapping `AppDefinition(...)` + `build_mcp_server(..., config={}, principal=...)`). Check the SDK field name by `uv run python -c "from mcp import types; print(types.ToolAnnotations.model_fields.keys())"` — the Python SDK spells it `read_only_hint` with alias `readOnlyHint`.

- [ ] **Step 2: Run** `uv run pytest tests/test_mcp_adapter.py -q` — FAIL.

- [ ] **Step 3: Implement**

`projection.py`:
```python
def to_mcp_tool(definition: ToolDefinition[BaseModel, BaseModel]) -> types.Tool:
    return types.Tool(
        name=definition.name,
        description=definition.description,
        input_schema=definition.input_schema(),
        output_schema=definition.output_schema(),
        annotations=types.ToolAnnotations(read_only_hint=True) if definition.read_only else None,
    )
```

`server.py`:
- signature `build_mcp_server(definition, lifespan, /, *, config: Mapping[str, object], principal: Principal)`;
- `server_lifespan` opens `tool_runtime_for(definition, lifespan, config=config, channel=Channel.AGENT)`;
- `list_tools` returns `[to_mcp_tool(tool.definition) for tool in definition.tools if Channel.AGENT in tool.definition.channels]`;
- `call_tool` invokes `ctx.lifespan_context.invoke(params.name, params.arguments or {}, principal=principal)`;
- add `except ToolForbiddenError as error: return _failure(error)` beside `ToolInputValidationError`.

`mcp.py`: `build_mcp_server(entrypoint.definition, entrypoint.lifespan, config={}, principal=AGENT)` with module constant `AGENT = Principal(id="agent")` and a one-line docstring: the party that launched this process.

- [ ] **Step 4: Update sites**: every `build_mcp_server(` in `tests/` and Studio tests gets `principal=Principal(id="agent")`. In `tests/test_channel_neutrality.py` add:

```python
async def test_exposure_varies_by_channel_while_the_tool_does_not() -> None:
    calls: list[Channel] = []

    async def count(ctx: ToolContext[None], _payload: EmptyInput) -> Count:
        calls.append(ctx.channel)
        return Count(n=len(calls))

    agent_only = Tool(
        definition=ToolDefinition(
            name="count", description="Count", input_model=EmptyInput, output_model=Count,
            read_only=False, channels=frozenset({Channel.AGENT}),
        ),
        handler=count,
    )
    definition = AppDefinition(app_id="neutral", name="Neutral", version="0", config=NoConfig,
                               tools=[agent_only], pages=[])
    async with tool_runtime_for(definition, no_dependencies, config={}, channel=Channel.AGENT) as agent:
        assert (await agent.invoke("count", {}, principal=Principal(id="a"))).model_dump() == {"n": 1}
    async with tool_runtime_for(definition, no_dependencies, config={}, channel=Channel.WEB) as web:
        with pytest.raises(ToolForbiddenError) as refused:
            await web.invoke("count", {}, principal=Principal(id="a"))
    assert refused.value.reason == "not_exposed"
    assert calls == [Channel.AGENT]
```
Define `EmptyInput` and `Count(n: int)` at the top of the file if absent; import `no_dependencies` from `lifecycle`.

- [ ] **Step 5: Run** `uv run pytest tests/test_mcp_adapter.py tests/test_channel_neutrality.py tests/test_mcp_command.py -q` — PASS.
- [ ] **Step 6: Commit** — `The Agent channel lists what is exposed to agents, says which Tools only read, and invokes as the principal its host names`.

---

### Task 7: The Web channel: the host names the principal

**Files:**
- Modify: `src/vibepy_core/adapters/nicegui/web.py`, `src/vibepy_core/adapters/nicegui/application.py`, `src/vibepy_core/serve.py`
- Test: `tests/test_nicegui_adapter.py`, `tests/test_serve_command.py` (construction only)

**Interfaces:**
- Produces: `register_pages(definition, pages, /, *, principal: Principal)`; `build_web_app(definition, lifespan, /, *, config, principal: Principal) -> FastAPI`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_nicegui_adapter.py`, following `test_page_interaction_invokes_a_tool`'s arrangement:

```python
async def test_the_hosts_principal_reaches_a_pages_tool_call(user: User) -> None:
    seen: list[Principal] = []

    async def who(ctx: ToolContext[None], _payload: EmptyInput) -> Nothing:
        seen.append(ctx.principal)
        return Nothing()

    async def handler(ctx: PageContext) -> None:
        await ctx.tools.invoke("who", {})

    definition = AppDefinition(..., tools=[Tool(definition=ToolDefinition(name="who", ..., read_only=True), handler=who)], pages=[page("home", "/home", handler)])
    build_web_app(definition, no_dependencies, config={}, principal=Principal(id="operator"))
    await user.open("/home")

    assert seen == [Principal(id="operator")]
```
Use the file's own model/lifespan helpers for the elided parts.

- [ ] **Step 2: Run** `uv run pytest tests/test_nicegui_adapter.py -q` — FAIL.

- [ ] **Step 3: Implement**: `register_pages(definition, pages, /, *, principal)` passes `principal` to `_builder(pages, declared.name, principal)`, whose `build()` awaits `runtime.render(name, principal=principal)`. `build_web_app(..., *, config, principal)` calls `register_pages(definition, pages, principal=principal)`. `serve.py::_serve` calls `build_web_app(..., config={}, principal=OPERATOR)` with `OPERATOR = Principal(id="operator")`.

- [ ] **Step 4: Update sites**: every `build_web_app(`/`register_pages(` in tests gets `principal=Principal(id="operator")`.
- [ ] **Step 5: Run** `uv run pytest tests/test_nicegui_adapter.py tests/test_serve_command.py tests/test_execution_semantics.py tests/test_dual_channel.py -q` — PASS.
- [ ] **Step 6: Commit** — `The Web channel invokes as the principal its host names`.

---

### Task 8: `vibepy_core.invoke` is told its channel and principal; Studio forwards its own

**Files:**
- Modify: `src/vibepy_core/invoke.py`, `packages/vibepy-studio/src/vibepy_studio/authoring/tools/invocation.py`, `packages/vibepy-studio/tests/tests_support.py` (`studio()` passes `channel=Channel.AGENT`)
- Test: `tests/test_invoke_command.py`, `packages/vibepy-studio/tests/test_invoke_tool.py`

**Interfaces:**
- Produces: `python -m vibepy_core.invoke <app> <tool> --channel {web,agent} --principal <id> [--role <r> ...]`.

- [ ] **Step 1: Write the failing tests** — in `tests/test_invoke_command.py` change `run_invoke` to:

```python
def run_invoke(
    app: str,
    tool: str,
    request: object,
    *,
    config: dict[str, str] | None = None,
    channel: str = "agent",
    principal: str = "tester",
    roles: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, "-m", "vibepy_core.invoke", app, tool, "--channel", channel, "--principal", principal]
    for role in roles:
        argv += ["--role", role]
    return subprocess.run(argv, input=json.dumps(request), capture_output=True, text=True,
                          env={**child_environment(), **environment_for(config or {})}, check=False)
```
and add:
```python
@pytest.mark.integration
def test_channel_and_principal_are_required() -> None:
    result = subprocess.run([sys.executable, "-m", "vibepy_core.invoke", "todo-app", "list_todos"],
                            input="{}", capture_output=True, text=True, env=child_environment(), check=False)
    assert result.returncode == 2
    assert "--channel" in result.stderr and "--principal" in result.stderr
```

- [ ] **Step 2: Run** `uv run pytest tests/test_invoke_command.py -q` — FAIL (argparse rejects unknown arguments → exit 2 everywhere).

- [ ] **Step 3: Implement** in `invoke.py`:
```python
parser.add_argument("--channel", type=Channel, choices=list(Channel), required=True)
parser.add_argument("--principal", required=True)
parser.add_argument("--role", action="append", default=[])
...
principal = Principal(id=str(parsed.principal), roles=frozenset(str(r) for r in parsed.role))
result = asyncio.run(_invoke(entrypoint, str(parsed.tool_name), request, channel=parsed.channel, principal=principal))
```
`_invoke(..., *, channel: Channel, principal: Principal)` opens `tool_runtime_for(..., config={}, channel=channel)` and calls `runtime.invoke(tool_name, request.input, principal=principal)`. A `ToolForbiddenError` propagates into the existing `except Exception` → `report(error)` → exit 1 (it carries a framework code, so it is classified, not `app.unhandled`). Module docstring: add the trust-model sentence from the spec.

Studio `invocation.py::invoke_tool`: the handler is `invoke_tool(ctx, payload)`; build argv with `"--channel", ctx.channel.value, "--principal", ctx.principal.id` plus `"--role", r` per `sorted(ctx.principal.roles)`. Rename the parameter from `_ctx` to `ctx`.

`tests_support.studio()`: `tool_runtime_for(STUDIO_APP, APP.lifespan, config=..., channel=Channel.AGENT)`; every `tools.invoke(...)` in Studio tests gets `principal=Principal(id="agent")` — add a helper `AGENT = Principal(id="agent")` in `tests_support.py`.

- [ ] **Step 4: Run** `uv run pytest tests/test_invoke_command.py packages/vibepy-studio/tests/test_invoke_tool.py -q` — PASS.
- [ ] **Step 5: Commit** — `invoke is told which channel it stands in for and who is calling; Studio forwards its own`.

---

### Task 9: Studio's exposure

**Files:**
- Modify: `packages/vibepy-studio/src/vibepy_studio/authoring/tools/{inspection,invocation}.py` (`channels=frozenset({Channel.AGENT})`), `packages/vibepy-studio/src/vibepy_studio/operating/tools/{configuration,installation,packages,runtime}.py` (`channels=frozenset({Channel.WEB})`)
- Test: `packages/vibepy-studio/tests/test_authoring_over_mcp.py`, Studio board tests

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test** — in `test_authoring_over_mcp.py` replace `test_authoring_tools_are_discoverable`'s assertion with equality:

```python
    assert {tool.name for tool in listed.tools} == {"inspect_framework", "inspect_app", "invoke_tool"}
```
and add:
```python
@pytest.mark.integration
async def test_read_only_authoring_tools_say_so(tmp_path: Path) -> None:
    async with Client(studio_server(tmp_path / "studio")) as agent:
        listed = await agent.list_tools()
    hints = {tool.name: (tool.annotations.read_only_hint if tool.annotations else None) for tool in listed.tools}
    assert hints == {"inspect_framework": True, "inspect_app": True, "invoke_tool": None}
```

- [ ] **Step 2: Run** `uv run pytest packages/vibepy-studio/tests/test_authoring_over_mcp.py -q` — FAIL (operating Tools still listed).

- [ ] **Step 3: Implement**: add `channels=frozenset({Channel.AGENT})` to the three authoring definitions and `channels=frozenset({Channel.WEB})` to the ten operating definitions. Import `Channel` from `vibepy_core`.

- [ ] **Step 4: Run** `uv run pytest packages/vibepy-studio -q` — PASS. Studio's in-process tests that invoke operating Tools through `studio()` (channel AGENT) will now be refused: change `tests_support.studio()` to take `channel: Channel = Channel.WEB` and have the authoring tests pass `channel=Channel.AGENT` explicitly (or the reverse — whichever touches fewer files; state which in the commit message).
- [ ] **Step 5: Commit** — `Studio: authoring is the Agent channel's, operating is the Web channel's, as ADR-032 deferred to M14`.

---

### Task 10: The Expense fixture

**Files:**
- Create: `fixtures/expense-app/pyproject.toml`, `fixtures/expense-app/src/expense_app/__init__.py` (empty docstring module), `fixtures/expense-app/src/expense_app/py.typed`, `fixtures/expense-app/src/expense_app/entry.py`
- Modify: `pyproject.toml` (`dev` group: `"vibepy-expense"`; `[tool.uv.sources] vibepy-expense = { workspace = true }`), `uv.lock` via `uv sync`
- Test: `tests/test_invoke_command.py`, `packages/vibepy-studio/tests/test_invoke_tool.py`

**Interfaces:**
- Produces: distribution `vibepy-expense`, app `expense-app`, Tools `submit_expense`, `approve_expense` (`required_roles={"manager"}`), `list_expenses`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_invoke_command.py`:

```python
@pytest.mark.integration
def test_a_role_gated_tool_refuses_a_principal_without_the_role() -> None:
    result = run_invoke("expense-app", "approve_expense", {"input": {"id": 1}}, principal="alice")
    payload = reported(result)
    assert payload["code"] == "tool.forbidden"
    assert payload["details"]["reason"] == "role_required"


@pytest.mark.integration
def test_a_manager_passes_the_role_gate_through_the_command() -> None:
    result = run_invoke("expense-app", "approve_expense", {"input": {"id": 1}}, principal="bob", roles=("manager",))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["failure"]["code"] == "expense.not_found"
```
The second test reaches the handler (the gate passed) and gets the App's own expected failure, because each `invoke` process opens a fresh window over an empty in-memory ledger. The self-approval rule and a real approval need one window with state, so they are proven in-process, appended to `tests/test_tool_authorization.py`:

```python
from expense_app.entry import EXPENSE_APP, expense_lifespan
from vibepy_core import tool_runtime_for


async def test_expense_shows_the_two_levels_of_authorization() -> None:
    async with tool_runtime_for(EXPENSE_APP, expense_lifespan, config={}, channel=Channel.AGENT) as run:
        alice = Principal(id="alice")
        bob = Principal(id="bob", roles=frozenset({"manager"}))
        carol = Principal(id="carol", roles=frozenset({"manager"}))
        submitted = await run.invoke("submit_expense", {"amount": 40}, principal=alice)
        own = await run.invoke("submit_expense", {"amount": 5}, principal=bob)

        with pytest.raises(ToolForbiddenError) as refused:
            await run.invoke("approve_expense", {"id": submitted.model_dump()["id"]}, principal=alice)
        assert refused.value.reason == "role_required"

        self_approval = await run.invoke("approve_expense", {"id": own.model_dump()["id"]}, principal=bob)
        assert self_approval.model_dump()["failure"]["code"] == "expense.self_approval"

        approved = await run.invoke("approve_expense", {"id": submitted.model_dump()["id"]}, principal=carol)
        assert approved.model_dump()["expense"]["status"] == "approved"
```
Both command tests stay in `test_invoke_command.py`.

- [ ] **Step 2: Run** both files — FAIL (`expense_app` not importable; `expense-app` not declared).

- [ ] **Step 3: Implement**

`fixtures/expense-app/pyproject.toml` — copy `fixtures/notes-app/pyproject.toml`, with `name = "vibepy-expense"`, description `"The Expense App docs/roadmap.md names: actor and role, without Pages"`, entry point `expense-app = "expense_app.entry:APP"`, package `src/expense_app`.

`fixtures/expense-app/src/expense_app/entry.py`:
```python
"""The Expense App: the role gate is the framework's, the self-approval rule is the App's."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import BaseModel

from vibepy_core import (
    AppDefinition, AppEntrypoint, ErrorCategory, ErrorInfo, NoConfig, Tool, ToolContext, ToolDefinition,
)


class Expense(BaseModel):
    id: int
    submitter: str
    amount: int
    status: str


class Submission(BaseModel):
    amount: int


class Approval(BaseModel):
    id: int


class Decision(BaseModel):
    expense: Expense | None = None
    failure: ErrorInfo | None = None


class Nothing(BaseModel):
    pass


class Expenses(BaseModel):
    expenses: list[Expense]


class Ledger:
    def __init__(self) -> None:
        self._rows: dict[int, Expense] = {}

    def submit(self, submitter: str, amount: int) -> Expense:
        row = Expense(id=len(self._rows) + 1, submitter=submitter, amount=amount, status="submitted")
        self._rows[row.id] = row
        return row

    def approve(self, approver: str, expense_id: int) -> Decision:
        row = self._rows.get(expense_id)
        if row is None:
            return Decision(failure=ErrorInfo(code="expense.not_found", category=ErrorCategory.CALLER,
                                            message=f"No expense {expense_id}", details={"id": str(expense_id)}))
        if row.submitter == approver:
            return Decision(failure=ErrorInfo(code="expense.self_approval", category=ErrorCategory.CALLER,
                                            message="An expense is not approved by its submitter",
                                            details={"id": str(expense_id), "submitter": approver}))
        approved = row.model_copy(update={"status": "approved"})
        self._rows[expense_id] = approved
        return Decision(expense=approved)

    def all(self) -> list[Expense]:
        return list(self._rows.values())


@asynccontextmanager
async def expense_lifespan(_config: NoConfig) -> AsyncGenerator[Ledger]:
    yield Ledger()


async def submit_expense(ctx: ToolContext[Ledger], payload: Submission) -> Expense:
    return ctx.dependencies.submit(ctx.principal.id, payload.amount)


async def approve_expense(ctx: ToolContext[Ledger], payload: Approval) -> Decision:
    return ctx.dependencies.approve(ctx.principal.id, payload.id)


async def list_expenses(ctx: ToolContext[Ledger], _payload: Nothing) -> Expenses:
    return Expenses(expenses=ctx.dependencies.all())


EXPENSE_APP: AppDefinition[Ledger, NoConfig] = AppDefinition(
    app_id="expense-app",
    name="Expense",
    version="0.1.0",
    config=NoConfig,
    tools=[
        Tool(definition=ToolDefinition(name="submit_expense", description="Submit an expense",
                                       input_model=Submission, output_model=Expense, read_only=False),
             handler=submit_expense),
        Tool(definition=ToolDefinition(name="approve_expense", description="Approve another's expense",
                                       input_model=Approval, output_model=Decision, read_only=False,
                                       required_roles=frozenset({"manager"})),
             handler=approve_expense),
        Tool(definition=ToolDefinition(name="list_expenses", description="Every expense",
                                       input_model=Nothing, output_model=Expenses, read_only=True),
             handler=list_expenses),
    ],
    pages=[],
)

APP: AppEntrypoint[Ledger, NoConfig] = AppEntrypoint(definition=EXPENSE_APP, lifespan=expense_lifespan)
```
Format with `uv run ruff format`. `pyproject.toml`: add `"vibepy-expense"` to `[dependency-groups].dev` and `vibepy-expense = { workspace = true }` to `[tool.uv.sources]`; run `uv sync`.

- [ ] **Step 4: Run** `uv run pytest tests/test_tool_authorization.py tests/test_invoke_command.py tests/test_app_distributions.py -q` — PASS (`test_app_distributions` discovers the new App by existing; if it asserts on a fixed list of Apps, that is a defect in the test to fix, not a reason to skip the fixture).
- [ ] **Step 5: Commit** — `Expense: the App docs/roadmap.md names for actor and role, showing the framework's gate and the App's rule side by side`.

---

### Task 11: Documentation, ADR-034, docstrings, gate

**Files:**
- Modify: `docs/architecture/tool-model.md`, `runtime.md`, `page-model.md`, `adapters.md`, `packaging.md`, `authoring.md`, `errors.md` (row done in Task 3), `docs/architecture.md` (ownership line "future permission and audit hooks" → "authorization; audit hooks are M15's")
- Create: `docs/decisions/ADR-034-authorization-is-operation-level-in-toolruntime.md`
- Docstring pass over every public symbol added or changed in Tasks 1–10.

- [ ] **Step 1: `tool-model.md`.** In ToolDefinition: list `read_only`, `channels`, `required_roles` as current fields; delete those three from "Future metadata" (leave idempotency, risk classification). Rename "## Query and command" to "## Side-effect semantics": `read_only` is required; the vocabulary is RFC 9110's *safe* carried by MCP's `readOnlyHint`; `destructive`/`idempotent` qualify a Tool that is not read-only and are not declared until a milestone needs them; `read_only` refuses nothing. ToolRuntime steps become: resolve → default policy (channel, roles) → App policy → ToolContext → Tool. Add "## Authorization": operation-level vs record-level, the default policy, `ToolPolicy`, "an App policy narrows and never widens", `Principal`, `ToolForbiddenError`; record-level rules are the handler's through `ctx.principal` and travel as data (ADR-029). Cite ADR-034.
- [ ] **Step 2: `runtime.md`.** ToolContext "currently carries": add `principal`, `channel`; remove `principal`, `actor`, `channel metadata`, `permissions` from "Future fields". Remove "authorization" from potential future concerns. Add a paragraph: channel is a window property (ADR-017), principal an invocation property; hosts decide the principal; M14's hosts name one constant each.
- [ ] **Step 3: `page-model.md`.** `render(name, *, principal)`; PageContext's invoker is bound to the render's principal; `PrincipalToolInvoker` is what PageRuntime is built over and ToolRuntime satisfies; remove "future principal/identity information" bullet and say Pages do not see principals.
- [ ] **Step 4: `adapters.md`.** MCP: `list_tools` projects Tools whose `channels` contains `AGENT`, `readOnlyHint` for `read_only`; `build_mcp_server(..., principal=)`; a hidden Tool called by name is `tool.forbidden` as an `isError` result. NiceGUI: `build_web_app(..., principal=)`, `register_pages(..., principal=)`, the builder renders as that principal.
- [ ] **Step 5: `packaging.md`.** "Invoking one Tool": the new arguments, that the command stands in for a host and is told its channel and principal, and the trust model sentence. "Running a channel"/"Opening the Agent channel": `serve` invokes as `operator`, `mcp` as `agent`, both without roles.
- [ ] **Step 6: `authoring.md`.** `invoke_tool` forwards the agent's channel and principal; the capability table notes which Tools are on which channel; the sentence deferring exposure to M14 becomes the outcome.
- [ ] **Step 6b: `errors.md` and `packaging.md`.** `ErrorInfo` is a pydantic model, the one form every writer dumps and every reader validates, an App's expected failure included (ADR-029's "same fields" becomes "the same type"); `describe` writes `DescribedApp` entries. In `tool-model.md`, one sentence where ToolDefinition is described: boundary shapes are pydantic, in-process declarations are dataclasses.
- [ ] **Step 7: ADR-034**, Nygard format, `Status: Accepted`. Context: nothing refuses; Studio's operating Tools reach agents; neither channel authenticates; MCP's authorization is HTTP-only and stdio trusts its launcher; OWASP's two levels. Decision: the framework decides operation-level authorization in ToolRuntime, from the declaration (`channels`, `required_roles`), the principal and the channel, before input validation; the App's policy runs after and can only refuse; record-level rules are the handler's. Alternatives considered: authorizing after input validation (leaks schema, invites record-level checks into the framework); exposure as a policy check with no declaration (discovery would still list the Tool); an App-level list of Tools per channel (a name written twice); a chain of policies (no need yet, `runtime.md`'s rule); a principal bound to the window (undone by the first login). Consequences: hosts name principals; `kind`'s absence; `read_only` as the vocabulary and its projection; what changes when authentication arrives.
- [ ] **Step 8: Docstring pass.** Every new public class/function/module from Tasks 1–10 gets a docstring in the repository's voice (a sentence on what it is, then why it is shaped so, citing the document that owns the rule). Update `ToolRuntime.invoke`'s Raises to include `ToolForbiddenError`.
- [ ] **Step 9: Gate.** `make lint typecheck test` — PASS. Paste the summary line of each into the commit message body.
- [ ] **Step 10: Commit** — `M14 documentation: authorization is operation-level in ToolRuntime (ADR-034); the Tool model, runtime, adapters and commands say what they now do`.

---

## After the plan

Two review rounds (branch review, then cross-check against the spec), the structural audit, then `--no-ff` merge into `main`, delete `docs/milestones/M14/` on integration, and do not push until the owner says so.

## Resolved during planning

The description surface was a hand-written copy of the declaration, so M14's new fields would have been absent from what an agent sees. The owner decided (2026-09-12) to fix the cause inside M14 and first: Task 0.
