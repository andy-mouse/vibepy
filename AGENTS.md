# Repository Instructions

This repository implements an agent-native application framework where one App exposes the same backend Tools through two first-class channels:

- Web channel: Pages rendered with NiceGUI for humans
- Agent channel: Tools exposed through MCP for AI agents

## Sources

- Answers come from this repository's documents first. Search `docs/` before introducing a concept, and say what you searched.
- External behaviour comes from official documentation, cited. Training data is not a source.
- When the documentation does not answer, the authority's own code does; a workaround is not an answer.
- Where no source answers, that is an open decision. Stop and ask; do not invent.

## Boundaries

What an agent working here must not do. What the framework *is* belongs to `docs/architecture/`,
and is not repeated below.

- Tools are channel-neutral: a Tool's behaviour must not branch on Web versus Agent.
- MCP-specific types and behavior must not leak into the core Tool model.
- NiceGUI-specific types must not leak into the core Page model, unless required at the app's UI implementation boundary.
- Pages must not bypass Tools for business state changes.
- Channel adapters invoke Tools through ToolRuntime, never a handler directly.
- ToolRuntime owns generic invocation semantics, not business logic.
- Application-scoped state reaches a handler only through ToolContext, and page/session state is not application-scoped state.
- Internal helpers, services, policies, and repositories do not need to be Tools.
- Prefer meaningful business operations over generic data mutation Tools.
- Prefer explicit implementations over magic or metaprogramming until repetition justifies abstraction.
- A defect must not be called fixed while what produced it remains.

## Commands

`make install | lint | format | typecheck | test`. A change is done when `make lint typecheck test` passes.

## Python conventions

- `pyproject.toml` is the only project config. No `setup.py`, no `requirements.txt`.
- `Any` and `cast` are not acceptable in the public API. Use `Protocol`, `TypedDict`, dataclass, or `TypeVar`.
- Exhaustive branches over typed unions end with `else: assert_never(value)`.
- Optional and configuration parameters are keyword-only.
- Blocking calls inside async code are wrapped in `asyncio.to_thread`.
- Framework exceptions derive from a single base class. Exception types are the contract, not message strings.
- Tests verify public contracts, not internals. A test file is one subject, not one criterion; a test that cannot fail is deleted.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- Filesystem paths are `pathlib.Path`, never strings. The framework runs on macOS and Windows.
- The public API is a product. Keep it backward compatible; deprecate before removing.

## Milestone workflow

One milestone in `docs/roadmap.md` is one Superpowers cycle. The skills own the process.

- A milestone does not start before the previous one is merged.
- Spec and plan go to `docs/milestones/<Mn>/`, overriding the skills' default location.
- The milestone's acceptance criteria in `docs/roadmap.md` are the tests.
- Implement only the current milestone, exactly as specified. Do not build ahead.
- `docs/roadmap.md` is never edited. If a milestone cannot be implemented as specified, stop and ask.
- Push once the milestone is merged, not before. CI runs the gate on macOS and Windows; the local gate covers one. A push is not done until its run is read.

## Documentation

One role per document. The same fact is not stated in two places.

| Surface | Sole role | Updated when |
| --- | --- | --- |
| `AGENTS.md` | non-negotiable repository rules | an invariant changes |
| `docs/architecture.md`, `docs/architecture/` | current truth | a public contract changes |
| `docs/decisions/` | why | a decision is taken between real alternatives |
| `docs/roadmap.md` | scope and order of milestones | never; the owner decides |
| `docs/milestones/` | what is next | per the milestone workflow |
| git history | history | everything else |

- A new architecture document requires a concept that no existing document owns. Extend the owning document first.
- A decision earns a record when it changes structure, quality characteristics, external dependencies, interfaces or construction technique, and is difficult to reverse or constrains later decisions. An internal mechanism with no contract outside its module is neither, and goes in the commit message instead.
- A record uses the Nygard format and says why a decision was taken, not how it was built. One that reads as a design guide is not a record, and a fact another surface owns is cited rather than restated.
- A `Proposed` record is edited freely. An `Accepted` one takes corrections to typos and broken references and nothing else: what changes meaning is a new record superseding it, or an amendment appended beneath its status. A record whose Decision has become false is superseded, and its Context and Consequences are never brought up to date — they are statements as of its own date, and current truth is `docs/architecture/`.
- On integration, promote what is still true out of the milestone folder, then delete the folder.
