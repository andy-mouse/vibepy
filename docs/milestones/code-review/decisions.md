# Code review follow-up — decisions of record

The full-repository code review of 2026-09-09 at `05d6027`, and the sequence agreed with the
owner for acting on it. This file exists so a new session can resume without the conversation
that produced it. It is deleted when the last stage below integrates.

Findings: `findings.md` (cross-checked). Raw per-axis reports: `reviews/`.

## How the review was run

Seven reviewer agents, each given AGENTS.md in full, `docs/architecture.md`, the ADR index and
the file tree as a shared baseline, then one axis as its *judgment responsibility* — never as a
reading limit. A seventh traced the two call paths end to end, because a defect that lives
between two regions is invisible to both.

Every finding was then re-verified against the code by the coordinator. Three outcomes are
recorded in `findings.md` alongside the confirmed ones: one finding downgraded (the mechanism is
real, no instance exists), one cross-axis disagreement adjudicated, and what was checked and
found sound.

Baseline at the time of review: `make lint typecheck test` passing, 152 tests.

## Principles the owner stated

**P1. Channel neutrality is the only thing this framework implements for itself.** It is the
capability no other library provides. Everywhere else, if an authoritative library covers the
problem, the framework delegates rather than writes its own. FastAPI and FastMCP are named as
the models — authority earned through a small surface, fast start and no magic — not as
dependencies to adopt.

**P2. The product is three distributions and nothing else.**

| Distribution | Import package | Ships with an App |
| --- | --- | --- |
| `vibepy-core` | `vibepy_core` | yes — an App bundles the framework |
| `vibepy-hub` | `vibepy_hub` | no |
| `vibepy-builder` | `vibepy_builder` | no |

`vibepy-builder` is the authoring MCP, which `docs/roadmap.md` M12 and M13 own. It does not
exist yet and L1 does not create it: an empty package would be building ahead. L1 only puts the
other two where it will go.

**P3. An App author pays nothing for the deployment shape.** A design that requires every App to
accommodate the way it is served is rejected on that ground alone.

These are not yet ADRs. A0 records them.

## Decisions

| # | Decision | Rationale |
| --- | --- | --- |
| D1 | Follow-up is split into stages A0, L1, CR1, CR2, R1, CR3 — none of them in `docs/roadmap.md`, which stays unedited | the findings span code, structure and documentation, and mixing them makes each diff unreadable |
| D2 | ADR-009 stands; FastMCP is not adopted | ADR-009 already rejected the high-level server *because* it derives a Tool's schema from a Python function signature, moving the source of truth into the SDK. That is the opposite of P1 |
| D3 | Repository moves to uv's documented workspace layout: `packages/*` members, virtual workspace root, examples out of the member tree | the current top-level `hub/` and `samples/` deviate from the layout uv documents; tests move into their own package, which also makes CI able to cover them |
| D4 | `vibepy-core` / `vibepy-hub` / `vibepy-builder`, importing as `vibepy_core` / `vibepy_hub` / `vibepy_builder` | one rule for three siblings, so no distribution's import name has to be looked up. The cost is real and accepted: every import in the Hub, the examples, the tests and the documents changes once |
| D5 | Channel SDKs move to extras: core depends on pydantic; `[web]` carries nicegui/fastapi/uvicorn, `[agent]` carries mcp | an App with no Pages currently installs the whole web stack. Under P1 the core has no channel; channels are optional |
| D6 | Web channels are fronted by **subdomain** routing, not a path prefix | verified: NiceGUI subpath serving needs `root_path` *and* manual prefixing of `html.img`, `ui.markdown` links, `.props()` URLs and RedirectResponse — a cost paid by every App author, which P3 forbids. Subdomain routing needs no accommodation from the application at all. Sources: nicegui discussions 4687 and 2813, `examples/nginx_subpath` |
| D7 | The proxy is nginx/Caddy/Traefik, never the Hub | writing a WebSocket-forwarding reverse proxy in Python is exactly the self-implementation P1 forbids |
| D8 | Ports become fixed per App, held in Hub state | a static proxy configuration cannot follow `free_port()`. Deletes `free_port()` — one less hand-rolled mechanism |
| D9 | The venv-per-App model is kept | `docs/architecture/packaging.md` states what it buys: no App's dependencies constrain another's, and no top-level import name collides. It is `uv venv` plus `uv pip install` — delegation, not self-implementation. The complexity worth removing is around it (the four name spaces), not the venv |
| D10 | Documents are corrected to match the code, not the reverse, wherever the two disagree | building what a document promises but no milestone asked for is building ahead |
| D11 | AGENTS.md's ADR rules are tightened first, and the existing records are brought to that bar in A0, before any new ADR is written | the criterion in AGENTS.md was already the industry one (Richards & Ford, by way of AWS Prescriptive Guidance), so the failure was in applying it, not in stating it. Two tests were missing and are now written down: Microsoft's *only what is difficult to reverse*, and AWS's *why it was decided, not how it was built*. Roughly five of the nineteen live records fail the second — they document an internal mechanism with no contract outside its module |
| D12 | An ADR that was wrong when written may be corrected in place | every ADR here was written and marked `Accepted` by the same author in one session. Immutability protects a decision a reviewer ratified; it does not protect an authoring defect, and citing it to avoid the correction is how the defect survives. Recorded in AGENTS.md so this does not have to be re-argued |

## Stages

Each stage gets its own `docs/milestones/<stage>/` with spec and plan, a branch, and a `--no-ff`
merge. Each stage corrects the documents its own changes invalidate; CR3 handles only the debt
that predates this work.

| Stage | Contents | Done when |
| --- | --- | --- |
| **A0** | the ADR rules in AGENTS.md, then the overhaul of the existing records against them, then one new ADR: the framework implements channel neutrality and delegates the rest (P1/P2), carrying the extras split and the three-distribution naming as its consequences | every surviving record passes the bar, and the new one was judged by the same bar rather than added on top of records that were not |
| **L1** | the layout move and the extras split. Pure restructuring, no behaviour change | the same 152 tests pass; a `notes` environment contains no nicegui; CI runs what the Makefile runs |
| **CR1** | framework core: C1 path traversal, I15 `to_error_info`, I1 `AppNotDeclared`, I6 duplicate Page name, D1 serialization schema, dead-code deletions, I14 invariant guards | a reproducing test per item |
| **CR2** | the Hub: App identity unification (dissolves I11, I18, M3, M5), I2 blocking I/O, I7/I16/I17 failure paths, I8/I9/I19 contracts, I10 state durability, I21/I22 hollow tests, I24 samples | a reproducing test per item |
| **R1** | subdomain routing and fixed ports, with its ADR. `RunningApp` returns a URL | two Apps served concurrently through one static proxy configuration |
| **CR3** | remaining documentation debt: I3, I4, I12, I13, I27, I28, and Q1–Q4 | the documents match the code |

Ordering is not arbitrary. A0 precedes L1 because the simplicity ADR is what justifies splitting
the core's dependencies. L1 precedes CR1 because a pure move must not share a diff with defect
fixes, and because it is what puts `hub` and `examples` under CI at all. CR1 precedes CR2 because
CR2's I8 and I9 are judgements about an error hierarchy CR1 repairs. R1 follows CR2 so that the
failure paths in the same files are sound first, and precedes roadmap M11, which renders the URLs
R1 defines.

## The ADR overhaul (A0)

Twenty-four records, five already superseded, nineteen live. They are sorted by what is wrong
with each, because the remedy differs:

| Defect | Records | Remedy |
| --- | --- | --- |
| wrong when written | ADR-012, whose Decision gives `register_pages` a signature it has never had | corrected in place, per D12 |
| states no rejected alternative | ADR-005 has no Context section. ADR-001 and ADR-002 have one that states the requirement instead, which is the same defect with a heading over it — and half of ADR-002's Decision is a sentence ADR-001 already carries as a consequence | Context supplied: the channel-first Tool model ADR-001 rejects, and the Web-side service layer ADR-002 rejects |
| the decision actually changed | ADR-006, which still names the `AppRuntime` that ADR-020 deleted, and which `docs/architecture/lifecycle.md` still cites as live | superseded |
| how, not why | ADR-003, 014, 016. ADR-021 was in this list on a partial reading and is not: removing `lifespan` from `AppDefinition` changes every App's public shape, and ADR-023 rests on it | marked `Deprecated`, bodies untouched, each pointing at the document that owns what survives it |
| decided but never recorded | the direct `fastapi`/`uvicorn` dependency with an ASGI-lifespan Web window, `python -m vibepy.serve` as a second command, and the Hub's `Diagnostic`/`hub.*` vocabulary | written, if they still pass the bar |

The last row matters as much as the others. The repository's problem was never that it recorded
too much; it is that it recorded the wrong altitude and then left real decisions unrecorded.

Deletion was proposed and then withdrawn. Every authority behind the bar calls the log
append-only — Microsoft states it in those words — so deleting records would break the rule in
the act of applying it, and ADR-020's body cites ADR-003, which deletion would leave pointing at
nothing. `Deprecated` is in Nygard's original status set and in the MADR template, and it leaves
the same fifteen live records while keeping the history and the citation intact.

The first pass exempted ADR-001 and ADR-002 for being foundational, which is not one of the
tests. Re-reading them against the same bar that retired ADR-003 found the same defect, and they
were repaired rather than exempted. A bar applied to the records that are easy to retire and not
to the ones that are hard is not a bar.

Nothing needed promoting. `adapters.md` already carried ADR-003's decision sentence for sentence,
and `tool-model.md` and `page-model.md` already carried what ADR-014 and ADR-016 assert — which
is why those records failed the bar in the first place.

A test replaces the index that would otherwise list which records are live. An index restates
twenty-six statuses that each record already declares, which is the defect this review found
elsewhere; `tests/test_decisions.py` asserts the rule instead, and found on its first run that
`lifecycle.md` and `composition.py` were both citing ADR-018, superseded by ADR-020 — a live
document resting on a withdrawn decision that none of the seven reviewers reported.

This runs before the new ADR is written, not after. A record added to a set that does not meet
the bar is not held to it either. Two consequences follow and are part of A0's scope: promoting
what ADR-011, 014, 016 and 021 still assert moves text into `docs/architecture/tool-model.md`,
and superseding ADR-006 changes the citation in `docs/architecture/lifecycle.md`. Both are the
documents' own maintenance, not scope creep.

I25 and I26 from `findings.md` are settled here rather than in CR3.

## Open questions for the owner

Recorded in `findings.md` as Q1–Q4. Q1 is the one that blocks work: AGENTS.md restates about
eleven facts that architecture documents own, so the repository's own one-role rule cannot be
satisfied without either a carve-out or a cite-don't-restate policy. Deciding it after CR3 edits
files means editing them twice.
