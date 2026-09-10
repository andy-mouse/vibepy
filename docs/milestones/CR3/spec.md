# CR3 - Documentation debt

CR3 is not a `docs/roadmap.md` milestone. Its scope and its place in the sequence come from
`docs/milestones/code-review-roadmap.md`. It acts on I3, I4, I13, I27 and I28 in
`docs/milestones/code-review/findings.md`, answers Q2 to Q4 there, and carries the docstring
convention the owner added to this stage.

One sentence states the whole of it: **every surface that describes this framework says what is
true today, and where a standard already governs a surface, the standard is switched on rather
than restated.** No code behaviour changes. Where a document and the code disagree, the document
is corrected — D10 in `code-review/decisions.md`.

## Acceptance criteria

From `code-review-roadmap.md`:

- no architecture document claims a guarantee the code does not provide: routes leaving with the
  window, and an Agent-channel command that does not exist
- the Hub is owned by a document, so M11 is specified against something defined
- `authoring.md` describes what exists or is retired
- the decisions taken but never recorded are recorded, or ruled below the bar
- the open questions Q2 to Q4 are answered: whether a Tool name is validated, whether two import
  surfaces are supported, and where a design artifact such as `hub-ui-mockup.html` belongs

Added to this stage by the owner:

- the docstrings under `src/` and `packages/*/src` satisfy PEP 257, and `make lint` is what says
  so, so the convention holds after this stage rather than during it
- what a docstring says and what a comment says is decided by the published conventions, applied
  site by site

## Sources

| Contract | Source |
| --- | --- |
| the stage's scope, its acceptance criteria and its place in the sequence | `docs/milestones/code-review-roadmap.md` |
| what each finding is, where it lives and how it was verified | `docs/milestones/code-review/findings.md`, I3, I4, I13, I27, I28, Q2 to Q4 |
| where a document and the code disagree, the document is corrected | `docs/milestones/code-review/decisions.md`, D10 |
| the repository moves to uv's documented workspace layout, which no record owns | `docs/milestones/code-review/decisions.md`, D3 |
| one role per document, and the same fact is not stated in two places | `AGENTS.md` |
| a record is earned by a decision that changes structure, interfaces or construction technique and is difficult to reverse | `AGENTS.md` |
| the Hub is a platform-tier App | `docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md` |
| the Web channel's routes are registered on the technology's process-global table inside the window, and that decision does not make them leave with it | `docs/decisions/ADR-026-the-web-window-is-the-served-applications-lifespan.md` |
| NiceGUI registers routes on a process-global app object, so one process serves one App's Pages | `docs/decisions/ADR-012-nicegui-adapter-registers-routes.md` |
| the framework defines no manifest format; a distribution points at its App through an entry point | `docs/decisions/ADR-023-a-package-points-at-its-app-through-an-entry-point.md` |
| a docstring "should summarize its behavior and document its arguments, return value(s), side effects, exceptions raised, and restrictions on when it can be called", and a summary line "prescribes the function or method's effect as a command" | PEP 257, *Docstring Conventions* (<https://peps.python.org/pep-0257/>) |
| "Write docstrings for all public modules, functions, classes, and methods"; "Comments that contradict the code are worse than no comments" | PEP 8, *Style Guide for Python Code* (<https://peps.python.org/pep-0008/>) |
| a docstring "should describe the function's calling syntax and its semantics, but generally not its implementation details, unless those details are relevant to how the function is to be used"; comments belong in "tricky parts of the code" and "Never describe the code... explain why" | Google, *Python Style Guide* §3.8 (<https://google.github.io/styleguide/pyguide.html>) |
| pydocstyle is implemented as the `D` rules, selected in `lint.select`, and `lint.pydocstyle.convention` selects which of them a convention disables | ruff, *Settings* (<https://docs.astral.sh/ruff/settings/>) |
| a repository path in a shipped docstring is a reference the consumer of the wheel cannot resolve | commit `682c8cd`, and `[tool.hatch.build.targets.wheel] packages = ["src/vibepy_core"]` |

## Problem

**Two documents promise what the code does not do.** `adapters.md:76-78` states that routes are
"registered as the window opens and left when it closes". They are not: `register_pages` calls
`ui.page(...)`, which mutates NiceGUI's process-global route table, and nothing removes an entry.
ADR-026 says so in its own consequences — "this decision does not make them leave with it" — so
the document contradicts the record it rests on. The same sentence is repeated in two docstrings,
`adapters/nicegui/application.py` and `adapters/nicegui/web.py`. `app-model.md:91` states that
the Agent channel's entrypoint is "a command the MCP client launches". No `[project.scripts]`
exists in any of the five project files, and no module runs an Agent channel; the Agent-only
fixture is reachable by nobody.

**The stale core-model diagram.** `architecture.md:18` still lists `Manifest / metadata` among
the core model's parts. `packaging.md` and ADR-023 state that the framework defines no manifest
format.

**No document owns the role the Hub plays.** `docs/architecture/` carries nine documents, and the
Hub appears in four of them as an aside. Its eight Tools, its `state` vocabulary and its fifteen
`hub.*` diagnostic codes are defined in `vibepy_hub/models.py` alone, so M11 is specified against
"Hub Core state" that no document defines. What is missing is not a document about the Hub: it is
the counterpart to `authoring.md`. An App's lifecycle is carried by two roles — authoring, which
`authoring.md` already owns, and operation, which nothing owns — and naming the missing document
after the Hub would name an implementation where the sibling names a role.

**`authoring.md` lists capabilities that do not exist and names that are taken.** `app_status` was
never built, and `start_app`, `stop_app` and `install_package` now collide with Tools the Hub
ships (`start_app`, `stop_app`, `install_app`), which belong to the operation role, not the
authoring one.

**A docstring convention that nothing keeps.** `make lint` does not select the `D` rules, so
PEP 257 is unenforced: 81 violations stand under the `pep257` convention across `src/` and
`packages/*/src` — 30 non-imperative summaries, 22 undocumented `__init__`, 21 undocumented
public methods, 8 undocumented public classes. Separately, commit `682c8cd` removed repository
paths from shipped docstrings on the ground that the wheel ships only `src/vibepy_core`; 28 such
references now stand again across 16 modules, because that reasoning was recorded in a commit
message and in no gate.

## Decisions

**The operation role gets a document, and the Hub is described inside it.**
`docs/architecture/operation.md`, *App Operation Architecture*, sibling to `authoring.md` and
written in its shape: the role's goal, what the framework is responsible for, the channel-neutral
core before any channel, the role's capabilities, what it must not become, and the north-star
test. The Hub is that role's current implementation and is described there — its Tools, its state
vocabulary and its diagnostic vocabulary — which is what M11 is then specified against. Naming the
document after the role rather than after the Hub is what keeps it true if the implementation is
reshaped later.

**No record and no document states where the Hub is going.** The owner holds the direction that
consumption and authoring become two channels of one App; `docs/roadmap.md` is where it lands and
the owner owns that file. CR3 writes the two roles as they are and takes no position on the
distribution shape.

**`authoring.md` is corrected, not retired.** It owns the authoring role, which is a real half of
the pair. The capability names that collide with the operation role's shipped Tools are removed
from it, `app_status` with them.

**Q2: a Tool name is not validated, and `tool-model.md` says so.** Registration refuses a
duplicate name — the window rejects a declaration carrying one name twice — and nothing checks a
name's format. The framework publishes no name grammar of its own: the constraint that exists
belongs to a channel's protocol, not to the Tool model. Stating that is the whole answer; no code
changes, because adding validation here would be the framework implementing a channel's rule for
it.

**Q3: the package root is the public import surface.** `tests/test_package.py` already asserts the
exact contents of `vibepy_core.__all__`, so the root is a guarded surface, not an accident. The
subpackages are internal structure. What made the question askable is that no consumer uses the
root: `fixtures/*` and `vibepy_hub` import from `vibepy_core.tool`, `.app`, `.page` and `.errors`
in 20 places, and the documents show no import at all. The imports move to the root, and
`app-model.md` states which surface an App author uses. Under `AGENTS.md`'s backward-compatibility
rule the subpackage paths keep working; they are simply not what is documented or used.

**Q4: the mockup moves to `docs/milestones/M11/`.** It says what is next rather than what is true,
and the milestone workflow already deletes that folder on integration, so the artifact disappears
when M11 renders the real thing. The role table gains no row and `AGENTS.md` is not edited.

**D3 is ruled below the bar and no record is written.** The uv workspace layout — a virtual root,
`packages/*` and `fixtures/*` as members, the core at the root — was decided in L1 and is recorded
nowhere, and it stays that way. What is a public contract about the distributions is already
recorded: ADR-025 carries which three exist, what each is named and how the extras split. Where
their source directories sit changes no interface, and the layout was not chosen between real
alternatives — it is the one uv documents, adopted as documented, which is delegation rather than
a decision. `packaging.md` owns what an environment holds, and git history records the move.

**The docstring conventions are switched on, and the published conventions decide what a
docstring holds.** `lint.select` gains `D` with `convention = "pep257"`, so `make lint` keeps
PEP 257 after this stage. What each docstring says is then decided by the sources above, applied
site by site rather than by a blanket rule:

- a docstring documents behaviour, arguments, return value, side effects, exceptions and
  restrictions, with the summary line in the imperative — PEP 257
- implementation detail belongs in a docstring only when it is "relevant to how the function is to
  be used" — Google §3.8
- what explains why the code is shaped as it is belongs to a comment, where the code reader needs
  it — Google §3.8, and PEP 8's requirement that a comment not contradict the code

Each of the 28 ADR and `docs/` references is judged by that test: one that a caller needs in order
to use the callable stays, one that explains the implementation to a maintainer becomes a comment
at the site it explains, and one restating a fact an architecture document owns is deleted, since
`AGENTS.md` forbids the same fact in two places. Nothing is moved wholesale.

**No gate is built for documentation.** The `D` rules are a published linter's implementation of a
published standard, which is why they are switched on. Beyond them, no test, hook or script is
added to police prose: CR3 corrects the surfaces and leaves enforcement to the standard that
exists.

## Scope

1. **`docs/architecture/operation.md`**, new, in `authoring.md`'s shape, carrying the Hub as the
   role's current implementation: its eight Tools, `AppRow.state`, and the `hub.*` codes with
   their categories, cited from `vibepy_hub/models.py` rather than copied where the code is the
   contract.
2. **`authoring.md`** loses `app_status` and the names the operation role owns, and gains the
   sentence that says which half of the lifecycle it is.
3. **I3**: `adapters.md:76-78` states what the window owns — the PageRuntime a builder closes over
   — and states that routes stay on the process-global table, citing ADR-026's consequence. The
   two docstrings follow. `tests/test_nicegui_adapter.py`'s own docstring already states that the
   tests isolate the global table themselves, and is left alone.
4. **I4**: `app-model.md:91` states that an App's Agent channel has no command today and that
   `packaging.md` owns what commands exist. `packaging.md` is checked against the same fact: it
   documents `python -m vibepy_core.describe` and `python -m vibepy_core.serve`, both of which
   exist, and must not imply a third.
5. **I27**: `Manifest / metadata` leaves the diagram at `architecture.md:18`.
6. **Q2**: `tool-model.md` states that a duplicate name is refused, a name's format is not
   validated, and a channel's protocol owns any grammar.
7. **Q3**: `app-model.md` states that `vibepy_core` is the import surface; the 20 subpackage
   imports in `fixtures/*` and `vibepy_hub` move to the root.
8. **Q4**: `docs/hub-ui-mockup.html` moves to `docs/milestones/M11/hub-ui-mockup.html`. Nothing
   in the repository references its path, so the move is the whole of it.
9. **The docstring pass**: `D` selected with the `pep257` convention, the 81 violations resolved,
    and the 28 references judged by the criterion above. One commit, separate from the document
    corrections.
10. **`code-review-roadmap.md`**: R1 is marked merged and `## Order` names CR3 as current. The
    file's own instruction — delete it when CR3 merges — is carried out at integration, together
    with the `code-review/` folder, promoting what is still true first.

## Public API

| Change | Kind |
| --- | --- |
| `vibepy_core`'s root export list | unchanged; it is documented as the public surface |
| `vibepy_core.tool`, `.app`, `.page`, `.errors` as import paths | unchanged and still working; no longer what documents and consumers use |
| every docstring under `src/` and `packages/*/src` | rewritten to the convention where it does not already satisfy it |

No signature, model or behaviour changes. `AGENTS.md` is not edited.

## Where each thing lives

**The role documents are a pair, and each owns one half of an App's lifecycle.**
`authoring.md` owns how an App comes to exist and be validated; `operation.md` owns how an
existing App is installed, addressed, started, stopped and reached. Neither owns the core model —
`app-model.md`, `tool-model.md` and `page-model.md` do — and neither restates it.

**The Hub's vocabularies stay in the code and are cited, not copied.** `models.py` carries the
code table today because CR2 and R1 put it there. `operation.md` names the vocabulary and points
at it: two copies of fifteen codes is the failure `AGENTS.md` names.

**The docstring pass is its own commit.** A convention pass across 16 modules and a set of
document corrections in one diff makes both unreadable, and the pass is what the memory of the
previous stage says to run last.

## Errors

No row joins `errors.md` and no `hub.*` code is added, removed or recategorized.

## Testing

`make test` collects 252 tests where CR3 begins, and collects 252 where it ends. Nothing in this
stage changes behaviour, so nothing here is provable by a new test, and none is written — a test
that cannot fail is deleted, which is the standing rule.

What the stage is verified by instead:

- `make lint typecheck test` passes, with `D` selected, which is what makes the docstring
  criterion hold rather than be asserted
- the Q3 import move is verified by the existing suite: `fixtures/*` and `vibepy_hub` are imported
  by tests that already exercise both channels, so a wrong import fails them
- the document corrections are verified by reading them against the code they describe, which is
  what the second review round is for

## Compatibility

Nothing outside this repository consumes these documents. The subpackage import paths keep
working, so an App written against them is unaffected. `docs/hub-ui-mockup.html` changes path and
nothing links to it.

## Out of scope

- **Unregistering routes.** D10 corrects the document, and ADR-026 already states that routes stay
  on the process-global table. Making them leave would be implementing what a document promised
  and no milestone asked for.
- **An Agent-channel command.** `docs/roadmap.md` M12 and M13 own the authoring channel; adding a
  command here would be building ahead.
- **`hub.md`, and any statement about the Hub becoming one App with two channels.** The direction
  is the owner's, and `docs/roadmap.md` is where it is taken.
- **Validating a Tool name.** Q2's answer is that the framework does not, stated in the document.
- **Deleting the subpackage import paths.** Backward compatibility, and no criterion asks for it.
- **A gate over prose.** No test, hook or script polices documentation; `D` is the only enforcement
  added, and it is a standard.
- **A record for the workspace layout.** Ruled below the bar above, with the reasoning stated
  there so the ruling is answerable.
- **`AGENTS.md`.** The owner owns it, and no acceptance criterion here requires an edit to it.
- **Promoting `code-review/` and deleting it.** That happens at integration, per the milestone
  workflow, not as a task inside the stage.
