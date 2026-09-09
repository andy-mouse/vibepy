# Axis 1 review — Tool and Page core model

HEAD 05d602750328f723354823b8fb97c6bf5862ba03, branch main.

Read in full: `AGENTS.md`, `docs/architecture.md`, `docs/architecture/{tool-model,page-model,errors,runtime}.md`,
ADR-001/002/004/005/007/008/011/013/014/016/019, the 24 ADR titles, `src/vibepy/tool/*`,
`src/vibepy/page/*`, `src/vibepy/errors.py`, `src/vibepy/app/{model,composition}.py`,
`src/vibepy/{__init__,describe}.py`, `src/vibepy/adapters/mcp/{projection,server}.py`,
`src/vibepy/adapters/nicegui/web.py`, `tests/test_{tool_core,page_core,errors,package}.py`,
`tests/test_execution_semantics.py` (header + test names), `hub/src` error grep.

## Strengths

- **Channel neutrality is real in the core.** `src/vibepy/tool/model.py` and
  `src/vibepy/page/model.py` import only `dataclasses`, `typing`, `collections.abc` and
  `pydantic`. No `mcp`, no `nicegui`, no channel vocabulary anywhere in
  `tool/{model,registry,runtime}.py` or `page/{model,registry,runtime}.py`. The AGENTS.md
  invariants "MCP-specific types and behavior must not leak into the core Tool model" and
  "NiceGUI-specific types must not leak into the core Page model" hold as written.
- **ADR-016's strongest consequence holds.** `src/vibepy/page/model.py:10-22` declares
  `ToolInvoker` structurally and the Page package imports nothing from `vibepy.tool`;
  `ToolRuntime.invoke` (`tool/runtime.py:82`) matches it positionally, and
  `app/composition.py:100` hands the runtime straight in with no adapter type. No
  `_ToolRuntimeInvoker`, no second Protocol.
- **ADR-014 binding has exactly one cause and one place.** `Tool.__init__`
  (`tool/runtime.py:41-62`) is the only erasure site; `ToolRegistry` (`tool/registry.py`) is
  one dictionary and implements no invocation semantics, matching ADR-011/ADR-014 and
  tool-model.md. No `Any`, no `cast` anywhere in the axis.
- **ToolContext is the only invocation-state path.** `Tool.bound` closes over `definition`
  and `handler` only; the resource arrives solely as `ToolContext.dependencies`, created by
  `ToolRuntime.invoke` (`tool/runtime.py:84-88`) and nowhere else. `ToolContext` is frozen,
  no channel constructs one, and `test_page_core.py:47` even pins `PageContext` to a single
  field. ADR-013 and the runtime.md contract are satisfied.
- **No serialization in the framework's own path.** `ToolRuntime` holds no lock,
  `PageRuntime.render` holds no per-Page state, and `tests/test_execution_semantics.py`
  proves overlap with a real `asyncio.Barrier` reached through `ctx.dependencies` at all four
  layers — the runtime.md constitutional test is honest, not a duration heuristic.
- **The error catalogue enforces itself.** `tests/test_errors.py:32-126` walks
  `VibepyError.__subclasses__()` recursively so a new exception without a code, a category
  row or a case fails the suite — exactly the enforcement ADR-019 promised.
- **ADR-007 is implemented where the ADR says it must be.** The result is revalidated from
  its dump (`tool/runtime.py:54-59`) rather than trusted, and `test_tool_core.py:177-189,
  234-242` pins the `model_construct` bypass.

## Findings

### Critical

None. I looked specifically for a channel type in the core model, a business decision inside
ToolRuntime, a second validation path, and a Page reaching state outside Tools; none exists.

### Important

**1. `src/vibepy/errors.py:213-219` — `to_error_info` cannot in fact describe "any exception".**

`docs/architecture/errors.md` states plainly: "`to_error_info(error)` builds one from any
exception." The implementation branches on `isinstance(error, VibepyError)` and then reads
`error.code` and `_CATEGORIES[error.code]`. `VibepyError.code` is a `ClassVar[str]` with no
value (`errors.py:36`), and `VibepyError` is exported from the package root
(`src/vibepy/__init__.py:30`, `__all__:78`). So:

- `to_error_info(VibepyError("boom"))` raises `AttributeError`;
- `to_error_info(SomeAppError("boom"))`, where an App subclasses the public base — which the
  public API invites — raises `KeyError` on `_CATEGORIES`.

This matters because of where `to_error_info` is called. `adapters/mcp/server.py:112-115`
catches `Exception` with the comment "Broad on purpose: a app defect must not surface as a
protocol error", then calls `_failure` → `_payload` → `to_error_info`. A `KeyError` raised
inside that `except` block escapes `call_tool` and becomes precisely the protocol error the
comment promises to prevent. `describe.py:23-25` and `serve.py:100` have the same shape.

The in-repo test cannot catch this: `test_every_framework_error_is_covered_here` only walks
subclasses defined in `vibepy.errors`.

Fix: make the unmapped case fall through to the `UNHANDLED_CODE` branch, e.g. resolve the
code with `getattr(error, "code", None)` and the category with `_CATEGORIES.get(code)`,
treating a miss as `app.unhandled`/`EXECUTION`. The existing catalogue test still guarantees
that no *framework* error takes that path.

**2. No executable guard on the repository's two headline invariants.**

`AGENTS.md` lists "MCP-specific types and behavior must not leak into the core Tool model"
and "NiceGUI-specific types must not leak into the core Page model" among the core
invariants, and ADR-016 records "the Page package imports nothing from the Tool package"
as a decision consequence. All three are true today by reading, and none is tested. By
contrast, much narrower rules do have tests: the exported-name list (`test_package.py:4`),
the error catalogue (`test_errors.py:107`), `PageContext`'s field list
(`test_page_core.py:47`).

`AGENTS.md` says "Tests verify public contracts, not internals" — an import boundary between
two published packages is a public contract, and it is the one a future milestone is most
likely to break silently (importing `mcp.types` for a schema shortcut inside `tool/model.py`
would pass lint, typecheck and every current test).

Fix: one test that imports `vibepy.tool` and `vibepy.page` in a subprocess and asserts no
`mcp*`/`nicegui*` module in `sys.modules`, plus a module-level assertion that no
`vibepy.page.*` module imports `vibepy.tool` (`ast` walk or `sys.modules` after a fresh
import). `tests/test_app_isolation.py:23-24` already uses the `sys.modules` technique.

**3. `adapters/mcp/projection.py:19` with `adapters/mcp/server.py:116` — the published
output schema and the returned value can diverge, which ADR-007 says they cannot.**

ADR-007's Context is explicit that "the Agent channel publishes a schema derived from that
model, so the value a channel receives must match what was published", and its first
consequence is "the published schema and the returned value cannot diverge silently".

`projection.py:19` publishes `output_model.model_json_schema()` — Pydantic's *validation*
schema (`mode='validation'` is the default). `server.py:116` sends
`result.model_dump(by_alias=True, mode="json")` — a *serialization* dump. For any output
model with a `computed_field` the two disagree. Verified in this repo's venv:

```
val schema props ['a']
ser schema props ['a', 'b']
dump {'a': 1, 'b': 2}
```

`errors.md` notes the MCP specification requires structured results to conform to the
declared output schema; here `structured_content` carries a member the published schema does
not describe. It survives only because JSON Schema allows unspecified properties by default.
The symmetric case (`Field(exclude=True)`) is caught, because the round trip in
`tool/runtime.py:54-59` fails validation — that is ADR-007 working as designed, which makes
the computed-field hole the one gap left.

The file is Axis 2's, but the guarantee is ADR-007's and therefore mine to report.
Fix: `model_json_schema(mode="serialization")` for `output_schema` (keep the default for
`input_schema`), plus a test with a computed-field output model.

### Minor

**4. `src/vibepy/tool/runtime.py:61-62` — `Tool` is a mutable object with a public bound
callable, unlike every neighbouring declaration.**

`ToolDefinition`, `ToolContext`, `PageDefinition`, `Page` and `ErrorInfo` are all frozen
dataclasses; `Tool` is a plain class assigning two public instance attributes, so
`tool.bound = something_else` or `tool.definition = ...` after registration is legal and
would desynchronise the registry key from the declaration name. ADR-014's consequence "a
Tool no longer exposes its handler" is honoured only in the letter: `bound` is the handler
plus validation, reachable by anyone holding a `Tool`, which means nothing structurally
enforces the AGENTS.md invariant "Channel adapters invoke Tools through ToolRuntime".

Fix: name it `_bound` and give `Tool` a `__call__`, or set both attributes through
`object.__setattr__` on a frozen shell. Either keeps `ToolRuntime` as the only caller by
construction rather than by convention.

**5. `src/vibepy/tool/runtime.py:54` — `warnings=False` plus lax revalidation silently
repairs an invalid handler result.**

Verified: `Todo.model_construct(id='7')` dumps to `{'id': '7', ...}` and revalidates to
`id=7`. The value the channel returns is not the value the handler produced, the app's bug
leaves no trace, and `warnings=False` suppresses the Pydantic serializer warning that would
otherwise have been the only signal. ADR-007's consequence "an app cannot use
model_construct to bypass its own output contract" is true of the *shape* but not of the
*value*. `test_tool_core.py:179` only exercises `"not-an-integer"`, a violation that cannot
coerce, so the coercible case is untested.

This may be a deliberate trade-off; it is not one ADR-007 records. Fix: either
`logger.warning` when `dumped != result.__dict__`-equivalent, or state the coercion
behaviour in ADR-007/tool-model.md, and add a test pinning whichever is chosen.

**6. `src/vibepy/tool/runtime.py:54` — a handler returning a non-model is `app.unhandled`,
not `tool.output_invalid`.**

`result.model_dump(...)` assumes the handler honoured its static return type. A handler
returning a `dict` (nothing at runtime prevents it; `ToolHandler` is a Protocol) raises
`AttributeError`, which `to_error_info` classifies as `app.unhandled`/`EXECUTION`. The
failure is genuinely "output did not satisfy the Tool's output model" and has a code for
that (`errors.md`, `tool.output_invalid`). Fix: guard with
`isinstance(result, definition.output_model)` — that also closes the case of a *different*
BaseModel whose dump happens to validate — and raise `ToolOutputValidationError`.

**7. `src/vibepy/tool/registry.py:23-24, 32-38` — "registration order" is ambiguous on
re-registration and untested.**

ADR-011 and tool-model.md both promise enumeration "in registration order". A dict
assignment to an existing key keeps the *original* insertion position, so re-registering
`create_todo` last leaves it first in `definitions()`. `PageRegistry` has the same
behaviour. `test_tool_core.py:290` registers a single name twice and so never observes
ordering; `test_page_core.py:93` likewise. Fix: state in tool-model.md/page-model.md that a
replacement keeps the earlier position, and pin it with a three-Tool test.

**8. `src/vibepy/errors.py` — the retired-code rule and the errors.md table are not
enforced.**

`errors.md` states "a retired code is never reused" and names `lifecycle.transition_forbidden`
and `lifecycle.not_running`. Nothing in code or tests records those two strings, so the rule
lives only in prose that a future milestone need not read — while ADR-019 leaned on the
walking test for the rest of the model. Similarly, no test compares `_CATEGORIES` against the
table in `errors.md`, so the two can drift. Fix: a `RETIRED_CODES: frozenset[str]` constant in
`errors.py` and one assertion in `test_errors.py` that no framework code is in it.

## Cross-boundary assumptions

Every place my conclusion depended on another module upholding a guarantee, and whether I
verified it:

| Assumption | Verified? | File checked |
| --- | --- | --- |
| `ToolRuntime` structurally satisfies `ToolInvoker`, so no adapter type stands between Page and runtime | yes | `page/model.py:22` vs `tool/runtime.py:82`; `app/composition.py:100` |
| The NiceGUI adapter injects no NiceGUI type into `PageContext` | yes — it closes over a `PageRuntime` and calls `render(name)` only | `adapters/nicegui/web.py:48-58` |
| Route format/uniqueness is validated where routes are registered, as page-model.md claims, not in the core Page model | yes — validated before any route is registered | `adapters/nicegui/web.py:34-45` |
| The MCP adapter reaches Tools only through `ToolRuntime.invoke` and never through `Tool.bound` | yes | `adapters/mcp/server.py:104`; repo-wide grep for `.bound` returns only `tool/runtime.py:62,89` |
| The MCP adapter reads the normalized form rather than classifying exceptions itself | partly — it reads `to_error_info`, but still branches per exception type to choose the protocol path (that choice is protocol policy, which errors.md assigns to the channel, so not a finding) | `adapters/mcp/server.py:104-120` |
| The published output schema matches the value sent | **no — this is Finding 3** | `adapters/mcp/projection.py:19`, `adapters/mcp/server.py:116` |
| The framework validates the same representation the channel publishes | no — the framework validates a python-mode round trip (`tool/runtime.py:54`) and the adapter then re-dumps `mode="json"` (`server.py:116`); a type whose json dump differs from its python dump is validated in one form and published in another. Marginal today; noted rather than raised, since ADR-007 specifies "one dump and validate round trip" without naming the mode | `tool/runtime.py:54`, `adapters/mcp/server.py:116` |
| The broad `except Exception` in the MCP call path really cannot raise | **no — Finding 1 shows `_payload` itself can raise** | `adapters/mcp/server.py:112-115`, `errors.py:213` |
| No Hub or sample code subclasses `VibepyError` unmapped (which would make Finding 1 live rather than latent) | yes — grep for `class .*Error` across `hub/src`, `samples`, `src` finds subclasses only in `errors.py` | `hub/src/**`, `samples/**` |
| `import vibepy` does not pull `mcp`/`nicegui` into a host process | yes — the root `__init__` imports `app`, `errors`, `page`, `tool` only; adapters are not re-exported | `src/vibepy/__init__.py:1-42` |
| `AppDefinition` holds Tools as declarations with no resource, so the registry stores declarations per ADR-011 | yes | `app/model.py:41-42`, `app/composition.py:36-43` |
| `errors.md` says the category enum's branches end in `assert_never`; something branches on it | no branch exists yet anywhere in the repo (grep for `assert_never` returns nothing). Not a violation — the rule is conditional — but the sentence describes a shape no code currently has | repo-wide grep |

## Rule concerns

None. Every finding above is measured against `AGENTS.md`, an ADR, or a
`docs/architecture*` sentence, and I did not substitute an outside standard. One observation
worth the owner's attention rather than a rule objection: neither `ToolRegistry` nor
`ToolDefinition` validates a Tool name (empty string, whitespace, MCP naming rules), and
tool-model.md does not require it. The Page model deliberately pushes route validation to the
channel that consumes routes; a Tool name has no equivalent consumer-owned check, since
`projection.py` passes it straight through. Whether the framework should validate names is an
open decision, so I am not raising it as a defect.

## Assessment

The axis is in good shape and the documents are unusually load-bearing — the ADRs describe
what the code actually does, including the parts that are subtle (the variance argument in
ADR-014, the `ToolInvoker` naming in ADR-016), and the constitutional tests are honest
proofs rather than smoke tests. Channel neutrality, single invocation path, ToolContext as
the only invocation-state carrier, and declarations-in-the-registry all hold.

The weaknesses are at the edges of the model rather than in it: the error normalizer breaks
on the extension point the framework itself publishes (Finding 1); the schema the Agent
channel publishes is not quite the one the framework validates (Finding 3); and the two
invariants AGENTS.md puts first are the two with no test behind them (Finding 2). None
blocks the current state of the framework; all three are the kind of gap a later milestone
turns into a real defect.
