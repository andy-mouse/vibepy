# L1 - Workspace layout and channel extras

L1 is not a `docs/roadmap.md` milestone. Its scope and its place in the sequence come from
`docs/milestones/code-review-roadmap.md`, and the decisions it carries out are D3, D4, D5 and
finding I23 in `docs/milestones/code-review/decisions.md` and `findings.md`.

L1 moves files, renames the core distribution and splits the core's dependencies. It changes no
behaviour, which is what makes its acceptance checkable: the suite that passes now passes
identically after.

## Acceptance criteria

- `make lint typecheck test` passes with the same 152 tests and the same results
- an environment holding `vibepy-notes` contains no NiceGUI, FastAPI or uvicorn

The uvicorn half of that criterion cannot be met, and the reason is not this stage's to fix. The
MCP SDK requires uvicorn of itself — `uvicorn>=0.31.1; sys_platform != 'emscripten'` in `mcp`
2.1.1's metadata — so any environment holding MCP holds uvicorn, and `[agent]` must hold MCP.
What the criterion is about is met: an Agent-only App's environment holds no Web technology,
NiceGUI and FastAPI both being absent. A project declares what it imports and constrains
versions; pip states the boundary in its own words, that a constraints file "only control[s]
which version of a requirement is installed, not whether it is installed or not"
(<https://pip.pypa.io/en/stable/user_guide/#constraints-files>). Removing uvicorn would mean
reaching into another project's dependencies, and the place to change what MCP requires is MCP.
`docs/milestones/code-review-roadmap.md` is the owner's and is not edited.
- CI runs what the Makefile runs, so `packages/vibepy-hub` and the examples are covered there
- no file under the framework's `src/` changes except its imports and the paths in its docstrings

The last criterion has one exception, and it is the whole of it: `serve.py` passes
`prog="vibepy.serve"` to `argparse`, which is neither an import nor a docstring, and a usage line
naming a module that no longer exists is a defect the rename would introduce. It becomes
`vibepy_core.serve`. `APP_GROUP = "vibepy.apps"` is the only other such string in `src/`, and it
stays.

## Sources

| Contract | Source |
| --- | --- |
| the framework declares no channel; a channel's SDK is an extra of the core | `docs/decisions/ADR-025` |
| three distributions, `vibepy-core`, `vibepy-hub`, `vibepy-builder`, importing as `vibepy_core`, `vibepy_hub`, `vibepy_builder` | `docs/decisions/ADR-025`, decision D4 |
| every workspace needs a root, which is also a workspace member, and the documented layout is a root project with accompanying libraries under `packages/` | uv, *Using workspaces* (<https://docs.astral.sh/uv/concepts/projects/workspaces/>) |
| `UV_PROJECT_ENVIRONMENT` sets the project environment path, and an absolute path is used as-is | uv, *Configuring projects* (<https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path>) |
| the Web channel is opened by `python -m <core>.serve`, and no command opens the Agent channel | `docs/architecture/packaging.md` |
| an App declares the channels it offers | `docs/decisions/ADR-025` |
| an installed App has one entrypoint per channel it offers; the Agent channel's is a command the MCP client launches, the Web channel's is what the Hub opens | `docs/architecture/app-model.md` |
| the Hub is a platform-tier App, consumed through a UI that consumes its Tools as any Page does, and its status and stop describe the Web channel | `docs/decisions/ADR-024`, `docs/decisions/ADR-017`, `docs/roadmap.md` M11 |
| Notes exists as the App with no Web channel for a Hub to start | git `be56a96` |
| `vibepy-builder` is not created here | `docs/roadmap.md` M12 and M13 own it; AGENTS.md forbids building ahead |
| CI lints `src tests` where the Makefile lints `src tests hub samples` | `findings.md` I23 |

## Problem

Three things are wrong at once, and each one is structural rather than a defect.

The repository's own layout deviates from the only workspace layout uv documents: `hub/` and
`samples/` sit at the top level, so every tool that needs to see them names them by hand. That
hand-written list is where I23 lives — CI names two of the four directories and has enforced a
smaller check than the Makefile since the day the Hub was added.

The core distribution is named `vibepy-framework` and imports as `vibepy`, so neither name can
be derived from the other two distributions' names.

The core depends on the SDKs of both channels, so an App declaring no Pages installs a Web stack
it never serves. Under ADR-025 the core has no channel, and nothing in the packaging says so.

## Decisions recorded separately

ADR-025 owns the distribution names and the extras split. D3 owns the move to uv's layout, and
D3 is the decision this stage is the whole of; no new record is written here, because the layout
of a repository is not an interface and reversing it costs one more move.

Two readings inside D3 are settled here rather than in a record, because each is a fact about uv
rather than a choice between alternatives:

- D3 says *virtual workspace root*. uv documents no such root: "Every workspace needs a root,
  which is _also_ a workspace member", and the only layout the *Workspace layouts* section shows
  is a root project with libraries under `packages/`. The root is therefore `vibepy-core` itself.
- D3 says *tests move into their own package*. Each package's tests live with the package whose
  contracts they verify, which is what the root-project layout gives without a third member.

## Scope

1. `src/vibepy` becomes `src/vibepy_core`; the root distribution becomes `vibepy-core`.
2. `hub/` becomes `packages/vibepy-hub/`; `samples/todo` and `samples/notes` become
   `examples/todo` and `examples/notes`.
3. The core's dependencies become `pydantic` alone, with `[web]` and `[agent]` extras.
4. Each consumer declares the extras its channels need.
5. CI invokes the Makefile, so the two cannot enforce different things again.
6. Every import, command string, tool path and document path that the four moves invalidate is
   updated.

## Package layout

```text
vibepy/
├── pyproject.toml              vibepy-core, the workspace root and a member
├── uv.lock
├── AGENTS.md  CLAUDE.md  Makefile  docs/
├── src/vibepy_core/
├── tests/
├── packages/
│   └── vibepy-hub/
│       ├── pyproject.toml
│       ├── src/vibepy_hub/
│       └── tests/
└── examples/
    ├── todo/                   pyproject.toml, src/todo_app/
    └── notes/                  pyproject.toml, src/notes_app/
```

`[tool.uv.workspace]` names `members = ["packages/*", "examples/*"]`. The examples stay members
because they are what two framework tests read — `tests/test_todo_distribution.py` reads Todo's
distribution metadata and Notes is the Agent-only App an acceptance criterion is about — and a
member is installed into the one environment those tests run in.

## Public API

Four renames, taken together because they are one rename:

| Was | Is |
| --- | --- |
| distribution `vibepy-framework` | `vibepy-core` |
| import package `vibepy` | `vibepy_core` |
| `python -m vibepy.serve`, `python -m vibepy.describe` | `python -m vibepy_core.serve`, `python -m vibepy_core.describe` |
| — | extras `[web]` and `[agent]` |

The entry-point group stays `vibepy.apps`. It is the name an App declares rather than a name
anyone imports, ADR-023 owns it, and D4 renames distributions and import packages only.

`vibepy-core` depends on `pydantic`. `[web]` carries `nicegui`, `fastapi` and `uvicorn` — the
three the framework imports itself, in `adapters/nicegui/` and `serve.py` — and `[agent]` carries
`mcp`. What each consumer declares follows from the channel it is actually served on:

| Distribution | Declares | Why |
| --- | --- | --- |
| `vibepy-hub` | `vibepy-core[web]` | the Hub opens Web channels and is consumed through one. ADR-024 says a Hub UI consumes its Tools *as any Page consumes Tools*; ADR-017 says Hub status and stop describe the Web channel and the Agent channel is available whether or not the Hub runs; `app-model.md:88-90` puts the Hub on the opening side of a Web channel and the MCP client on the Agent side. `docs/roadmap.md` M11 builds that UI in NiceGUI. No document exposes the Hub itself on the Agent channel |
| `vibepy-todo` | `vibepy-core[web,agent]` | it declares Tools *and* Pages, so it offers both channels, and `tests/test_dual_channel.py` runs this one declaration through an MCP client and a NiceGUI user to prove it |
| `vibepy-notes` | `vibepy-core[agent]` | being the App with no Web channel is why it exists: "a second sample `vibepy-notes` declares Tools and no Pages — the App that has no Web channel for a Hub to start" (be56a96). This is what makes it Agent-only in its dependency tree rather than only in its declaration |

The dev group declares `vibepy-core[web,agent]` and `nicegui[testing]`, because the suite
exercises both channels.

Importing a channel adapter without its extra raises `ImportError` from the missing SDK. The
framework adds nothing to it: a message of our own would say less than the name of the package
that is absent.

## Testing

- the existing 152 tests pass unchanged in count and result. Their content changes only where a
  path or an import name appears: `tests/test_serve_command.py`,
  `tests/test_describe_command.py`, `hub/tests/tests_support.py`
- the two guards that assert no MCP or NiceGUI import in the core — `test_mcp_adapter.py:313`
  and `test_nicegui_adapter.py:150` — follow the package to `src/vibepy_core`
- one test is added for the second acceptance criterion, and it builds a real environment rather
  than reading a declaration: `UV_PROJECT_ENVIRONMENT` set to a temporary directory,
  `uv sync --package vibepy-notes --no-dev --frozen`, then that environment holds neither
  `nicegui`, `fastapi` nor `uvicorn`. It resolves from `uv.lock`, so it reaches no network

## Continuous integration

The Makefile is the only place the checks are named. CI runs `uv sync` and then
`make lint typecheck test`, so a check added to one is added to both. The Windows job installs
GNU make first, which the runner image does not carry.

## Compatibility

`vibepy-framework` was never published — version `0.0.0`, no index — so no installation breaks
and no compatibility shim is written. ADR-025 already accepted the extras split as a
compatibility event taken while there are three distributions. AGENTS.md's rule that the public
API is kept backward compatible begins from the names L1 leaves behind.

## Documentation

Only what L1 makes false: the paths, import names and command lines in
`docs/architecture/adapters.md`, `packaging.md` and `lifecycle.md`, and the extras and
dependency facts wherever `packaging.md` states what an App's environment holds. An `Accepted`
record takes a corrected file path as a broken reference and nothing else; no record's reasoning
is rewritten.

## Out of scope

- `vibepy-builder`, which `docs/roadmap.md` M12 and M13 own
- a command that opens the Agent channel (I8), and the `[project.scripts]` it needs — CR2
- every defect in CR1 and CR2, including the four App-name spaces and the unconstrained
  `remove_app` path
- R1's addressing, which needs its own ADR
