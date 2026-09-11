# M13 - Authoring MCP

Date: 2026-09-11

## Acceptance criteria

From `docs/roadmap.md`, verbatim:

- Authoring capabilities are discoverable through MCP
- MCP calls delegate to Authoring Core rather than duplicating authoring behavior
- structured validation and runtime results are preserved through the MCP surface

## Sources

| Contract | Source |
| --- | --- |
| Authoring is Studio's Agent channel; its Tools reach an agent over MCP as any App's do; "the Agent channel's server command is M13's" | `docs/architecture/authoring.md`, `docs/decisions/ADR-032-authoring-is-studios-agent-channel.md` |
| `build_mcp_server` returns an SDK server and runs nothing; the stdio entrypoint is package metadata | `docs/architecture/adapters.md`, `docs/decisions/ADR-010-agent-platform-owns-the-mcp-process.md` |
| The Agent channel process is launched by the MCP client; each channel runs in its own process | `docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md` |
| The Agent channel's window is opened by the SDK, which enters the lifespan inside `run()` | `docs/architecture/lifecycle.md`, `docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md` |
| A window that will not open reports its own failure; every command reports one line of `code`, `category`, `message`, `details` on stderr and exits 1 | `docs/decisions/ADR-030-a-window-reports-its-own-failure.md`, `docs/architecture/packaging.md` |
| `config` is a declared Pydantic model; where the raw mapping comes from "belongs to the installation model" and was not decided | `docs/decisions/ADR-022-configuration-is-a-declaration.md` |
| `serve` reads configuration from stdin; recorded as a consequence, with no alternative weighed | `docs/decisions/ADR-026-the-web-window-is-the-served-applications-lifespan.md`, `docs/architecture/packaging.md` |
| stdin carries configuration "so that a secret reaches the child without a file, an environment variable or an argument vector" | `vibepy_studio/internals/processes.py`, `Processes.start` docstring |
| The Agent channel reports failures as an `isError` text block, and `structuredContent` only for output that conforms to the declared schema | `docs/architecture/errors.md`, `src/vibepy_core/adapters/mcp/server.py` |
| stdio: the client launches the server as a subprocess; the server writes nothing but MCP messages to stdout and may log to stderr | MCP specification 2025-06-18, Transports |
| `async with stdio_server() as (read, write): await server.run(read, write, init_options)`; while serving, fd 0 is the null device and fd 1 is stderr, so handlers and children cannot write to the wire | MCP Python SDK v2, `mcp.server.stdio` |
| `Server.run(read_stream, write_stream, initialization_options)` enters the lifespan; `create_initialization_options()` builds the options | MCP Python SDK v2, `mcp.server.lowlevel.server` |
| `Client(StdioServerParameters(command, args, env, cwd))` launches a server and talks to it; only a safe subset of the parent's environment is inherited by default | MCP Python SDK v2, `mcp.client.stdio`, `mcp.client.client` |
| Codex: `[mcp_servers.<name>]` with `command`, `args`, `env`; `codex mcp add <name> -- <command>` | <https://learn.chatgpt.com/docs/extend/mcp?surface=cli> |
| Claude Code: `.mcp.json` `mcpServers.<name>.{command,args,env}`, `${VAR}` expansion, secrets through `env` | <https://code.claude.com/docs/en/mcp> |
| An MCP server declares its configuration as `environmentVariables[]` (name, required, secret) and `packageArguments[]`, one entry per value | MCP Registry, `server.json` reference |
| Config in the environment; one variable is one independent control, not a grouped blob | <https://12factor.net/config> |
| Environment variables are a last resort for secrets, when mounted files or a secret store are not possible | OWASP Secrets Management Cheat Sheet, §5.1 |
| `BaseSettings` reads one variable per field: "the `_env_prefix` keyword argument on instantiation", "environment variable names are case-insensitive", complex types and sub-models "by treating the environment variable's value as a JSON-encoded string", init kwargs over env over dotenv over secrets over defaults; unrelated variables are not picked up | pydantic-settings documentation, <https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/> |
| `BaseSettings` is a `BaseModel`: `model_validate`, `model_json_schema` and `SecretStr` behave as ADR-022 relies on | pydantic-settings API, `BaseSettings(BaseModel)` |

## Problem

The authoring Tools exist and are channel-neutral (M12), and the framework can build an MCP
server for any App, but nothing runs one. `describe`, `serve` and `invoke` cross the process
boundary; no command opens an App's Agent channel, so no agent platform can be configured to
reach Studio. `docs/architecture/authoring.md` names that command as this milestone's.

Writing it exposes a decision ADR-022 left open. Every command so far hands an App its
configuration on standard input. Over stdio, standard input *is* the transport: the specification
forbids the client to write anything there but MCP messages. The Agent channel therefore cannot
take its configuration the way the other two commands do, and the framework has to decide, for the
first time on the record, how a raw configuration mapping reaches a framework process.

## Decision: configuration reaches a process through the environment

One rule for every framework command: the process reads its App's configuration from its
environment, **one variable per declared field**, named `VIBEPY_<FIELD>` with the field name
upper-cased.

```text
StudioConfig(root: Path, proxy_port: int)   ->   VIBEPY_ROOT=/…   VIBEPY_PROXY_PORT=8080
TodoConfig(root: Path, db_key: SecretStr)   ->   VIBEPY_ROOT=/…   VIBEPY_DB_KEY=…
```

Why this and not the alternatives, recorded in ADR-033:

- **stdin** is unavailable to the one channel this milestone opens, and a rule that holds for two
  commands out of three is not a rule.
- **one JSON object in one variable or one argument** is grouped configuration, which 12-factor
  argues against and no platform or registry schema models; every MCP client and the registry
  declare configuration as individual variables.
- **a file path** reintroduces a file the Hub would have to write and clean up, and the
  platforms already offer `env`.
- **secrets in the environment** is the counter-argument that made stdin the earlier choice.
  OWASP prefers a mounted file or a secret store and names the environment as the fallback when
  neither is possible. A stdio server launched by a client on the developer's machine has
  neither; the MCP ecosystem passes its secrets this way and its clients recommend it. The
  framework follows the platform it integrates with. What Studio already does — handing a child
  only the environment it is entitled to (`child_environment`) — stays.

### Reading rule

The reading is pydantic-settings', not the framework's. pydantic-settings is Pydantic's own
answer to the question ADR-022 left open — where a declared model's values come from — and it
covers the whole of this decision: one variable per field, a prefix given at instantiation,
case-insensitive names (which is also what Windows does), complex fields and sub-models as JSON,
`SecretStr` from a string, and a defined priority of sources.

To use it as documented, an App's configuration model subclasses `BaseSettings`:

```python
class AppDefinition[DepsT, ConfigT: BaseSettings]:
    config: type[ConfigT]

class NoConfig(BaseSettings): ...
```

A window instantiates the declaration rather than validating a mapping against it:

```python
definition.config(_env_prefix="VIBEPY_", **raw)
```

`raw` is what a caller hands the window explicitly — a test literal, a deprecated stdin object —
and by the library's documented priority it stands above the environment, field by field.
A `ValidationError` is `AppConfigInvalidError`, code `config.invalid`, naming every field that
failed, exactly as today; a missing variable is a missing field. No dotenv file and no secrets
directory are configured, so the sources in play are the two above and the model's defaults.

`BaseSettings` is a `BaseModel`, so `model_json_schema` still projects the declaration, `describe`
still writes `config_schema`, and `SecretStr` still masks itself. `inspect_app`'s `config_schema`
therefore lists field names, and the schema a host reads is the list of variables it sets. A
model that declares a validation alias on a field names the variable by that alias, as the
library documents; no framework rule is added for it.

`vibepy-core` depends on `pydantic-settings>=2.15`. It is a Pydantic project, depends on
`pydantic` and `python-dotenv`, and is the library the framework's own configuration model
already comes from; ADR-033 records the dependency.

#### Rendering, on the parent side

The library reads; nothing in it writes. A parent that starts a framework process renders its
held values into variables, and that rule is written once:

```python
def environment_for(config: Mapping[str, object], /) -> dict[str, str]: ...
```

in `vibepy_core/app/config.py`, public through `vibepy_core`: a `str` value verbatim, anything
else `json.dumps`, each under `VIBEPY_<FIELD>` with the field name upper-cased. It is the inverse
of the library's documented decoding and lives beside the contract it inverts.

### Compatibility of the narrowed bound

`ConfigT: BaseModel` becomes `ConfigT: BaseSettings`. Every configuration model in this
repository — `StudioConfig`, `TodoConfig`, `NotesConfig`, `TimerConfig`, `NoConfig`, the test
models — changes its base class, a one-word edit each. No App exists outside this repository, so
no deprecation period is owed for the bound itself (as M12 said of the Hub's rename); the public
API section below states the change.

### What changes for the existing commands

`serve` and `invoke` take the environment as their configuration channel. Their stdin
configuration is **deprecated, not removed**: a `config` object on stdin is still read and handed
to the window as explicit values — above the environment, in the library's order — and logs one
deprecation record when it is non-empty. `invoke`'s stdin keeps its shape,
`{"config": {...}, "input": {...}}`; `input` is per-call data and stays where it is. The
`packaging.md` contract is edited accordingly and names the deprecation; removal is a later
milestone's.

Every launcher in this repository moves to the environment now: `Processes.start`
(`serve`), `invoke_tool` (`invoke`), `scripts/run_studio.py`, and every test that starts a
command. Studio's `child_environment` gains the rendered configuration on top of what it already
passes.

## The command

```text
python -m vibepy_core.mcp <app-name>
```

`src/vibepy_core/mcp.py`, shaped like `serve.py` and `invoke.py`. Run with an App environment's
own interpreter, it opens that App's Agent channel over stdio for as long as the client keeps
the process alive.

```text
argv: app_name
environ: VIBEPY_<FIELD> per declared field
  -> load_app(app_name)
  -> build_mcp_server(definition, lifespan, config={})   # the window reads the environment
  -> async with stdio_server() as (read, write):
         await server.run(read, write, server.create_initialization_options())
```

- `Server.run` enters the App's window; the window is the process, as ADR-017 says of stdio.
- stdout belongs to the SDK. The framework's own records go to stderr at `ERROR`, in the
  `reported` format `serve` already uses; nothing else is configured.
- Failures of the command itself — `package.app_not_declared`, `package.entrypoint_unloadable`,
  `package.entrypoint_invalid` — are one `report` line on stderr and exit 1. A window that
  refuses to open (`config.invalid`, a lifespan that raises) propagates out of `run`, is reported
  the same way, and exits 1; that is ADR-030 applied to this channel.
- There is no `--config` argument and no stdin configuration: this command has one
  configuration channel, the one every command now shares.
- No new failure code. `serve.config_invalid` and `invoke.request_invalid` stay for their stdin
  shapes; the environment has no shape of its own to be invalid, only fields.

`pyproject.toml`'s per-file ignore names `src/vibepy_core/mcp.py` beside `serve.py`: the command
that opens a channel is a channel component. `packages/vibepy-studio/pyproject.toml` depends on
`vibepy-core[web,agent]`, so the command exists in Studio's environment.

Studio's code does not change for this: `AUTHORING_TOOLS` is already declared on `STUDIO_APP`,
and until M14 the consumption Tools appear beside them, as ADR-032 says.

### How a platform reaches Studio

Recorded in `packaging.md` as the command's usage, with both platforms' documents cited:

```toml
# Codex, config.toml
[mcp_servers.vibepy-studio]
command = "<studio environment>/bin/python"
args = ["-m", "vibepy_core.mcp", "vibepy-studio"]
[mcp_servers.vibepy-studio.env]
VIBEPY_ROOT = "/Users/me/.vibepy/studio"
VIBEPY_PROXY_PORT = "8080"
```

```json
// Claude Code, .mcp.json
{ "mcpServers": { "vibepy-studio": {
    "command": "<studio environment>/bin/python",
    "args": ["-m", "vibepy_core.mcp", "vibepy-studio"],
    "env": { "VIBEPY_ROOT": "/Users/me/.vibepy/studio", "VIBEPY_PROXY_PORT": "8080" } } } }
```

## Data flow

```text
agent platform (Codex, Claude Code)
  spawns: python -m vibepy_core.mcp vibepy-studio      env: VIBEPY_ROOT, VIBEPY_PROXY_PORT
    -> load_app, build_mcp_server; the window reads VIBEPY_* as it opens
    -> stdio_server: stdout = wire, fd 1 = stderr for everything else
    -> Server.run enters studio_lifespan (the window)
agent: tools/list  -> to_mcp_tool(...) per declared Tool: inspect_framework, inspect_app,
                      invoke_tool, and the consumption Tools
agent: tools/call inspect_app {"project": "/…/todo-app"}
    -> ToolRuntime.invoke -> authoring handler -> uv run --project … python -m vibepy_core.describe
       (the child's stray output lands on fd 1 = stderr, never on the wire)
    -> AppInspection dumped -> CallToolResult.structuredContent = {"apps": [...], "diagnostic": …}
agent: tools/call inspect_app {"project": "/nowhere"}
    -> AppInspection(diagnostic=authoring.project_not_found) -> structuredContent, isError false:
       an expected failure is data (ADR-029) and conforms to the declared output schema
agent: tools/call inspect_app {}   -> tool.input_invalid -> isError text block (unchanged)
```

Delegation is structural: the adapter's `call_tool` reaches a handler only through
`ToolRuntime.invoke`, and this milestone adds no code between the two. Criterion two is held by
what exists (`docs/architecture/adapters.md`, the channel-neutrality tests) and by the fact that
`vibepy_core.mcp` contains no authoring code.

## Testing

One file per subject; success and failure paths of a subject share its file.

| File | Subject |
| --- | --- |
| `tests/test_app_config.py` | a window over a `BaseSettings` declaration reads `VIBEPY_*`: scalars coerced (`int`, `Path`, `SecretStr`), a sub-model from JSON, an explicit value standing above the environment, a missing field `config.invalid` naming it, an unrelated `VIBEPY_` variable ignored; `environment_for` renders what such a window reads back |
| `tests/test_mcp_command.py` | the command as a real process through `Client(StdioServerParameters(...))`: `vibepy-todo` with `VIBEPY_*` set lists its declared Tools and a `create_todo` call returns `structuredContent` equal to the output model; an unknown App name, and a missing `VIBEPY_ROOT`, each one stderr report and exit 1 |
| `tests/test_serve_command.py`, `tests/test_invoke_command.py` | configuration through the environment; one test each that stdin configuration still works and is logged as deprecated |
| `tests/test_dual_channel.py` | unchanged in assertion; it is in-process |
| `packages/vibepy-studio/tests/test_authoring_over_mcp.py` | Studio as a real stdio process: discovery lists the three authoring Tools; `inspect_app` on `fixtures/todo-app` yields `structuredContent.apps[0].tools` with the fixture's Tool names; `inspect_app` on a directory without `pyproject.toml` yields `structuredContent.diagnostic.code == "authoring.project_not_found"` with `isError` false; `inspect_app` with no arguments yields `isError` true and the `tool.input_invalid` payload |
| `packages/vibepy-studio/tests/test_processes.py`, `test_invoke_tool.py`, `test_runtime.py` | launchers pass configuration in the environment; assertions unchanged |

The stdio tests launch `sys.executable` — this repository's environment holds Studio and the
fixtures — and pass an environment of their own, because the SDK inherits only a safe subset.
The Studio test's authoring calls run `uv` inside the child; `uv` must be on the `PATH` the test
passes, as it is for the M12 tests.

## Compatibility

`environment_for` and `vibepy_core.mcp` are additions to the public API. `ConfigT`'s bound
narrows from `BaseModel` to `BaseSettings`; `NoConfig` follows. Configuration on stdin for
`serve` and `invoke` is deprecated and still honoured. Nothing else is removed. `vibepy-core`
gains `pydantic-settings`; the `[agent]` extra's contents do not change; `vibepy-studio` now
requires it.

## Documentation

- `docs/architecture/packaging.md`: a "Configuration" section owning the variable naming, the
  reading and rendering rules and the deprecation; the `mcp` command beside the other three with
  both platforms' configuration; "all three commands" becomes four
- `docs/architecture/authoring.md`: the sentence deferring the server command to M13 becomes the
  command; "Authoring MCP" section states what exists
- `docs/architecture/lifecycle.md`, `docs/architecture/adapters.md`: the stdio process is
  `vibepy_core.mcp`; the Hub hands configuration through the environment
- `docs/architecture/app-model.md`: `ConfigT: BaseSettings`, and where the values come from —
  one line pointing at packaging
- `docs/decisions/ADR-033-configuration-reaches-a-process-through-the-environment.md`: the
  decision above with its alternatives, the OWASP counter-argument and the new dependency; an
  amendment beneath ADR-026's status noting that its stdin sentence is superseded; ADR-022's
  open question is answered by reference and its `BaseModel` bound is amended beneath its status,
  its body untouched
- `vibepy_studio/internals/processes.py`: the `Processes.start` docstring's stdin rationale is
  replaced, since the mechanism it explains is gone
- this folder is deleted on integration

## Out of scope

Per-channel exposure — the consumption Tools remain visible over MCP (M14). Streamable HTTP.
Removing stdin configuration (a later milestone, after this deprecation). Scrubbing `VIBEPY_*`
from a command's own environment before it spawns children. Dotenv files and a secrets
directory, which the library offers and no host here needs. A `server.json` registry manifest
for Studio.
