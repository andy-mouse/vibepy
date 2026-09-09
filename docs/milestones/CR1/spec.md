# CR1 - Framework core defects

CR1 is not a `docs/roadmap.md` milestone. Its scope and its place in the sequence come from
`docs/milestones/code-review-roadmap.md`, and the findings it acts on are C1, I1, I5, I6, I14,
I15, I20 and D1 in `docs/milestones/code-review/findings.md`.

Seven defects in the framework and the Hub, plus the guards that would have caught them. Six are
a failure to apply a decision this repository has already recorded — ADR-007, ADR-012, ADR-019
and `docs/architecture/errors.md` — and CR1 applies each where the code departed from it. The
seventh could not be fixed at its cause without reversing a consequence still stated as current
truth, so CR1 takes one new decision, ADR-027.

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
| the contract CR1 entered against: a channel adapter projected declarations for discovery through a `ToolRegistry` rather than through a second path beside it. `ADR-027` reverses it, and no document states it now | `docs/decisions/ADR-011`, the record whose consequence it was; `ADR-027` for why it no longer holds |
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

## Decisions

One is recorded, in ADR-027. Every other change applies a record that already exists:

- the new exception and the new code apply ADR-019's rule that an added exception declares a
  code and maps a category. Adding one under the rule is not a decision between alternatives.
- the Page name conflict applies ADR-012's stated consequence to the field `page-model.md`
  assigns to the framework rather than to the adapter.
- the serialization schema applies ADR-007's first consequence.
- the Hub's name constraint is a defect fix inside one module. What an App is addressed by is
  CR2's, and a record belongs there if anywhere.

ADR-027 is written, because the sixth criterion cannot be met without taking a decision. The
criterion is that `PageRegistry.definitions()` and the Agent channel's second `ToolRegistry` are
gone or used, and the second `ToolRegistry` exists for one reason: the adapter builds a lookup
table to enumerate a list it already holds. Removing that reason reverses a consequence
`tool-model.md` still states, which is a record's work rather than a spec's. Two readings the
record rests on:

- **ADR-011's consequence outlived its premise.** ADR-011 had the adapter enumerate a registry
  because the registry "stores the bound callable alone and discards each declaration", so
  discovery "has nothing to enumerate". ADR-014 moved binding into `Tool`, so an `AppDefinition`
  holds Tools that carry their own declarations — and kept `definitions()` "unchanged" without
  asking whether an adapter still needed it. Of three enumerating surfaces only one went through
  a registry: the Web adapter reads the declaration (ADR-012's amendment) and so does
  `AppEntrypoint.describe`.
- **Refusing a duplicate name becomes required for Tools, not only for Pages.** While discovery
  read the registry a duplicate Tool name could not be seen: one Tool was published and that same
  one was called. Enumerating the declaration removes that, so the refusal `page_registry_for`
  performs is now owed by `tool_registry_for` too. The registries keep replacement as their own
  contract, and no framework path reaches it.

## Scope

1. The Hub constrains the App name on every Tool input that carries one, and `environment()`
   refuses a name that does not resolve under the environments root.
2. `to_error_info` classifies only a code the framework maps, and describes everything else.
3. `AppNotDeclared` becomes a framework exception in `errors.py`, with a code and a category,
   and `serve` reports it the way it reports every other failure.
4. A duplicate Page name is refused where declarations become a registry.
5. A declaration answers with its own JSON Schemas, and both publishing surfaces ask it,
   so the output schema a channel publishes is the one its payload is serialized against.
6. Both channels enumerate the declaration, both registries answer a name and nothing
   else, and both refuse a name declared twice. `PageRegistry.definitions()` and
   `ToolRegistry.definitions()` are deleted, and a running App holds one `ToolRegistry`.
7. One guard covers both channel SDKs across every core module, statically and at import time.

## Public API

Five additions and two deletions. Nothing is renamed and no signature changes.

| Change | Kind |
| --- | --- |
| `AppNotDeclaredError` in `vibepy_core.errors`, exported from the package root | added |
| code `package.app_not_declared`, category `caller` | added |
| `PageNameConflictError`, code `page.name_conflict`, category `declaration` | added |
| `ToolDefinition.input_schema()` and `output_schema()` | added |
| `ToolNameConflictError`, code `tool.name_conflict`, category `declaration` | added |
| `PageRegistry.definitions()` | deleted |
| `ToolRegistry.definitions()` | deleted |

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

`make test` collects 153 tests where CR1 begins and 189 where it ends. Two go with the method
each covers: `test_definitions_enumerates_every_registered_page` and
`test_registry_enumerates_the_declarations_it_registered`. The two that assert a registry replaces
on re-registration keep their `resolve` assertion and lose their `definitions()` one, because that
replacement is still each registry's own contract. Every other existing test passes untouched.
What CR1 adds:

- **C1** — `remove_app` with `../../victim` and with an absolute name leaves the target
  directory in place and reports `tool.input_invalid`. The test creates a real directory outside
  the root, and an environments directory inside it, because without one the operating system
  cannot traverse `..` through it and the deletion fails for the wrong reason.

  `environment()` is also tested directly, and it is a Hub internal. AGENTS.md has tests verify
  public contracts rather than internals; this is the one place CR1 departs from that, because
  the acceptance criterion names the file and because the reason for a second gate is that a
  Tool input is not the only caller — reaching it only through a Tool would leave the sink
  unverified. Each gate is tested for what it alone guarantees: `environment()` for what this
  platform reads as leaving the root, the input field for a character set that is a separator on
  either platform.
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
- **I14** — the static half moves to the linter and the two duplicated AST scans are deleted.
  `TID251` bans `mcp` and `nicegui` across `src/vibepy_core`, with `adapters/` and `serve.py`
  exempt because being a channel component is their job — `packaging.md` documents `serve` as
  the command that opens the Web channel. A rule a tool enforces is not re-implemented as a
  test, and the linter reaches modules a test cannot: `describe.py` is covered though nothing
  imports it.

  One test remains, for what a static rule cannot see — an SDK reached through another import
  rather than named in the file. It imports `vibepy_core` in a subprocess and asserts neither
  SDK is in `sys.modules`; `test_app_isolation.py` uses the same technique.

  This reads the seventh criterion's "fails a test" as the repository's own gate, which
  `AGENTS.md` states as `make lint typecheck test`: a leak anywhere in the core fails it. A leak
  in a module the package root reaches fails the test as well. The reading is stated here
  because it is a reading, and the criterion is the owner's.

## Compatibility

Two public names are removed and two behaviours change.

`PageRegistry.definitions()` is exported from the package root, and AGENTS.md keeps the public
API backward compatible and deprecates before removing. That rule protects a consumer of a
working contract, and this method has neither. ADR-012's amendment records that `register_pages`
has always enumerated the declaration and never took a `PageRegistry`, so the method's own
docstring — that a Web channel adapter projects these into routes — was never true. Deprecating
a false statement for a release cycle preserves nothing, and the acceptance criterion offers
`gone` as one of its two branches.

`ToolRegistry.definitions()` is the second removal, and the argument above does not cover it: it
had a caller, and `tool-model.md` described it accurately. ADR-027 carries why a deprecation
cycle was available and not taken.

Both behaviour changes can break an App, and each replaces a defect rather than a working
configuration. An App declaring two Pages under one name used to serve, and was serving one Page
from two routes; one declaring two Tools under one name used to serve, and was publishing a Tool
that resolved to another. Both now fail to open a window.

The MCP output schema changes shape for any output model whose serialization schema differs from
its validation schema. No such model exists in this repository, and a client reading the schema
receives a more accurate one.

`AppNotDeclared`'s stderr goes from prose to JSON. The Hub does not capture the child's stderr,
so nothing reads either form today.

## Documentation

Only what CR1 makes false:

- `errors.md` — three rows in the code table.
- `tool-model.md` — what a channel asks of a registry, and that a duplicate name is refused
  before one is filled. `adapters.md` — that the Agent channel's adapter builds no registry.
- `page-model.md` — the paragraph stating that the registry enumerates its declarations because
  a Web channel adapter projects them is deleted, which is what ADR-012's amendment already
  recorded; a sentence says where a name conflict is refused.

No existing record changes. ADR-012's decision is unaffected: CR1 adds the check its consequence
describes to a second field. ADR-027 is new, and supersedes nothing — the consequence it reverses
belongs to a record ADR-014 already superseded, and current truth is `tool-model.md`.

The Hub has no architecture document to update, which is I13 and CR3's.

## Out of scope

- every CR2 finding, including the four App-name spaces, blocking I/O on the event loop, the
  orphaned child process, `config.invalid` at the Hub boundary and the Hub's second error
  vocabulary
- `serve.py`'s hand-written `serve.config_invalid` string, a published code with no exception
  class. The review did not promote it and it is the same path as I8, which CR2 owns
- Q2's question of whether a Tool name's string is validated at all — CR3. ADR-027 makes a
  duplicate name a failure; whether a name is well formed is a separate question
- `list_tools` ignoring the pagination cursor, and the reviewer suggestions the coordinator did
  not promote to `findings.md`
- ADR-016's untested consequence that the Page package imports nothing from the Tool package.
  CR1's guard covers the two channel SDKs, which is what the criterion names
