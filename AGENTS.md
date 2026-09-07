# Repository Instructions

This repository implements an agent-native application framework where one App exposes the same backend Tools through two first-class channels:

- Web channel: Pages rendered with NiceGUI for humans
- Agent channel: Tools exposed through MCP for AI agents

Read `docs/architecture.md` before modifying framework code.

- Statements about external libraries, tools, or standards cite official documentation. Training data is not a source.
- Silence in this repository's documents is an open decision, not permission. Stop and ask.

## Core invariants

- App is the unit of application definition and runtime composition.
- Tools are the canonical public backend operations of an App.
- Tools are channel-neutral.
- Pages consume Tools to implement human workflows.
- NiceGUI is the Web channel technology used to expose Pages to humans.
- MCP is the Agent channel technology used to expose Tools to agents.
- MCP-specific types and behavior must not leak into the core Tool model.
- NiceGUI-specific types must not leak into the core Page model.
- Pages must not bypass Tools for business state changes.
- Channel adapters invoke Tools through ToolRuntime.
- ToolRuntime owns generic invocation semantics, not business logic.
- AppDefinition and AppRuntime are different concepts.
- Runtime lifecycle and package installation lifecycle are different concepts.
- App-scoped state belongs to AppRuntime.
- Page/session state is not application-scoped state.
- Invocation state belongs to ToolContext.
- Tool behavior must not branch on Web versus Agent channels.
- Internal helpers, services, policies, and repositories do not need to be Tools.
- Prefer meaningful business operations over generic data mutation Tools.
- Prefer explicit implementations over magic or metaprogramming until repetition justifies abstraction.

## Commands

`make install | lint | format | typecheck | test`. A change is done when `make lint typecheck test` passes.

## Python conventions

- `pyproject.toml` is the only project config. No `setup.py`, no `requirements.txt`.
- `Any` and `cast` are not acceptable in the public API. Use `Protocol`, `TypedDict`, dataclass, or `TypeVar`.
- Exhaustive branches over typed unions end with `else: assert_never(value)`.
- Optional and configuration parameters are keyword-only.
- Blocking calls inside async code are wrapped in `asyncio.to_thread`.
- Framework exceptions derive from a single base class. Exception types are the contract, not message strings.
- Tests verify public contracts, not internals.
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
- Push once the milestone is merged, not before.

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

- ADRs use the Nygard format. Edit a `Proposed` ADR; supersede an `Accepted` one, never rewrite it.
- On integration, promote what is still true out of the milestone folder, then delete the folder.
