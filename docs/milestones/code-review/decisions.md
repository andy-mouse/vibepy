# Code review follow-up — decisions of record

The full-repository code review of 2026-09-09 at `05d6027`, and what was agreed with the owner
about acting on it. This file holds what only the conversation knows: how the review was run,
the principles the owner stated, and the decisions no other document owns yet. A fact another
surface owns is cited here, not repeated. It is deleted when the last stage integrates.

- what each stage does, what it has to satisfy, and why they run in that order:
  `../code-review-roadmap.md`
- what was found, where, and how each finding was verified: `findings.md`, and the seven reports
  it was distilled from in `reviews/`
- the open questions the owner still has to answer: `findings.md`, Q2 to Q4

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

**P2. The product is three distributions and nothing else** — `vibepy-core`, `vibepy-hub`,
`vibepy-builder`, of which only the core ships with an App.

P1 and P2 are recorded: ADR-025, which also carries the distribution table and the extras split.
They are restated here only because the stages below were reasoned from them before it existed.

**P3. An App author pays nothing for the deployment shape.** A design that requires every App to
accommodate the way it is served is rejected on that ground alone. No record owns this yet; R1's
ADR is where it lands.

## Decisions

The stage each one is carried out by is `../code-review-roadmap.md`.

| # | Decision | Rationale | Owned by |
| --- | --- | --- | --- |
| D1 | Follow-up is split into stages A0, L1, CR1, CR2, R1, CR3 — none of them in `docs/roadmap.md`, which stays unedited | the findings span code, structure and documentation, and mixing them makes each diff unreadable | `../code-review-roadmap.md` |
| D2 | ADR-009 stands; FastMCP is not adopted | ADR-009 already rejected the high-level server *because* it derives a Tool's schema from a Python function signature, moving the source of truth into the SDK. That is the opposite of P1 | ADR-009 |
| D3 | Repository moves to uv's documented workspace layout: `packages/*` members, virtual workspace root, examples out of the member tree | the current top-level `hub/` and `samples/` deviate from the layout uv documents; tests move into their own package, which also makes CI able to cover them | nothing yet; L1 |
| D4 | `vibepy-core` / `vibepy-hub` / `vibepy-builder`, importing as `vibepy_core` / `vibepy_hub` / `vibepy_builder` | one rule for three siblings, so no distribution's import name has to be looked up. The cost is real and accepted: every import in the Hub, the examples, the tests and the documents changes once | ADR-025 |
| D5 | Channel SDKs move to extras: core depends on pydantic; `[web]` carries nicegui/fastapi/uvicorn, `[agent]` carries mcp | an App with no Pages currently installs the whole web stack. Under P1 the core has no channel; channels are optional | ADR-025 |
| D6 | Web channels are fronted by **subdomain** routing, not a path prefix | verified: NiceGUI subpath serving needs `root_path` *and* manual prefixing of `html.img`, `ui.markdown` links, `.props()` URLs and RedirectResponse — a cost paid by every App author, which P3 forbids. Subdomain routing needs no accommodation from the application at all. Sources: nicegui discussions 4687 and 2813, `examples/nginx_subpath` | nothing yet; R1 |
| D7 | The proxy is nginx/Caddy/Traefik, never the Hub | writing a WebSocket-forwarding reverse proxy in Python is exactly the self-implementation P1 forbids | nothing yet; R1 |
| D8 | Ports become fixed per App, held in Hub state | a static proxy configuration cannot follow `free_port()`. Deletes `free_port()` — one less hand-rolled mechanism | nothing yet; R1 |
| D9 | The venv-per-App model is kept | `packaging.md` states what it buys: no App's dependencies constrain another's, and no top-level import name collides. It is `uv venv` plus `uv pip install` — delegation, not self-implementation. The complexity worth removing is around it (the four name spaces), not the venv | `docs/architecture/packaging.md` |
| D10 | Documents are corrected to match the code, not the reverse, wherever the two disagree | building what a document promises but no milestone asked for is building ahead | nothing; it governs CR3 |
| D11 | AGENTS.md's ADR rules are tightened first, and the existing records are brought to that bar before any new ADR is written | the criterion in AGENTS.md was already the industry one (Richards & Ford, by way of AWS Prescriptive Guidance), so the failure was in applying it, not in stating it. Two tests were missing: Microsoft's *only what is difficult to reverse*, and AWS's *why it was decided, not how it was built* | `AGENTS.md` |
| D12 | An `Accepted` record takes typo and broken-reference corrections and nothing else | the carve-out that let an authoring defect be corrected in place was a deviation from every source behind the bar, and it was used to rewrite three records' reasoning before it was withdrawn. Nobody needs a record to be current, because `docs/architecture/` is what current truth is read from | `AGENTS.md` |

## Which stage answers which finding

| Stage | Findings |
| --- | --- |
| A0 — merged | I25, I26 |
| Q1 — merged | I12 |
| L1 — next | I23 |
| CR1 | C1, I1, I5, I6, I14, I15, I20, D1 |
| CR2 | I2, I7, I8, I9, I10, I11, I16, I17, I18, I19, I21, I22, I24 |
| R1 | none; it acts on D6 to D8 |
| CR3 | I3, I4, I13, I27, I28, and Q2 to Q4 |

CR2's App-identity unification dissolves I11 and I18 together rather than fixing them separately.

## What A0 settled, and what it cost

The outcome is in the records themselves and in AGENTS.md. What is written here is only the
reasoning that produced it, because it is what stops the same three mistakes being made again.

Twenty-four records, five already superseded, nineteen live. Sorted by what was wrong with each,
because the remedy differs: a record that was wrong when written takes an amendment (ADR-012);
one that states no rejected alternative takes nothing, because reasoning that was not recorded
is a fact about the record; one whose decision actually changed is superseded (ADR-006); one
that documents how rather than why is deprecated with its body untouched (ADR-003, 014, 016);
and a decision taken but never recorded is written.

That last case matters as much as the others. The repository's problem was never that it
recorded too much; it is that it recorded the wrong altitude and then left real decisions
unrecorded — the ASGI-lifespan Web window, `python -m vibepy.serve`, and the Hub's `Diagnostic`
vocabulary were all live and undocumented.

Deletion was proposed and then withdrawn. Every authority behind the bar calls the log
append-only — Microsoft states it in those words — so deleting records would break the rule in
the act of applying it, and ADR-020's body cites ADR-003, which deletion would leave pointing at
nothing. `Deprecated` is in Nygard's original status set and in the MADR template, and it keeps
the history and the citation intact.

ADR-021 was classified for deprecation on a partial reading and is not: removing `lifespan` from
`AppDefinition` changes every App's public shape, and ADR-023 rests on it.

Three passes were needed and each corrected the one before it. The first exempted ADR-001 and
ADR-002 for being foundational, which is not one of the tests. The second repaired them by
writing the Context they lack — worse, because an `Accepted` record allows only typo and
broken-reference corrections, so a reader can tell what was recorded then from what someone
reconstructed later. The third reverted that. The pattern in all three is asking a record to be
persuasive today, which is not its role.

Two things were built during A0 and removed. An index of live records would have restated
twenty-six statuses each record already declares. A test gating ADR status was written and
deleted: `make test` verifies the framework's public contracts, and an ADR's status is not one.
While it existed it found `lifecycle.md` and `composition.py` both citing ADR-018, superseded by
ADR-020 — a live document resting on a withdrawn decision that none of the seven reviewers
reported. Both are fixed.

Nothing needed promoting out of the deprecated records. `adapters.md` already carried ADR-003's
decision sentence for sentence, and `tool-model.md` and `page-model.md` already carried what
ADR-014 and ADR-016 assert — which is why those records failed the bar in the first place.
