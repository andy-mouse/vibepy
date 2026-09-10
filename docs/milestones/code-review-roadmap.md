# Code Review Roadmap

The stages that act on the full-repository review of 2026-09-09 at `05d6027`. None of them is in
`docs/roadmap.md`, which the owner owns and which is not edited; this file plays the same part
for this work and is read the same way. A stage's acceptance criteria are its tests, its spec and
plan go to `docs/milestones/<stage>/`, and a stage does not start before the previous one merges.

The review ran as seven agents, each holding one area as its judgment responsibility while
reading anywhere, plus one tracing the two call paths end to end. Every finding was re-verified
against the code before it reached this file.

Each stage's acceptance criteria below name what to fix. Why a finding was judged the way it was
— what was reproduced, what was read, what was reported and rejected — is in
`code-review/findings.md`, and the seven reports it was distilled from are in
`code-review/reviews/`. The principles the owner stated and the decisions taken about how to act
on the review are in `code-review/decisions.md`.

Delete this file when CR3 merges.

## A0 - Decision records

Give ADRs a bar in `AGENTS.md`, bring the existing records to it, then record what the framework
builds for itself and what it adopts.

Acceptance:
- every surviving record passes the bar, and the bar was applied before the new record was written
- the framework's own boundary is recorded: channel neutrality is implemented here, and where an
  authoritative library covers a problem the framework delegates

Merged.

## Q1 - AGENTS.md holds boundaries

Twelve of the twenty-two invariants described what the framework is, which the architecture
documents already carried — and one copy had drifted. Lifted ahead of CR3 because every later
stage has to know what belongs in `AGENTS.md`.

Acceptance:
- `AGENTS.md` states only what an agent must not do
- no fact appears both there and in an architecture document

Merged.

## L1 - Workspace layout and channel extras

Move to the layout uv documents, rename the distributions, and make each channel's SDK an extra
of the core. Pure restructuring: no behaviour changes.

Acceptance:
- `make lint typecheck test` passes with the same 152 tests and the same results
- an environment holding `vibepy-notes` contains no NiceGUI, FastAPI or uvicorn
- CI runs what the Makefile runs, so `hub` and the examples are covered there
- no file under `src/` changes except its imports and the paths in its docstrings

Merged.

## CR1 - Framework core defects

Fix the defects in the framework itself and the guards that would have caught them.

Acceptance:
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

Merged.

## CR2 - Hub defects

Unify what identifies an App, then fix the failure paths that the four competing names produced.

Acceptance:
- an App is addressed by one name across install, configure, start, stop and list; installing by
  a project name and by a folder name cannot produce two rows
- the App a Hub starts is the App its facts describe, joined by identity rather than by position
- no Hub Tool handler performs filesystem, process or metadata work on the event loop
- a child process is owned from the moment it exists, so cancellation or a broken stdin cannot
  leave one the window cannot release
- a failed install leaves no environment behind, and a source folder that has disappeared yields
  a diagnostic rather than an exception
- `config.invalid` and the fields that failed survive the process boundary into the Hub's answer
- one failure model reaches an agent, carrying the category that says whether a retry can succeed
- Hub state survives a concurrent write and an interrupted one
- `start_app`'s `secrets`, `hub.already_running` and `hub.declaration_missing` have tests, and
  the Hub tests that assert less than their names claim assert what they claim
- the Todo example writes to the path it declares, ships no test scaffolding, and narrows a Tool
  result by validation rather than by `assert`

Merged.

## R1 - One address per App

The Hub gives each App a stable port held in its state, and a proxy in front maps one hostname
per App to it. Subdomain routing rather than a path prefix: serving a Page under a prefix
requires `root_path` and manual prefixing inside the App's own markup, which is a cost every App
author would pay. The proxy is nginx, Caddy or Traefik — writing one here is the
self-implementation A0's record rules out. Needs its own ADR.

Acceptance:
- two Apps are served concurrently through one static proxy configuration
- `RunningApp` answers with an address rather than a port, and `free_port` is gone
- an App's own code contains nothing that exists because of how it is served

Precedes `docs/roadmap.md` M11, which renders these addresses.

## CR3 - Documentation debt

Acceptance:
- no architecture document claims a guarantee the code does not provide: routes leaving with the
  window, and an Agent-channel command that does not exist
- the Hub is owned by a document, so M11 is specified against something defined
- `authoring.md` describes what exists or is retired
- the decisions taken but never recorded are recorded, or ruled below the bar
- the open questions Q2 to Q4 are answered: whether a Tool name is validated, whether two import
  surfaces are supported, and where a design artifact such as `hub-ui-mockup.html` belongs

## Order

CR3 — next.

A0 before L1: the record of what the framework adopts is what justifies splitting the core's
dependencies. L1 before CR1: a pure move must not share a diff with defect fixes, and it is what
puts `hub` and the examples under CI at all. CR1 before CR2: CR2's judgements about error
propagation rest on the hierarchy CR1 repairs. R1 after CR2: the failure paths in those files
are sound first. CR3 last, because every stage before it changes what is true — each stage still
corrects the documents its own changes invalidate, and CR3 takes only the debt that predates
this work.
