# L1 — Workspace layout and channel extras

L1 is not a `docs/roadmap.md` milestone. Its scope, acceptance criteria and place in the order
come from `docs/milestones/code-review-roadmap.md`, which is read the way `docs/roadmap.md` is.

L1 moves files and splits dependencies. It changes no behaviour, which is what makes its
acceptance criteria checkable: the suite that passes now must pass identically after.

## Acceptance criteria

- `make lint typecheck test` passes, with the same 152 tests and the same results
- an environment holding `vibepy-notes` contains no NiceGUI, FastAPI or uvicorn
- CI runs what the Makefile runs, so `hub` and the examples are linted and type-checked there
- no file under `src/` changes except its import statements and the paths in its docstrings

## Sources

| Contract | Source |
| --- | --- |
| the framework declares no channel; a channel's SDK is an extra of the core | `docs/decisions/ADR-025` |
| three distributions, `vibepy-core`, `vibepy-hub`, `vibepy-builder`, of which only the core installs with an App | `docs/decisions/ADR-025` |
| members live under `packages/`, and a workspace root need not be a package | uv, *Using workspaces* (<https://docs.astral.sh/uv/concepts/projects/workspaces/>) |
| a distribution name is hyphenated and its import package is not | uv's own example, `packages/bird-feeder/src/bird_feeder/` |
| `vibepy-builder` is not created here | `docs/roadmap.md` M12 and M13 own it; AGENTS.md forbids building ahead |
| the Web technology already requires FastAPI, Starlette and uvicorn | `importlib.metadata.requires("nicegui")` at nicegui 3.16 |

## Package layout

```text
vibepy/
├── pyproject.toml              virtual workspace root: members, dev group, ruff/pyright/pytest
├── uv.lock
├── AGENTS.md  CLAUDE.md  Makefile  docs/
├── packages/
│   ├── vibepy-core/
│   │   ├── pyproject.toml      name = "vibepy-core"
│   │   ├── src/vibepy_core/
│   │   └── tests/
│   └── vibepy-hub/
│       ├── pyproject.toml      name = "vibepy-hub"
│       ├── src/vibepy_hub/
│       └── tests/
└── examples/
    ├── todo/
    └── notes/
```

The root `pyproject.toml` keeps `[tool.uv.workspace]` and the shared tool configuration and
loses `[project]`: nothing is built from the repository root any more. Tests move to the package
whose contracts they verify, which is what lets CI name `packages/*` in one line instead of
listing directories that were easy to forget.

## Public API

Three renames, taken together because they are one rename:

| Was | Is |
| --- | --- |
| distribution `vibepy-framework` | `vibepy-core` |
| import package `vibepy` | `vibepy_core` |
| — | extras `[web]` and `[agent]` |

`vibepy-core` depends on `pydantic` alone. `[web]` carries `nicegui`, `fastapi` and `uvicorn`;
`[agent]` carries `mcp`. `examples/todo` declares `vibepy-core[web,agent]` and `examples/notes`
declares `vibepy-core[agent]`, which is what makes an Agent-only App Agent-only in its
dependency tree rather than only in its declaration.

Importing a channel adapter without its extra raises `ImportError` from the missing SDK. That is
the error the reader needs and the framework adds nothing to it: a message of our own would say
less than the name of the package that is absent.

## Compatibility

The distribution has never been published — version `0.0.0`, never pushed to an index — so no
installation breaks. Every import inside this repository changes once, in this stage, and
`AGENTS.md`'s rule that the public API is kept backward compatible begins from the names L1
leaves behind.

## Documentation

`docs/architecture/packaging.md` carries the distribution names and the entry-point examples and
is updated with them. Paths quoted in other architecture documents follow. No invariant changes
here: "the core declares no channel" is a boundary that becomes true in this stage, so
`AGENTS.md` gains that line when the split lands and not before.

## Out of scope

- `packages/vibepy-builder` — M12 and M13 own it, and an empty package is building ahead
- every defect the review found — CR1 and CR2 own them, and the roadmap lists them. A defect noticed while moving a file is
  reported, not fixed, because a fix inside a pure move cannot be reviewed as either
- subdomain routing and fixed ports — R1
- the documentation debt — CR3
