# Axis 6 — Documentation coherence (HEAD 05d6027)

Scope read: `AGENTS.md`, `CLAUDE.md`, `docs/architecture.md`, all nine `docs/architecture/*.md`,
ADR-001..024, `docs/roadmap.md`, `docs/hub-ui-mockup.html` (structure only), plus the
implementation they describe: all of `src/vibepy/`, all of `hub/src/vibepy_hub/`,
`samples/todo`, `samples/notes`, `pyproject.toml`, `Makefile`, and the test files the documents
name (`tests/test_execution_semantics.py`, `tests/test_dual_channel.py`,
`tests/test_app_isolation.py`, `tests/test_page_core.py`). Git history for M9 and M10 read to
check what was promoted before the milestone folders were deleted.

## Strengths

- The core-model documents are unusually accurate. `docs/architecture/app-model.md`'s
  `AppDefinition`, `Lifespan`, `tool_runtime_for` and `page_runtime_for` signatures match
  `src/vibepy/app/model.py` and `src/vibepy/app/composition.py` field for field, including the
  keyword-only `config`.
- `docs/architecture/errors.md`'s code table is exactly the nine codes in `src/vibepy/errors.py`,
  with the same categories, and the two retired `lifecycle.*` codes are recorded as retired
  rather than deleted — the one place in the repo where a document keeps a promise about the
  past.
- `docs/architecture/runtime.md`'s two "constitutional test" claims are real:
  `tests/test_execution_semantics.py` proves the barrier at all four layers it names
  (ToolRuntime, PageRuntime, MCP SDK, NiceGUI) and `tests/test_dual_channel.py` proves the
  single backend.
- `docs/architecture/packaging.md` is true end to end: the `vibepy.apps` group, the `AppRef`
  fields, the `(app_name, distribution)` ordering, the `python -m vibepy.describe` output and
  exit-1 behaviour, and the `python -m vibepy.serve <app> --port <n>` stdin-JSON contract all
  match `src/vibepy/app/package.py`, `src/vibepy/describe.py` and `src/vibepy/serve.py`.
- ADR-020 and ADR-023 are model Nygard records: real alternatives, cited external sources, and
  consequences that name what breaks.
- The supersession chain ADR-008 → ADR-011 → ADR-014 is complete and links in both directions.

## Findings

### Critical — a document asserts something false about the code

**C1. `docs/architecture/app-model.md:88-90` — "one entrypoint per channel" is not the model
that shipped.**

> "An installed App has one entrypoint per channel it offers. The Agent channel's is a command
> the MCP client launches; the Web channel's is what the Hub opens."

The code has exactly one entrypoint per App, not per channel. `samples/todo/pyproject.toml`
declares a single `[project.entry-points."vibepy.apps"] todo-app = "todo_app.entry:APP"`, and
`docs/architecture/packaging.md:11-21` states that same single-group model. The Web channel is
opened from that one `AppEntrypoint` by `src/vibepy/serve.py:95-103`. There is no Agent-channel
command anywhere: `grep` for `project.scripts` / `console_scripts` across all four
`pyproject.toml` files returns nothing.

Rule broken: `docs/architecture*` owns current truth. Why it matters: this is the paragraph an
App author reads to learn what to declare in their package, and following it produces a second
entry point that nothing reads. Fix: state one composition root serving both channels, and say
that the Agent channel's launch command is not yet produced by the packaging layer (ADR-010
defers it; nothing implements it).

**C2. `docs/architecture/page-model.md:135-136` — PageRegistry's enumeration is justified by a
consumer that does not exist.**

> "The registry also enumerates its declarations, because a Web channel adapter projects every
> PageDefinition into a route."

`register_pages` in `src/vibepy/adapters/nicegui/web.py:33-45` iterates `definition.pages`
twice and never touches the registry. `PageRegistry.definitions()` has no caller outside
`tests/test_page_core.py:103,116`. (The Tool side is genuinely used —
`src/vibepy/adapters/mcp/server.py:97` calls `registry.definitions()` — so the asymmetry is
real, not a reading error.)

Rule broken: current truth. Why it matters: the document gives a reason for a public method
that the reason does not support; a reader deleting the method on that basis would break only
tests, and a reader trusting it would look for the call site in the adapter and not find it.
Fix: either say the Web adapter reads the declaration directly and `definitions()` exists for a
future consumer, or drop the justification.

**C3. `docs/architecture.md:18` — the App core model still lists a Manifest, which
`docs/architecture/packaging.md:132` says does not exist.**

`docs/architecture.md` draws `App ├─ Manifest / metadata`, while
`docs/architecture/packaging.md:132` states the invariant "an App declares itself in metadata.
The framework defines no manifest format", and ADR-023 rejects inventing one. No manifest type
exists in `src/vibepy/`.

Rule broken: current truth, and "the same fact is not stated in two places" — here the two
places disagree. Why it matters: `docs/architecture.md` is the whole-system map and the first
document a new reader opens. Fix: `App ├─ package metadata (entry point)`.

### Important — duplication, ADR hygiene, ownership gaps

**I1. `AGENTS.md:16-37` restates, in whole or in part, at least eleven facts that an
architecture document also owns.**

Concrete pairs (AGENTS.md line → architecture line):

| AGENTS.md | Restated in |
| --- | --- |
| 16 "App is the unit of packaging and declaration; a channel process is the unit of execution." | `app-model.md:5-7` |
| 17 "Reading what an environment offers imports nothing, and the framework publishes no operation that imports an App into its caller's process." | `packaging.md:133-134` (verbatim) |
| 23 "MCP-specific types and behavior must not leak into the core Tool model." | `adapters.md:33` |
| 24 "NiceGUI-specific types must not leak into the core Page model." | `adapters.md:87` |
| 28 "A declaration is not a running channel." | `app-model.md:136` and `architecture.md:86` (three places) |
| 29 "Runtime lifecycle and package installation lifecycle are different concepts." | `lifecycle.md:5` and `architecture.md:87` (three places) |
| 30 "An App declares what it requires of its host as a type, and a channel validates against that declaration before it acquires anything." | `app-model.md:134-135` (verbatim but for "channel"/"window") |
| 31 "Application-scoped state … reaches a handler only through ToolContext." | `app-model.md:96-108`, `runtime.md:55-64` |
| 34 "Tool behavior must not branch on Web versus Agent channels." | `tool-model.md:143-154` |
| 35 "Internal helpers, services, policies, and repositories do not need to be Tools." | `tool-model.md:28` (verbatim) |
| 36 "Prefer meaningful business operations over generic data mutation Tools." | `tool-model.md:122-132` |

Rule broken: "One role per document. The same fact is not stated in two places." Why it matters:
this is the repository's own headline documentation rule, and it is breached most heavily by the
document that states it. The 30 → `app-model.md:134` pair has already drifted in wording
("a channel validates" vs "a window validates"), which is exactly how duplicated facts start to
disagree. Fix: pick one side per row. The defensible split is that `AGENTS.md` keeps the
short prohibitions an agent must not violate mid-task, and the architecture doc keeps the
contract with its mechanism — but whichever side loses a row should lose the sentence, not
paraphrase it.

**I2. `docs/architecture.md:82-88` ("Key distinctions") is a third copy of facts that
`AGENTS.md` and the sub-documents both already own.**

All five bullets restate something else: line 84 restates `adapters.md:25-31`, line 85 restates
`page-model.md:9`, line 86 restates `app-model.md:136`, line 87 restates `lifecycle.md:5`,
line 88 restates `tool-model.md:28`. Rule broken: same-fact-twice; a whole-system map's role is
to point at the documents that own the facts, which the "Documents" list at line 90 already
does. Fix: delete the section or reduce it to the two distinctions no sub-document states
(Tool ≠ MCP Tool is stated in `adapters.md`; nothing is left).

**I3. ADR-006 is Accepted and its Decision is false; ADR-020 contradicts it with no supersession
link.**

`docs/decisions/ADR-006-runtime-vs-package-lifecycle.md:103` — "AppRuntime manages start/stop
execution lifecycle only" — and its consequence "AppRuntime state machine remains small".
ADR-020 removed `AppRuntime`, its state machine and its two errors, and supersedes ADR-004,
ADR-015 and ADR-018 by name. ADR-006 is not in that list, so a reader following statuses reads
an Accepted decision that describes a class the codebase does not contain. Worse,
`docs/architecture/lifecycle.md:64` cites ADR-006 as a live source for the package-lifecycle
boundary — which is the half of ADR-006 that survived.

Rule broken: "an `Accepted` [ADR] is superseded, never rewritten"; statuses must be coherent.
Why it matters: ADR-006 is one of only two documents behind AGENTS.md's "Runtime lifecycle and
package installation lifecycle are different concepts" invariant, and half of it is now fiction.
Fix: a new ADR that supersedes ADR-006's runtime half and restates the surviving boundary, or
add ADR-006 to ADR-020's `Supersedes:` line if the owner reads ADR-020 as having intended it.
Do not edit ADR-006's body.

**I4. ADR-012 is Accepted and its Decision no longer matches the adapter.**

`docs/decisions/ADR-012-nicegui-adapter-registers-routes.md:301` — "register_pages projects a
PageRegistry onto NiceGUI routes". The signature is
`register_pages(definition: AppDefinition, pages: PageRuntime)`
(`src/vibepy/adapters/nicegui/web.py:25-27`); no registry is passed. Its consequence at line 312
— "the runtime lifecycle adds a call to `ui.run()` at startup" — is also dead: the Web channel
is now `ui.run_with(FastAPI(lifespan=window))` plus `uvicorn.run`
(`src/vibepy/adapters/nicegui/application.py:43-51`, `src/vibepy/serve.py:73-74`).

Rule broken: status coherence for an Accepted ADR. Why it matters: a consequence going stale is
normal for a Nygard record, but the *Decision* naming the wrong parameter is what a reader
implements against. Fix: supersede, or record the correction in the ADR that changed it — the
change landed in commit 54602f2 with no ADR at all (see I6).

**I5. Four ADRs are not in Nygard form: they have no Context.**

`ADR-003`, `ADR-004`, `ADR-005` and `ADR-006` each go straight from `Status:` to `## Decision`.
Nygard's format is Title / Status / Context / Decision / Consequences, and `AGENTS.md`
("ADRs use the Nygard format") admits no shortened variant. ADR-004 is superseded so its shape
is history; ADR-003, ADR-005 and ADR-006 are Accepted and are cited as live sources
(`runtime.md:90` cites ADR-003, `runtime.md:139` cites ADR-005, `lifecycle.md:64` cites
ADR-006). Why it matters: without a Context, none of the three says what alternative it rejected,
so none can be argued with. Fix: these are the M0-era records; if their context is unrecoverable,
say so in an editorial note rather than leaving the section absent.

**I6. Three decisions visible in the code have no ADR behind them.**

a) *The framework took a direct dependency on FastAPI and uvicorn, and the Web channel's window
became an ASGI lifespan.* `pyproject.toml:7,11` lists `fastapi>=0.115` and `uvicorn>=0.34`;
`build_web_app` returns a `FastAPI` and `serve.py` runs `uvicorn.run`. AGENTS.md's own bar — "An
ADR records a decision that changes structure, quality characteristics, **external dependencies**,
interfaces, or construction technique" — is met three times over. The reasoning exists, well
written, in `src/vibepy/adapters/nicegui/application.py:8-13` and
`docs/architecture/packaging.md:100-104`, but a module docstring is not a decision record, and
the M10 spec had explicitly specified the opposite ("It builds no FastAPI application and calls
no ASGI server: NiceGUI owns the server") before the folder was deleted. The reversal now lives
only in commit 54602f2/ab6a609 messages.

b) *`python -m vibepy.serve` as a second framework command.* ADR-023 records `vibepy.describe`
as a command; the serve command is an equally load-bearing interface decision documented only in
`packaging.md:89-107`.

c) *The Hub's diagnostic convention.* `hub/src/vibepy_hub/models.py:13-18` defines a `Diagnostic`
with `hub.*` codes returned inside output models, deliberately beside the framework's exception
model. The M10 spec asserted "`docs/architecture/errors.md` already settles this: the code table
is for framework exceptions" — but `docs/architecture/errors.md` says no such thing; it never
mentions App-defined codes at all. The convention now exists in code with neither a document nor
an ADR behind it.

Rule broken: the ADR threshold in AGENTS.md's Documentation section. Fix: one ADR for (a)+(b)
together (the Web channel is served as an ASGI application by a framework command), and either
an ADR or a paragraph in `errors.md` for (c).

**I7. No document owns the Hub as current truth.**

The Hub is ~700 lines across eight Tools, a state file, an environment-per-App installation
model, a child-process manager, a secret-holding policy and a JSON-Schema-based secret detector
(`format: password`, `hub/src/vibepy_hub/internals/configuration.py:31-43`). What the documents
say about it is: ADR-024 (why it is an App — 34 lines), three sentences in
`docs/architecture/lifecycle.md:53-64`, and one clause in `docs/architecture/packaging.md:120-121`.
Nothing owns its Tool surface, its states (`available` / `installed` / `running`), its
diagnostic codes, or the workspace/distribution layout (`pyproject.toml:14`
`members = ["hub", "samples/*"]`) that M10 introduced.

Rule broken: "On integration, promote what is still true out of the milestone folder, then
delete the folder." Commit 9cbe84f deleted a 253-line spec and a 1792-line plan and promoted
four lines. Why it matters: M11 (Hub UI) is specified against "Hub Core state", and there is no
document stating what that state is. Fix: `docs/architecture/hub.md` is justified under
"a new architecture document requires a concept that no existing document owns" — no existing
document owns the control plane. Alternatively extend `lifecycle.md`, but the Tool surface does
not belong in a lifecycle document.

**I8. `docs/architecture/authoring.md` documents nothing that exists and duplicates
`docs/roadmap.md`.**

The whole file is future scope: "The framework *should* provide", "Conceptual capabilities",
"Authoring MCP *is an adapter over*". Its "North-star dogfooding test" (line 67) —
"A fresh Codex session should be able to use repository documentation plus Authoring MCP to
build a new App, validate it, run it, test both channels, package it, and install it" — is
roadmap M18 (`docs/roadmap.md:201`) restated. Its capability list (`inspect_app`, `start_app`,
`stop_app`, `app_status`, `install_package`) is roadmap M12/M13 scope, and three of those names
now collide with Tools the Hub actually ships — with `app_status` folded into `list_apps`, so
the list is stale as well as duplicated.

Rule broken: `docs/architecture*` owns current truth; `docs/roadmap.md` owns scope and order;
`docs/milestones/` owns what is next. Why it matters: a reader cannot tell which parts of
`docs/architecture/` describe the system and which describe an intention. Fix: this belongs in
the M12 milestone folder when M12 starts; until then the roadmap already carries it.

**I9. The same aspirational-content problem, smaller, in three more architecture documents.**

`runtime.md:15-25` ("Potential future cross-cutting concerns" — authorization, audit, timeout,
tracing, metrics, rate limits) restates roadmap M14/M15/M20. `runtime.md:39-47` ("Future fields
may include: principal, actor, channel metadata, tenant, locale, permissions, trace context")
restates M14/M15. `tool-model.md:47-56` ("Future metadata may include: query/command kind,
side-effect marker, idempotency, permissions, exposure policy, risk classification") and
`tool-model.md:134-141` ("Query and command") restate M14. `architecture.md:72` lists "future
permission and audit hooks" as framework ownership. Same rule, same fix: the roadmap owns scope.
The one line worth keeping in each is the prohibition ("Do not add these before a milestone
requires them"), which is a rule and belongs to `AGENTS.md` if anywhere.

**I10. `docs/architecture/app-model.md:124-129` reproduces ADR-022's consequence nearly verbatim.**

App-model: "Adding a second resource mechanism beside ToolContext would put two answers in the
codebase to the question of where a handler's resource comes from, which is what ADR-013
settled." ADR-022 consequence: "adding a second resource mechanism beside it would put two
answers in the codebase to the question of where a handler's resource comes from, which is what
ADR-013 settled." Rule broken: `docs/decisions/` owns *why*; an architecture document owns the
contract. Why it matters: if the decision is ever revisited, the argument must be superseded in
one place, not two. Fix: app-model.md states "there is no per-invocation resource scope" and
cites ADR-022, which it already does on line 129.

The same pattern, less exactly, at `adapters.md:62-65` ("a closure is used because it is a
language guarantee rather than a library one"), which reproduces ADR-020's argument and is *also*
in `src/vibepy/adapters/nicegui/web.py:7-10`. Three copies of one rationale.

**I11. `docs/hub-ui-mockup.html` has no role under the table.**

949 lines of HTML in `docs/`, last touched by commit f057c76 ("Update the Hub UI mockup for the
configuration lifecycle"). It is neither a rule, nor current truth (no Hub UI exists — the Hub
declares `pages=[]` at `hub/src/vibepy_hub/entry.py:52`), nor a decision, nor scope, nor a
milestone folder. The M10 spec said "`docs/hub-ui-mockup.html` is not updated here; M11 owns it",
which is an admission that it is milestone material sitting outside a milestone folder. It also
already contains content that would be stale by M11: its sample diagnostic at line 646 uses the
framework code `package.entrypoint_unloadable`, whereas the Hub's own listing path emits
`hub.declaration_missing` (`hub/src/vibepy_hub/tools/installation.py:76`).

Rule broken: one role per document. Fix: move it into `docs/milestones/M11/` when M11 opens, or
state a role for it in the table.

### Minor

**M1. `docs/architecture/adapters.md:35` gives `build_mcp_server(definition, lifespan)`, omitting
the required keyword-only `config`.** The real signature
(`src/vibepy/adapters/mcp/server.py:66-72`) is
`build_mcp_server(definition, lifespan, /, *, config)`. Two lines later the same document writes
`build_web_app(definition, lifespan, config=…)` correctly, so the omission reads as an oversight
rather than a convention. Fix: add `config=…`.

**M2. `docs/architecture/packaging.md:15` uses `todo = "todo_app.entry:APP"`; the sample declares
`todo-app`** (`samples/todo/pyproject.toml`). Harmless as an illustration, but the document is
the one place that explains what the left-hand name means, and the repository's own example
disagrees with it.

**M3. `docs/architecture/errors.md:49-50` claims a branch that does not exist.** "The set is
closed and is an enum, so a branch over it ends with `assert_never`" — `grep assert_never` over
`src`, `hub` and `tests` returns nothing; `to_error_info` uses an `isinstance` check and a
mapping lookup, no branch over `ErrorCategory`. The sentence is also a restatement of
`AGENTS.md:47`. Fix: state the property (the enum is closed) and drop the claim about a branch
the framework does not yet contain.

**M4. Eight occurrences of "a app" survive the plugin→App rename.**
`docs/architecture/tool-model.md:73,96`, `docs/architecture/page-model.md:76`,
`docs/architecture/runtime.md:87,110`, `docs/decisions/ADR-021:13,45`, and
`src/vibepy/adapters/mcp/server.py:112`. ADR-021 is Accepted, so its two are a supersede-or-leave
question; the rest are editable. `docs/architecture.md:12` has the same defect in another form:
"A app authoring agent supplies the domain implementation."

**M5. No document owns the sample Apps.** `samples/notes` exists — an App with Tools, a
`SecretStr` field and no Pages, whose docstring says it exists to prove ADR-017's "an App
declaring no Pages … is complete for an agent". `docs/roadmap.md:227-248` names Todo, Customer
and Expense, and no other document mentions samples at all. Reported, not proposed: the roadmap
is the owner's.

**M6. `docs/architecture.md:90-101` ("Documents") omits `docs/decisions/`.** The map lists the
nine architecture documents and the roadmap, but not the twenty-four ADRs the architecture
documents cite forty-odd times.

**M7. `docs/.DS_Store` is present on disk but untracked and covered by `.gitignore:6`.** Not a
repository-content problem; noted only because the brief asked.

**M8. `CLAUDE.md` is clean.** It is three lines that delegate to `AGENTS.md` via `@AGENTS.md`,
duplicating nothing. No finding.

## Documented-vs-actual contract table

| Document | Contracts it states | Code match |
| --- | --- | --- |
| `architecture.md` | two channels converge at ToolRuntime; framework/app ownership split; App core model; key distinctions | Mostly true. **False**: "Manifest / metadata" (C3). **Duplicated**: key distinctions (I2), future hooks (I9), "A app" (M4), decisions/ omitted (M6) |
| `architecture/app-model.md` | `AppDefinition` fields; `Lifespan` type; `tool_runtime_for`/`page_runtime_for` signatures; config validated before lifespan; three state scopes; no per-invocation resource scope | Signatures and semantics **exact** against `app/model.py`, `app/composition.py`. **False**: "one entrypoint per channel" (C1). **Duplicated**: ADR-022 consequence (I10), AGENTS.md invariants (I1) |
| `architecture/tool-model.md` | `ToolDefinition` fields; positional-only handler params; Tool binds at construction and hides its handler; registry is storage only, `definitions()` in registration order; `invoke` = resolve/context/await; output revalidated via `model_dump(by_alias=True)` | **True** against `tool/model.py`, `tool/registry.py`, `tool/runtime.py` including the `by_alias` round trip. Aspirational sections duplicate roadmap M14 (I9) |
| `architecture/page-model.md` | `PageDefinition` = name/route/title; handler returns None, positional-only; Page not generic; `ToolInvoker` Protocol signature; `PageContext` carries only tools; `PageRuntime.render` resolves/creates/awaits; route validation lives in the adapter | **True** except the registry-enumeration justification (C2) |
| `architecture/runtime.md` | ToolContext carries app id, invocation id, dependencies; runtime creates it per invocation; no global lock; concurrency ownership table; two constitutional tests | **True**; both named tests exist and prove what is claimed. Future-field lists duplicate the roadmap (I9) |
| `architecture/lifecycle.md` | no lifecycle object or state; window = `async with`; lifespan yield semantics; cleanup table; `Package -> install -> configure -> open a channel`; Hub holds values incl. secrets, reports a secret as set, opens the Web channel with `python -m vibepy.serve` | **True**, and the secret sentence matches `hub/internals/state.py` and `configuration.py:masked` exactly. Cites ADR-006, half of which is dead (I3) |
| `architecture/packaging.md` | `vibepy.apps` group; `AppEntrypoint` shape and `describe()`; `AppRef` fields; `discover_apps` ordering and `path=`; `describe_app` imports; `AppDescription` fields; both commands; three-part isolation invariant | **True** end to end, including that `tests/test_app_isolation.py` exists and proves what is claimed. Example name mismatch (M2); ASGI/uvicorn decision unrecorded (I6) |
| `architecture/errors.md` | nine codes with categories; `app.unhandled` belongs to no class; two retired codes; `ErrorInfo` fields; `to_error_info`; Web translates nothing; Agent uses JSON-RPC `data` and a text block, not `structuredContent`, for failures | **True** against `errors.py`, `adapters/mcp/server.py` and `adapters/nicegui/`. **False detail**: the `assert_never` branch (M3). **Gap**: says nothing about App-defined diagnostic codes, which the Hub now emits (I6c) |
| `architecture/adapters.md` | MCP adapter responsibilities and projection direction; adapter builds, never runs; `register_pages` semantics; validate-all-before-register; Web translates no errors; `build_web_app` window = ASGI lifespan | **True**, including "a rejected registry leaves no half-registered app behind" (`web.py:33-45` validates in a first pass). `build_mcp_server` signature incomplete (M1); closure rationale is a third copy (I10) |
| `architecture/authoring.md` | thirteen "conceptual capabilities"; Authoring MCP as an adapter; north-star test | **Nothing exists.** Duplicates roadmap M12/M13/M18; three capability names now collide with shipped Hub Tools and `app_status` no longer exists (I8) |
| `docs/decisions/` | 24 ADRs | ADR-006 Accepted but half-false (I3); ADR-012 Accepted with a wrong Decision (I4); ADR-003/004/005/006 lack Context (I5); three implemented decisions have no ADR (I6) |
| `docs/roadmap.md` | scope and order | Owner's; reported only: M6's lifecycle states and M9's "manifest" were both departed from, and ADR-020/ADR-023 record the departures with owner approval, which is the correct handling |
| `docs/hub-ui-mockup.html` | — | No role under the table (I11) |

## Rule concerns

1. **"The same fact is not stated in two places" and "AGENTS.md owns non-negotiable rules" pull
   against each other, and the repository has not resolved it.** Almost every invariant in
   `AGENTS.md:16-37` *is* a fact an architecture document owns; stated as a rule it is the same
   fact in an imperative mood. Either the rule needs an explicit carve-out ("a rule may restate a
   contract in one sentence; the mechanism stays with the contract") or `AGENTS.md` should cite
   rather than restate. As written, I1 is unfixable without changing one of the two rules.

2. **The role table has no row for a design artifact.** `docs/hub-ui-mockup.html` is a real and
   useful thing with nowhere to live between the milestone that drew it and the milestone that
   builds it. Either milestone folders should be allowed to outlive their milestone for
   forward-looking assets, or the table needs a row.

3. **"On integration, promote what is still true" has no check.** M10 deleted 2045 lines of spec
   and plan and promoted four. Nothing in the workflow forces a reviewer to diff the deleted
   folder against the architecture documents, which is how I7 happened.

## Assessment

The documents that describe what the framework *is* are in strong shape — `app-model.md`,
`tool-model.md`, `packaging.md`, `errors.md` and `runtime.md` hold up against a line-by-line
read of the code they describe, and the ADR corpus argues rather than asserts, with sources.
That is rare and worth protecting.

Three things have gone wrong around the edges. First, three specific claims are now false
(C1-C3), of which C1 is the one that would mislead an App author writing packaging metadata.
Second, the "one role per document" rule is breached systematically rather than accidentally:
`AGENTS.md` restates eleven facts the architecture documents own, `architecture.md`'s "Key
distinctions" is a third copy of five of them, and four documents carry roadmap scope
(`authoring.md` carries nothing else). Third, M10's integration under-promoted: the Hub is the
largest single body of code in the repository and no document owns it, while three decisions
that meet AGENTS.md's own ADR threshold — the FastAPI/uvicorn dependency and ASGI-lifespan
window, the `vibepy.serve` command, and the Hub's diagnostic convention — were made in commit
messages.

Priority order: C1, C3, C2 (small, factual, cheap); then I7 and I6 (the M10 promotion debt,
before M11 builds on an undocumented Hub); then I3 and I4 (ADR statuses, which need the owner
since Accepted ADRs cannot be edited); then I1/I2/I8/I9/I10, which are one decision applied
repeatedly and should be settled as a rule (see Rule concerns 1) before being applied file by
file.
