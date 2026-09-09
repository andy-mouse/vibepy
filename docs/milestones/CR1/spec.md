# CR1 - Framework core defects

CR1 is not a `docs/roadmap.md` milestone. Its scope and its place in the sequence come from
`docs/milestones/code-review-roadmap.md`, and the findings it acts on are C1, I1, I5, I6, I14,
I15, I20 and D1 in `docs/milestones/code-review/findings.md`.

Seven defects in the framework and the Hub, plus the guards that would have caught them. Each
one is a failure to apply a decision this repository has already recorded, so CR1 takes no new
decision: it applies ADR-007, ADR-012, ADR-019 and `docs/architecture/errors.md` where the code
departed from them.

## Acceptance criteria

- an App name reaching `remove_app` cannot address a directory outside the Hub's environments
  root; an absolute name is refused (`hub/.../installation.py:159`, `internals/installer.py:39`)
- `to_error_info` describes an exception raised by an App subclassing the public `VibepyError`,
  rather than raising `AttributeError` or `KeyError` (`errors.py:213`)
- every framework exception derives from the single base, `AppNotDeclared` included, and the
  catalogue test sees it (`serve.py:33`)
- two Pages declaring one name fail at registration rather than serving one handler on two
  routes (`adapters/nicegui/web.py:34`)
- the schema the Agent channel publishes is the one the payload is serialized against
  (`adapters/mcp/projection.py:19`)
- `PageRegistry.definitions()` and the Agent channel's second `ToolRegistry` are gone, or used
- an import of an MCP or NiceGUI type anywhere in the core packages, `vibepy/__init__.py`
  included, fails a test

## Sources

| Contract | Source |
| --- | --- |
| a milestone that adds an exception declares a code and maps a category, and a test that walks every subclass enforces both | `docs/decisions/ADR-019` |
| `app.unhandled` belongs to no exception class; an exception raised by an App's own code is described, not classified | `docs/architecture/errors.md` |
| `caller` means the call itself was wrong and a different call may succeed | `docs/architecture/errors.md` |
| the self-description command's failure writes the framework's code and message to standard error and exits 1. `packaging.md` states this of `describe` only; `serve` reports the same way, which is the shape CR1 gives it | `docs/architecture/packaging.md` |
| the published output schema and the returned value cannot diverge silently | `docs/decisions/ADR-007` |
| structured results must conform to the declared output schema | MCP specification, *Server / Tools* (<https://modelcontextprotocol.io/specification/2025-06-18/server/tools>) |
| a validation schema and a serialization schema are separate JSON Schemas of one model | Pydantic, *JSON Schema* (<https://docs.pydantic.dev/latest/concepts/json_schema/>) |
| `register_pages` takes an `AppDefinition` and enumerates `definition.pages`, never a `PageRegistry` | `docs/decisions/ADR-012`, amendment; `docs/architecture/adapters.md` |
| two Pages declaring one route fail loudly at registration rather than one disappearing silently | `docs/decisions/ADR-012` |
| `route` and `title` are validated where routes are registered; `name` is the identifier the framework addresses a Page by | `docs/architecture/page-model.md` |
| `ToolRegistry.definitions()` enumerates declarations in registration order, which is what a channel needs for discovery, and a channel does not receive them through a second path beside the registry | `docs/architecture/tool-model.md`, `adapters.md`. The reasoning is `ADR-011`'s, which `ADR-014` kept unchanged; both records are retired, so the architecture documents are what state it |
| registering a name twice replaces the earlier registration | `docs/architecture/tool-model.md`, `page-model.md` |
| validation is the framework's to own | `docs/architecture.md`, Framework ownership |
| every Hub Tool is exposed on the Agent channel, so a Tool input is a model-controlled string | `docs/decisions/ADR-024` |
| a Tool's expected, actionable failure is a `Diagnostic` field rather than an exception | `docs/decisions/ADR-007`, `vibepy_hub/models.py` |
| blocking calls inside async code are wrapped, `Any` and `cast` are not acceptable in the public API, exception types are the contract | `AGENTS.md` |

## Problem

Six of the seven are one shape: a rule this repository states, and a place the code does not
follow it.

**C1.** `AppName.app_name` is an unconstrained `str`, `environment()` is a bare
`root / "envs" / name` join, and `remove_app` calls `shutil.rmtree` on the result. ADR-024
exposes every Hub Tool on the Agent channel, so a model-controlled string reaches a recursive
delete: `../../victim` escapes the root and an absolute name discards it entirely. Verified in
`findings.md` by resolving paths only.

**I15.** `to_error_info` promises to describe any exception and cannot describe two: a bare
`VibepyError`, whose `code` is an unassigned `ClassVar`, and an App's own subclass of it, whose
code no category table names. Both are reachable, because `VibepyError` is exported. The MCP
adapter calls it inside an `except Exception` that exists so an App defect cannot become a
protocol error, and the `KeyError` escaping that clause is precisely that protocol error.

**I1.** `AppNotDeclared` derives from `Exception`, so it has no code, no category and no row in
`errors.md`. `test_errors.py` walks `VibepyError.__subclasses__()`, so the catalogue test that
enforces ADR-019 cannot see it — the one exception outside the rule is the one exception the
guard is blind to. The same function writes a code-and-message JSON object for every other
failure and prose for this one.

**I6.** The Web adapter validates route format and route uniqueness before registering
anything, and does not validate name uniqueness. The registry it renders through is keyed by
name and replaces on re-registration. Two Pages with one name and two routes therefore register
both routes and render the second handler from each, with no diagnostic. ADR-012 exists because
a silent replacement is unacceptable; the same disappearance is reachable through the name.

**D1.** The adapter publishes `model_json_schema()`, Pydantic's validation schema, and sends
`model_dump(mode="json")`, a serialization dump. A `computed_field` makes the payload carry a
member the published schema does not describe, which ADR-007 says cannot happen. No output
model in the repository has one today, so the finding is latent and the fix is one argument.

**I5.** `PageRegistry.definitions()` has no caller. Its own docstring and
`page-model.md` both say a Web channel adapter projects those declarations into routes, and
ADR-012's amendment records that the adapter has always enumerated the declaration instead.

**I14.** The two headline invariants — no MCP type in the core Tool model, no Web type in the
core Page model — are true by reading and untested. The AST guards that exist scan `tool/`,
`page/` and `app/`, skipping `__init__.py`, `errors.py` and `describe.py`, and the package root
is where an SDK import would reach every consumer.

## Decisions recorded separately

None. Every change applies a record that already exists:

- the new exception and the new code apply ADR-019's rule that an added exception declares a
  code and maps a category. Adding one under the rule is not a decision between alternatives.
- the Page name conflict applies ADR-012's stated consequence to the field `page-model.md`
  assigns to the framework rather than to the adapter.
- the serialization schema applies ADR-007's first consequence.
- the Hub's name constraint is a defect fix inside one module. What an App is addressed by is
  CR2's, and a record belongs there if anywhere.

Two readings are settled here rather than in a record, because each follows from a document
rather than from a choice:

- **The two channels enumerate declarations from different sources, and both are documented.**
  The Agent channel enumerates a `ToolRegistry` built from the declaration (ADR-011's
  consequence, kept unchanged by ADR-014, held by `tool-model.md` and `adapters.md`); the Web
  channel enumerates the declaration itself (ADR-012's amendment, `adapters.md`). CR1 does not
  unify them. `PageRegistry.definitions()` is therefore deleted and `ToolRegistry.definitions()`
  is kept, and the acceptance criterion's two branches are answered one each.
- **Name replacement stays the registries' contract, and only Pages need a conflict refused.**
  A duplicate Tool name is invisible to an agent because discovery and dispatch read the same
  registry: one Tool is published and that same one is called. A duplicate Page name is not,
  because registration reads the declaration and rendering reads the registry. The defect is the
  asymmetry, not the replacement, so the replacement rule is left as three documents state it.

## Scope

1. The Hub constrains the App name on every Tool input that carries one, and `environment()`
   refuses a name that does not resolve under the environments root.
2. `to_error_info` classifies only a code the framework maps, and describes everything else.
3. `AppNotDeclared` becomes a framework exception in `errors.py`, with a code and a category,
   and `serve` reports it the way it reports every other failure.
4. A duplicate Page name is refused where declarations become a registry.
5. A declaration answers with its own JSON Schemas, and both publishing surfaces ask it,
   so the output schema a channel publishes is the one its payload is serialized against.
6. `PageRegistry.definitions()` is deleted.
7. One guard covers both channel SDKs across every core module, statically and at import time.

## Public API

Three additions and one deletion. Nothing is renamed and no signature changes.

| Change | Kind |
| --- | --- |
| `AppNotDeclaredError` in `vibepy_core.errors`, exported from the package root | added |
| code `package.app_not_declared`, category `caller` | added |
| `PageNameConflictError`, code `page.name_conflict`, category `declaration` | added |
| `ToolDefinition.input_schema()` and `output_schema()` | added |
| `PageRegistry.definitions()` | deleted |

`AppNotDeclared` moves out of `serve.py` and gains the `Error` suffix every other framework
exception carries. It was never exported and never caught outside the module that raised it, so
the move is an addition to the public surface rather than a compatibility event.

Its category is `caller`. `errors.md` defines `caller` as the call itself being wrong where a
different call may succeed, which is what naming an App this environment does not declare is;
`declaration` describes an App declaring something the framework rejects, and here nothing was
declared. Its code sits in the `package.` namespace beside `package.entrypoint_unloadable` and
`package.entrypoint_invalid`, which the same function raises at the same point.

`PageNameConflictError` carries the name and both routes, so `details()` says which declarations
collided. It is `declaration`, as `page.route_conflict` is.

## Where each check lives

`page-model.md` places a check by the model that owns the field: `route` and `title` are
consumed by the Web channel adapter, so route format and route uniqueness are validated where
routes are registered and not in the core Page model. `name` is the identifier the framework
addresses a Page by, so a name conflict is the core's to refuse, and it is refused in
`page_registry_for` — where a declaration becomes a registry, before the window opens and
therefore before any route exists. Route validation stays in the adapter, untouched.

The registries are unchanged. `PageRegistry.register` still replaces, as `page-model.md` states;
composition does not hand it a duplicate.

The Hub is gated twice, and both gates are reachable:

- the constrained field on `AppName`, `ConfigureRequest` and `StartRequest` refuses a name that
  is not a single path segment. Refusal is Pydantic's, so the Agent channel already answers it
  as `tool.input_invalid` and the Hub grows no diagnostic for it.
- `environment()` refuses a name whose joined path does not resolve to a direct child of
  `root / "envs"`. This is the guarantee: the three input models are not the only callers, and
  the sink is where a later caller cannot forget it.

Output models keep an unconstrained `app_name`. An output model is revalidated, so constraining
one would turn an environment directory the Hub did not create into a Tool failure rather than a
row.

## Errors

Two rows join `errors.md`'s table:

| Code | Category | Exception |
| --- | --- | --- |
| `page.name_conflict` | declaration | `PageNameConflictError` |
| `package.app_not_declared` | caller | `AppNotDeclaredError` |

`to_error_info` resolves a code with `getattr` and a category with a mapping lookup that may
miss, and a miss falls through to `app.unhandled` / `execution`. This is what `errors.md`
already says: an exception raised by an App's own code is described, not classified. The
catalogue test continues to guarantee that no framework exception takes that path, because it
walks every subclass of the base and asserts each one's code is mapped.

The Hub's `environment()` raises a Hub exception of its own. The Hub's failure vocabulary is
I9's, and CR2 unifies it; CR1 adds one type and no new `Diagnostic` code.

## Testing

The suite is 153 tests. One goes with the method it covers:
`test_definitions_enumerates_every_registered_page` is deleted, and
`test_registering_a_name_twice_replaces_the_earlier_page` keeps its `resolve` assertion and loses
its `definitions()` one, because `page-model.md`'s replacement contract is unchanged. Every other
existing test passes untouched. What CR1 adds:

- **C1** — `remove_app` with `../../victim` and with an absolute name leaves the target
  directory in place and reports `tool.input_invalid`; `environment()` refuses both directly.
  The test creates a real directory outside the root and asserts it survives.
- **I15** — `to_error_info(VibepyError("x"))` and `to_error_info(<App subclass with its own
  code>)` both describe rather than raise, and both report `app.unhandled` / `execution`. One
  test drives it through the MCP adapter, because the escaping `KeyError` is what made the
  finding critical: a Tool raising an App-defined subclass answers with a result, not a protocol
  error.
- **I1** — the catalogue test sees `AppNotDeclaredError` without being edited to name it, and
  `serve` writes a code-and-message JSON object for an App the environment does not declare.
- **I6** — an App declaring two Pages with one name and two routes fails
  `page_runtime_for` with `PageNameConflictError`, and no route is registered. The existing
  route-conflict test is unaffected.
- **D1** — an output model with a `computed_field`: every property the payload carries appears
  in the published output schema. `input_schema` keeps the validation schema, and a test pins
  that too, because the payload the input schema describes is the one being validated.
- **I20** — a Page handler raising a framework error, and one raising an App's own exception,
  both reached through a registered route. The assertion is that the exception arrives unchanged
  and no normalized payload is produced: the Web channel translates nothing.
- **I14** — one guard replaces the two duplicated AST scans. It reads every module under
  `src/vibepy_core` that is not a channel component — `adapters/` and `serve.py`, which
  `packaging.md` documents as the command that opens the Web channel — and it also imports
  `vibepy_core` in a subprocess and asserts neither `mcp` nor `nicegui` is in `sys.modules`,
  which catches a leak reached through an import rather than written in the file.
  `test_app_isolation.py` already uses the subprocess technique.

## Compatibility

One public name is removed and one behaviour changes.

`PageRegistry.definitions()` is exported from the package root, and AGENTS.md keeps the public
API backward compatible and deprecates before removing. That rule protects a consumer of a
working contract, and this method has neither. ADR-012's amendment records that `register_pages`
has always enumerated the declaration and never took a `PageRegistry`, so the method's own
docstring — that a Web channel adapter projects these into routes — was never true. Deprecating
a false statement for a release cycle preserves nothing, and the acceptance criterion offers
`gone` as one of its two branches.

The behaviour change can break an App: one declaring two Pages under one name used to serve and
now fails to open its window. That App was serving one Page from two routes, so the failure
replaces a defect rather than a working configuration.

The MCP output schema changes shape for any output model whose serialization schema differs from
its validation schema. No such model exists in this repository, and a client reading the schema
receives a more accurate one.

`AppNotDeclared`'s stderr goes from prose to JSON. The Hub does not capture the child's stderr,
so nothing reads either form today.

## Documentation

Only what CR1 makes false:

- `errors.md` — two rows in the code table.
- `page-model.md` — the paragraph stating that the registry enumerates its declarations because
  a Web channel adapter projects them is deleted, which is what ADR-012's amendment already
  recorded; a sentence says where a name conflict is refused.
- `tool-model.md`, `adapters.md` — unchanged. Both describe the Agent channel's enumeration as
  it stays.

No `Accepted` record changes. ADR-012's decision is unaffected: CR1 adds the check its
consequence describes to a second field.

The Hub has no architecture document to update, which is I13 and CR3's.

## Out of scope

- every CR2 finding, including the four App-name spaces, blocking I/O on the event loop, the
  orphaned child process, `config.invalid` at the Hub boundary and the Hub's second error
  vocabulary
- `serve.py`'s hand-written `serve.config_invalid` string, a published code with no exception
  class. The review did not promote it and it is the same path as I8, which CR2 owns
- unifying the two channels' enumeration sources, which would reverse ADR-011 and ADR-014 and
  answers no defect
- Tool name conflicts, and Q2's question of whether a Tool name is validated at all — CR3
- `list_tools` ignoring the pagination cursor, and the reviewer suggestions the coordinator did
  not promote to `findings.md`
- ADR-016's untested consequence that the Page package imports nothing from the Tool package.
  CR1's guard covers the two channel SDKs, which is what the criterion names
