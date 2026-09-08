# M10 - Hub Core

## Acceptance criteria

From `docs/roadmap.md`:

- Hub Core can manage package and installation lifecycle independently
- installed Apps can be started, stopped, and queried for status
- Hub lifecycle operations remain separate from App business logic

Capabilities named there: list/install/remove/start/stop/status.

## Sources

| Contract | Source |
| --- | --- |
| the Hub owns the package lifecycle and the Web channel runtime | `docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md` |
| the framework owns composition of a channel's running window | `docs/architecture.md` |
| an app owns its repositories and domain-specific integrations | `docs/architecture.md` |
| internal helpers, services and repositories need not be Tools | `AGENTS.md`, `docs/architecture/tool-model.md` |
| a Tool is `ToolDefinition + ToolHandler`, reaching its resource through `ToolContext` | `docs/architecture/tool-model.md` |
| a Tool's output is revalidated, so it must round-trip through `model_dump`/`model_validate` | `docs/decisions/ADR-007-framework-guarantees-tool-output.md` |
| an App declares itself in the `vibepy.apps` entry point group | `docs/architecture/packaging.md` |
| reading what an environment offers imports nothing; `describe_app` runs in the App's own interpreter | `docs/architecture/packaging.md` |
| an App is installed into an environment of its own, and M10's Hub must install through a mechanism that satisfies it | `docs/architecture/packaging.md` |
| configuration is a declaration the window validates before the lifespan | `docs/decisions/ADR-022-configuration-is-a-declaration.md` |
| where the configuration mapping comes from belongs to the installation model | `docs/decisions/ADR-022-configuration-is-a-declaration.md` |
| the framework defines no secret storage | `docs/decisions/ADR-022-configuration-is-a-declaration.md` |
| an App's own exception is described, not classified; the code table is for framework exceptions | `docs/architecture/errors.md` |
| the NiceGUI adapter registers routes and starts no server | `docs/architecture/adapters.md`, `docs/decisions/ADR-012-nicegui-adapter-registers-routes.md` |
| `ui.run` defaults `reload=True` and `show=True`; `python -m` breaks reload | [NiceGUI ui.run](https://nicegui.io/documentation/run), [zauberzeug/nicegui#1111](https://github.com/zauberzeug/nicegui/issues/1111) |
| `app.on_startup` / `app.on_shutdown` take async functions | [NiceGUI llms.md](https://github.com/zauberzeug/nicegui/blob/v3.13.0/nicegui/llms.md) |
| entry points live in `entry_points.txt`, not in core metadata, and are read with `importlib.metadata` | [entry points spec](https://packaging.python.org/en/latest/specifications/entry-points/) |
| a backend may only append to statically declared entry points | [pyproject.toml spec](https://packaging.python.org/en/latest/specifications/pyproject-toml/) |
| metadata without installing requires the optional `prepare_metadata_for_build_wheel` hook, else a wheel build | [PEP 517](https://peps.python.org/pep-0517/) |
| a workspace root declares `tool.uv.workspace`; every member has its own `pyproject.toml`; members depend on each other through `tool.uv.sources` | [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) |
| splitting one package across distributions means a namespace package, and every such distribution must omit `__init__.py` | [namespace packages](https://packaging.python.org/en/latest/guides/packaging-namespace-packages/) |
| moving a package into a subdirectory breaks installs from a repository URL unless `subdirectory=` is added | [packaging overview](https://packaging.python.org/en/latest/overview/) |
| a core distribution and separately released extensions live in one repository, each building from its own `pyproject.toml` | [Airflow providers](https://airflow.apache.org/docs/apache-airflow-providers/), [apache/airflow#44511](https://github.com/apache/airflow/issues/44511) |
| only a parent can observe its own children: `Popen.poll`, `wait`, `terminate`, `kill`; no documented API observes an arbitrary pid | [subprocess](https://docs.python.org/3/library/subprocess.html) |

## Problem

Nothing installs an App. `docs/architecture/packaging.md` states the contract that each App is
installed into an environment of its own and leaves M10 to install through a mechanism that
satisfies it. Nothing starts one either: the Web channel adapter registers routes and starts no
server, and no command opens a channel's window.

A second gap is that no App exists. `tests/todo_fixture.py` says of itself that it stays a
fixture because an importable sample app presumes the App Package layer, and the package tests
write `entry_points.txt` by hand. Nothing has ever been built or installed, so installing,
starting and stopping cannot be demonstrated against anything.

## Decision recorded separately

One ADR: the Hub is a platform-tier App. It is built with the framework, depends on it, and the
framework never depends on the Hub. Shipping it as its own distribution is that decision's
consequence, not a second decision. Everything below the line `AGENTS.md` draws — the choice of
`uv`, the shape of the state file, the port policy — belongs to commit messages.

## Scope

Three concerns and one new framework command.

| Concern | Knows | Does not know |
| --- | --- | --- |
| package sources | registered local folders and the installable candidates inside them | what an App declares; a schema needs an import |
| installations | which environment holds which App, and the configuration values held for it | whether it is running |
| runtime | the child processes this Hub window started, and their ports | processes the Hub did not start |

The Hub is an App: `AppDefinition` with eight Tools, one lifespan, and a configuration
declaration. Its Pages are M11's. Its work — calling `uv`, reading a folder, holding child
processes, reading and writing its state file — is domain internals, reached only through
`ctx.dependencies`, exactly where `docs/architecture.md` places an app's repositories and
integrations. There is no facade class and no Tool over those internals.

## Package layout

The repository becomes a uv workspace. One `pyproject.toml` defines one distribution, so the
split requires one project file per distribution.

Two shapes are rejected on published guidance. Shipping the Hub as `vibepy.hub` from a second
distribution would make `vibepy` a namespace package, and the guide requires that every
distribution sharing a namespace omit `__init__.py` — one that does not breaks the import of
every other. `src/vibepy/__init__.py` exists, so a separate top-level package avoids the
failure rather than managing it. Moving the framework into a subdirectory is rejected for the
reason the same guidance gives: installing from a repository URL then needs `subdirectory=`,
and existing workflows break. The framework stays at the root, which is also the workspace
root.

The shape has precedent. Airflow keeps its core and its separately released providers in one
repository, each provider a directory that builds with standard tooling from its own
`pyproject.toml`, and discovers an installed provider rather than importing a list of them.

```text
pyproject.toml              vibepy-framework, and [tool.uv.workspace] members
src/vibepy/serve.py         new: the Web channel command
hub/pyproject.toml          vibepy-hub, depending on vibepy-framework
hub/src/vibepy_hub/
  entry.py                  AppDefinition, lifespan, AppEntrypoint
  tools.py                  the eight declarations and their handlers
  state.py                  the state file: sources and configuration values
  sources.py                reading a registered folder
  installer.py              uv
  processes.py              child processes and port selection
samples/todo/pyproject.toml  vibepy-todo, declaring itself in vibepy.apps
samples/todo/src/todo_app/   the Todo App, moved out of tests/todo_fixture.py
```

`tests/todo_fixture.py` is removed and its importers use `todo_app`, so one Todo exists rather
than two.

## Public API

`vibepy_hub` publishes an `AppEntrypoint` and nothing else. Its Tools are its API.

Its configuration declares one field: the root under which it keeps its state file and the
environments it creates. A test supplies a temporary directory there, which is why the root is
declared rather than assumed.

| Tool | Input | Output |
| --- | --- | --- |
| `register_package_source` | a folder path | the registered source and its candidates |
| `remove_package_source` | a folder path | the remaining sources |
| `list_apps` | empty model | one row per App: identity, state, url, configured, diagnostic |
| `install_app` | a candidate | the installation, or a diagnostic |
| `configure_app` | an app name and a mapping | the values held, secret fields excluded |
| `start_app` | an app name and the secret values required | the url, or a diagnostic |
| `stop_app` | an app name | the app's state |
| `remove_app` | an app name | the remaining installations |

`status` from the roadmap's list is `list_apps`: every row carries its state, so a per-App
status Tool would answer a question the list already answers. `configure_app` is the weakest
name in the set; it is kept because configuration is a declared object of this domain and
per-field setters would be the `set_field` pattern `docs/architecture/tool-model.md` rejects.

`install_app` and `list_apps` read a candidate's name and version from `pyproject.toml` and
report whether `vibepy.apps` is statically declared. That reading is a hint: entry points are
not core metadata, and a backend may add them, so a folder without a visible declaration is
still offered for installation. What an App declares is read after installation, by running
`python -m vibepy.describe` with the new environment's interpreter.

### The Web channel command

```text
python -m vibepy.serve <app-name> --port <n>
```

Configuration arrives as one JSON object on standard input, so a secret reaches the child
without a file, an environment variable or an argument vector. The module registers
`app.on_startup` and `app.on_shutdown` around an `AsyncExitStack` that enters
`page_runtime_for` and registers the App's routes, then calls `ui.run` with `reload=False`,
`show=False` and the given port. It builds no FastAPI application and calls no ASGI server:
NiceGUI owns the server, and its own hooks are the lifecycle mechanism.

This is a framework command because composing a channel's running window is framework
ownership. The Hub runs it; it does not assemble it.

## Data flow

```text
register  folder                -> state file
list      state file + envs     -> rows            (discover_apps per environment)
install   candidate             -> uv venv, uv pip install, python -m vibepy.describe
configure app + mapping         -> state file      (secret fields dropped)
start     app + secrets         -> free port, child process, stdin JSON
stop      app                   -> terminate, wait, kill
remove    app                   -> stop, delete environment, drop records
```

Installed Apps are not listed from a copy. Each App has an environment of its own, and
`discover_apps(path=…)` reads an environment's metadata without importing it, so the file
system is the truth about what is installed and the state file holds only what the framework
does not answer: registered folders and configuration values.

`start_app` reports that an App declaring no Pages has no Web channel to start. Configuration
is not validated by the Hub; the window validates it and raises `config.invalid`.

`remove_app` deletes the environment. An App's data lives where its own configuration points,
outside that environment, so it survives.

## Errors

No framework code is added, and the Hub defines no code table. `docs/architecture/errors.md`
already settles this: the code table is for framework exceptions, and an App's own exception is
described rather than classified.

- an expected, actionable outcome is a diagnostic in a Tool's output model: a folder that is
  not installable, `uv` missing or failing, a port already taken, an entrypoint that cannot be
  loaded, an App with no Web channel
- a framework code arriving from an App's environment — `package.entrypoint_unloadable` and
  friends, written to standard error by `python -m vibepy.describe` — is carried as data in
  that diagnostic
- a programming error propagates as raised

Because output models are revalidated, a diagnostic is plain fields: `code`, `message`,
`details`. No live object and no exception instance travels in an output.

## Testing

Contract tests use real `uv` and a real distribution.

- a registered folder lists `samples/todo` as an installable candidate
- installing it creates an environment of its own, and the installation reports what the App
  declares, read through `python -m vibepy.describe`
- an installed App starts, answers over HTTP on the reported url, stops, and reports its state
  at each step
- routes registered during startup are served — the ASGI contract completes startup before
  requests, and this pins it
- removing an installed App deletes its environment and leaves data written outside it
- `uv` absent is a diagnostic, not a crash
- an App declaring no Pages installs and reports that there is nothing to start

No fake installer stands in for `uv`. What this milestone claims is that an App is installed
into an environment of its own and started with that environment's interpreter, and a
substitute would test the substitute.

## Compatibility

`vibepy`'s public API gains `vibepy.serve` and changes nothing else. `vibepy-framework` ships
the same modules it ships today; `vibepy-hub` and `vibepy-todo` are new distributions. An
installed App's environment contains the framework and the App, and never the Hub.

## Documentation

- a new ADR: the Hub is a platform-tier App
- `docs/architecture/packaging.md`: the installation model is no longer only a contract — record
  what the Hub installs through
- `docs/architecture/lifecycle.md`: the Web channel's window is opened by a named command; align
  its `uninstall` with the roadmap's `remove`
- `docs/architecture.md`: the framework's ownership list gains the Web channel command
- `docs/hub-ui-mockup.html` is not updated here; M11 owns it

## Out of scope

- a proxy and a stable address per App. Each running App has a port of its own because each
  channel is its own process; one public address is the proxy's job and belongs with the UI
- unattended restart, and therefore stored secrets. The Hub holds no secret, so an App that
  requires one needs it supplied at each start. `keyring` is the candidate when a real
  requirement exists
- update and upgrade
- the Hub's own Agent channel. A channel exists when a client launches it, and nothing does
- dependency, process and filesystem isolation hardening: M17
- query/command classification, side-effect markers, permissions and exposure policy on the
  Hub's Tools: `docs/architecture/tool-model.md` says not before a milestone requires them
