# Packaging Architecture

How an installed distribution says which App it contains, and how a reader learns what that App
is without importing it.

`docs/architecture/app-model.md` owns the declaration and the running window; this document owns
everything between a distribution and that declaration.

## The declaration

An App declares itself in the `vibepy.apps` entry point group. In its own `pyproject.toml`:

```toml
[project.entry-points."vibepy.apps"]
todo = "todo_app.entry:APP"
```

The name on the left is the App's name inside its distribution. The value on the right is a
`module:attr` reference to an `AppEntrypoint`. A build writes both to `entry_points.txt` inside
the distribution's `*.dist-info`, so a reader finds them without executing anything. See
`docs/decisions/ADR-023-a-package-points-at-its-app-through-an-entry-point.md`.

## The composition root

`AppEntrypoint` is what a package names: one definition and the lifespan that resources it.
ADR-021 keeps the factory out of the declaration, so the pairing needs an object of its own.

```python
@dataclass(frozen=True)
class AppEntrypoint[DepsT, ConfigT: BaseModel]:
    definition: AppDefinition[DepsT, ConfigT]
    lifespan: Lifespan[DepsT, ConfigT]

    def describe(self) -> AppDescription: ...
```

`describe()` projects the declarations and nothing else. It reads no configuration and enters no
lifespan, so describing an App acquires nothing.

## Inspection and loading

> What can be read without running is read from metadata. What requires an import happens in the
> App's own environment.

Two operations, one on each side of that line, and nothing that spans it.

```python
APP_GROUP = "vibepy.apps"

@dataclass(frozen=True)
class AppRef:
    app_name: str
    distribution: str
    distribution_version: str
    module: str
    attr: str

def discover_apps(*, path: Sequence[Path] | None = None) -> tuple[AppRef, ...]: ...

def describe_app(ref: AppRef, /) -> AppDescription: ...
```

`discover_apps` reads metadata. An `AppRef` carries where an App is declared and no imported
object, and `path` points the search at an environment other than the running interpreter's.
Results are ordered by `(app_name, distribution)`, so a reader gets the same list twice.

`describe_app` imports. It resolves the reference, checks that what it found is an
`AppEntrypoint`, and returns that entrypoint's description. Because it imports, it belongs in
the App's environment and not in a Host's.

`AppDescription` is what crosses a process boundary: `app_id`, `name`, `version`,
`config_schema`, and a `ToolDescription` and `PageDescription` per declaration. It carries no
type parameter and every schema is typed as the JSON it becomes there.

## The self-description command

```text
python -m vibepy_core.describe
```

Run with an App environment's own interpreter, it writes a JSON array to standard output — one
object per App declared in that environment. A failure writes the framework's code and message
to standard error and exits 1.

This is how a Host reads an App it must not import. The Host runs the command with the App
environment's interpreter and parses the result; the import happens on the far side of a process
boundary, where the App's dependencies belong.

## Running a channel

```text
python -m vibepy_core.serve <app-name> --port <n>
```

Run with an App environment's own interpreter, it opens that App's Web channel: the App's window
is the served application's own lifespan, and one JSON object of configuration is read from
standard input. A configuration therefore reaches a running App without a file, an environment
variable or an argument vector.

The window is the lifespan and not a startup hook because ASGI already decides what a window
that cannot open means: a server that sees `lifespan.startup.failed` logs the message and exits
(<https://asgi.readthedocs.io/en/latest/specs/lifespan.html>). An App whose configuration its
window refuses therefore has no server, rather than a server answering for an App that never
opened.

Both commands exist for one reason. Reading a declaration and running one both import, and an
import belongs on the App's side of a process boundary.

## What an environment holds

An App's environment holds `vibepy-core`, the extras for the channels that App offers, and the
App. `vibepy-core` itself declares no channel: `vibepy-core[web]` carries the Web technology and
`vibepy-core[agent]` carries MCP, so an App declaring no Pages installs no Web technology. See
`docs/decisions/ADR-025-the-framework-implements-channel-neutrality-and-delegates-the-rest.md`.

What a channel's SDK requires of itself is that SDK's own declaration and is not narrowed here:
MCP requires uvicorn, so an environment offering the Agent channel holds uvicorn whether or not
it offers the Web one.

## The isolation invariant

Three statements, and they are not guaranteed in the same place.

| Statement | Enforced by |
| --- | --- |
| the Host never imports an App | the framework: no published operation imports an App into its caller, and `tests/test_app_isolation.py` proves discovery leaves `sys.modules` untouched |
| loading happens in the App's own interpreter | the framework: `describe_app` is reached across a process boundary through `python -m vibepy_core.describe` |
| an App is installed into an environment of its own | the installation model. The Hub creates one environment per App and installs into it; Python packaging cannot enforce it |

The third is a contract, not a guarantee, and the difference is stated rather than blurred:
nothing in packaging stops two Apps being installed into one environment by hand. The Hub keeps
the contract by construction — `uv venv` then `uv pip install` per App — and M17 owns hardening
it. This is the division ADR-017 already made: the framework states the contract, the host
implements it.

What the invariant buys is that no App's dependencies constrain another's, and that no top-level
import name can collide between two Apps or between an App and the framework. That is why
neither a renamed import package nor a collision detector is part of this design: neither
removes the class of failure, and environment isolation does.

## Invariants

- an App declares itself in metadata. The framework defines no manifest format
- reading what an environment offers imports nothing
- the framework publishes no operation that imports an App into its caller's process
