# Repository Instructions

This repository implements an agent-native application framework where one App exposes the same backend Tools through two first-class channels:

- Web channel: Pages rendered with NiceGUI for humans
- Agent channel: Tools exposed through MCP for AI agents

Read `docs/architecture.md` before modifying framework code.

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

- `make install` - sync dependencies and install pre-commit hooks
- `make lint` / `make format` - ruff
- `make typecheck` - pyright strict
- `make test` - pytest

Every change must pass `make lint typecheck test` before it is considered done.

## Python conventions

- uv manages dependencies and the environment. `uv.lock` is committed.
- `pyproject.toml` is the single source of project configuration. No `setup.py`, no `requirements.txt`.
- The package lives under `src/`.
- ruff lints and formats. pyright runs in strict mode. Both are pre-commit hooks and merge gates.
- `Any` and `cast` are not acceptable in the public API. Use `Protocol`, `TypedDict`, dataclass, or `TypeVar`.
- Exhaustive branches over typed unions end with `else: assert_never(value)`.
- Optional and configuration parameters are keyword-only.
- Blocking calls inside async code are wrapped in `asyncio.to_thread`.
- Framework exceptions derive from a single base class. Exception types are the contract, not message strings.
- Tests use pytest and verify public contracts. Prefer integration tests over unit tests where both apply.
- Standard `logging` only, `getLogger(__name__)` per module. No `print`.
- The public API is a product. Keep it backward compatible; deprecate before removing.

## Milestone workflow

One milestone in `docs/roadmap.md` is one Superpowers cycle. The skills own the process.

- A milestone does not start before the previous one is merged.
- Spec and plan go to `docs/milestones/<Mn>/`, overriding the skills' default location.
- The milestone's acceptance criteria in `docs/roadmap.md` are the tests.
- Implement only the current milestone. Do not build ahead.

## Documentation

One role per document. The same fact is not stated in two places.

| Surface | Sole role |
| --- | --- |
| `AGENTS.md` | non-negotiable repository rules |
| `docs/architecture.md`, `docs/architecture/` | current truth |
| `docs/decisions/` | why |
| `docs/roadmap.md` | scope and order of milestones |
| `docs/milestones/` | what is next |
| git history | history |

What triggers an update:

- A change to a public contract updates `docs/architecture/`.
- A new or changed invariant updates `AGENTS.md`.
- A decision taken between real alternatives adds an ADR.
- A change to milestone scope updates `docs/roadmap.md`.
- Everything else belongs in the commit message, not in a document.

ADRs follow the Nygard format with a `Status:` line. A `Proposed` ADR may be edited; the substance of an `Accepted` one is never rewritten, only superseded by a new ADR.

Milestone specs and plans are not a source of current truth. On integration, whatever is still true is promoted into `docs/architecture/` or an ADR, and the milestone folder is removed.
