# M8-M9 Configuration and the App Package: Design

M8 and M9 are implemented as one cycle. The owner took that decision for two reasons. M9 must
resolve an entrypoint, and an entrypoint is exactly where a definition, a lifespan and a
configuration meet, so implementing M8 alone would settle the composition contract once and
risk re-cutting it in M9. And the two milestones ask for the same machine: read a declaration,
validate a mapping against it, report what failed with a stable code.

`docs/roadmap.md` is not edited. Both entries' acceptance criteria are quoted below and are
the tests. M8's criteria name `AppRuntime`, which ADR-020 removed; they are read as naming a
channel's running window, which is what owns application-scoped dependencies now.

## Acceptance criteria

From M8:

- app configuration is validated before normal runtime use
- application-scoped dependencies are shared within one running window
- independent running windows remain isolated by default

From M9:

- valid packages can be inspected and validated deterministically
- invalid package metadata produces structured diagnostics
- a valid package can resolve and load its declared AppDefinition

And:

- `make lint typecheck test` passes

## Sources

| Contract | Source |
| --- | --- |
| a declaration holds no resource factory; an entrypoint pairs a definition with a lifespan and is the composition root | `docs/decisions/ADR-021-a-declaration-holds-no-resource-factory.md` |
| what an App may declare about its host — configuration schema, secret names — is a real declaration and is M8 territory | `docs/decisions/ADR-021-a-declaration-holds-no-resource-factory.md` |
| the executable entrypoint belongs to the App Package layer; what the framework supplies for stdio is a command the platform executes, which is package metadata | `docs/decisions/ADR-010-agent-platform-owns-the-mcp-process.md` |
| each channel runs in its own OS process; an app-scoped resource must be share-nothing | `docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md` |
| the channel host owns the runtime lifecycle; a runtime exists only inside a window | `docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md` |
| acquisition and release are one async context manager | `docs/decisions/ADR-018-app-scoped-resource-is-an-async-context-manager.md` |
| the resource reaches a handler only through ToolContext, typed by the app | `docs/decisions/ADR-013-dependencies-reach-handlers-through-tool-context.md` |
| a framework error carries a stable code; a retired code is never reused | `docs/architecture/errors.md`, `docs/decisions/ADR-019-framework-errors-carry-stable-codes.md` |
| runtime lifecycle and package lifecycle are separate; `Package -> install -> configure -> open a channel` | `docs/decisions/ADR-006-runtime-vs-package-lifecycle.md`, `docs/architecture/lifecycle.md` |
| per-invocation resource scope is undecided and M8 owns the decision | `docs/architecture/app-model.md` |
| entry points live in `entry_points.txt` inside `*.dist-info`; group names match `^\w+(\.\w+)*$`; a value is `importable.module:object.attr`; "consumers defining a new group should use names starting with a PyPI name owned by the consumer project, followed by `.`" is advice, not a rule | <https://packaging.python.org/en/latest/specifications/entry-points/> |
| `.name`, `.group`, `.value`, `.module`, `.attr` are read from package metadata; `.load()` "resolves and loads the value" and imports; the selectable interface exists from Python 3.10 and is not provisional | <https://docs.python.org/3/library/importlib.metadata.html> |
| `distributions(**kwargs)` accepts a `DistributionFinder.Context` or the keyword arguments to build one; "The `path` attribute defaults to `sys.path` and is the set of import paths to be considered in the search" | <https://docs.python.org/3/library/importlib.metadata.html>, <https://github.com/python/cpython/blob/main/Doc/library/importlib.metadata.rst> |
| `Distribution.files` returns `PackagePath` instances, does not require importing the package, and returns `None` when the installation database's file records are missing | <https://docs.python.org/3/library/importlib.metadata.html> |
| `importlib.resources.files(anchor)` resolves resources from a package that must be importable, and works for packages imported from a zip | <https://docs.python.org/3/library/importlib.resources.html> |
| pytest discovers third-party plugins through the `pytest11` entry point group, declared as `[project.entry-points.pytest11]`, loaded at startup unless `PYTEST_DISABLE_PLUGIN_AUTOLOAD` is set | <https://docs.pytest.org/en/stable/how-to/writing_plugins.html> |
| `PluginManager.load_setuptools_entrypoints(group)` "loads the associated modules into the current process" and registers them | <https://pluggy.readthedocs.io/en/stable/api_reference.html> |
| `uv tool install` creates a virtual environment per tool in the uv tools directory, and exposes "all console entry points, script entry points, and binary scripts provided by a Python package" — but not those of its dependencies | <https://docs.astral.sh/uv/concepts/tools/> |
| a tool environment is persistent — "When installing a tool with `uv tool install`, a virtual environment is created in the uv tools directory" and "The environment will not be removed unless the tool is uninstalled" — whereas `uvx` uses a cached environment "treated as disposable"; "Tool environments are _not_ intended to be mutated directly" | <https://github.com/astral-sh/uv/blob/main/docs/concepts/tools.md>, <https://docs.astral.sh/uv/concepts/tools/> |
| the tools directory defaults to `~/.local/share/uv/tools` and is queried with `uv tool dir`; executables live in a separate directory queried with `uv tool dir --bin` | <https://docs.astral.sh/uv/reference/storage/> |
| verified on uv 0.12.1: each installed tool is a complete virtual environment at `<tools dir>/<tool>/`, with its own `bin/`, its own `lib/pythonX.Y/site-packages/` carrying that tool's `.dist-info`, and `pyvenv.cfg` recording `include-system-site-packages = false` | local inspection; the layout is what `distributions(path=...)` is pointed at |
| core metadata has no field declaring a conflict with another distribution; `Obsoletes-Dist` means "the two projects should not be installed at the same time" and is rarely used because "popular installation tools ignore them completely" | <https://packaging.python.org/en/latest/specifications/core-metadata/> |
| `packages_distributions()` maps each top-level import name to a *list* of distributions, so one import name provided by two distributions is representable and observable | <https://docs.python.org/3/library/importlib.metadata.html> |

## Problem

**An App cannot state what it needs.** `AppDefinition` declares identity, Tools and Pages. A
database path or an API endpoint is read inside the lifespan, which is a callable and not a
readable declaration. Nothing can answer "what does this App require of its host" without
running it, and a missing value fails inside the App's own code as whatever exception that code
raises, outside the error model M7 established.

**A package cannot be found.** Nothing connects an installed distribution to the App inside it.
`lifecycle.md` names `Package -> install -> configure -> open a channel` and ADR-010 defers the
executable entrypoint to this layer, but no document owns it and no code implements it.

**The Host cannot import the App.** `uv tool install` puts each tool in its own virtual
environment, and ADR-017 puts each channel in its own process. A Host that imported an App to
inspect it would break both. This is where pluggy's model does not transfer: pytest loads
plugins into its own process because a plugin is an extension of pytest, whereas an installed
App is a separate program. The declaration mechanism transfers; the loading mechanism does not.

## Governing principle

> What can be read without running is read from metadata. What requires an import happens in
> the App's own environment.

The framework offers one operation on each side of that line and nothing that spans it.

This is not a convenience. It is the dependency dimension of ADR-017, and it is what makes
installing an App unable to disturb anything else:

- an App is installed into an environment of its own, so two Apps never resolve one dependency
  set and never share a top-level import name
- the Host reads metadata and never imports an App, so no App dependency enters the Host's
  environment and the Host's own dependencies constrain no App
- loading an App happens in that App's interpreter, so what the framework is called in the
  Host's environment is irrelevant to every App

Without the invariant, every installed App is a possible version conflict and every top-level
import name is a possible collision — including the framework's own, which an unrelated
distribution on PyPI already claims. With it, the only remaining conflict is one an App declares
inside its own dependency set, which is that App's to resolve and is not a framework concern.
No name is changed and no collision detector is added: neither would remove the class of
failure, and the invariant does.

The three parts are not guaranteed in the same place, and the difference is stated rather than
blurred. The second and third are guarantees this framework makes and this milestone tests: it
publishes no operation that imports an App into its caller's process, and description runs under
the App's own interpreter. The first is a requirement on the installation model, which Python
packaging cannot enforce — nothing stops two Apps being installed into one environment by hand.
`uv tool install` satisfies it by construction, M10's Hub must install through such a mechanism,
and M17 owns hardening it. This is the same division ADR-017 already made: the framework states
the contract, the host implements it.

## Configuration is a declaration

`AppDefinition` gains a configuration model and a second type parameter:

```python
@dataclass(frozen=True)
class AppDefinition[DepsT, ConfigT: BaseModel]:
    app_id: str
    name: str
    version: str
    config: type[ConfigT]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
```

The field is a type, so it is readable: `definition.config.model_json_schema()` answers what the
App requires without acquiring anything. `DepsT` remains what it was — a type the framework
carries and never inspects — and `ConfigT` is its opposite: a type the framework validates
against and projects.

The declaration is required. An App needing no configuration declares the framework's own empty
model, `NoConfig`, rather than `None`. One declaration always present means one validation path
always taken: there is no branch in which configuration is absent, and therefore no second
behaviour to specify or test.

Secrets are separated by type, not by storage. A secret-bearing field is declared with Pydantic's
`SecretStr`, whose representation hides its value, so a configuration object may be logged and a
schema published without disclosing anything. Where secret values come from is the Hub's
question and is not answered here.

## Validation precedes the window

A lifespan receives its App's validated configuration:

```python
type Lifespan[DepsT, ConfigT] = Callable[[ConfigT], AbstractAsyncContextManager[DepsT]]
```

Both window functions take the raw mapping as a keyword-only argument, validate it against the
declared model, and only then enter the lifespan:

```python
async with tool_runtime_for(definition, lifespan, config=raw) as tools: ...
```

An invalid mapping raises `AppConfigInvalidError` and the lifespan is never called, so no
resource is acquired for a window that cannot run. This is the whole of M8's first criterion:
validation is not a step an App may forget, because the App never sees the raw mapping.

Where the raw mapping comes from is deliberately not decided. The framework accepts a
`Mapping[str, object]` from its caller. A file format, an environment-variable convention and a
secret store are all questions the installation model owns, and that model does not exist yet.

## The entrypoint is a value

A package points at the composition root, which ADR-021 defines as the place a definition and a
lifespan meet:

```python
@dataclass(frozen=True)
class AppEntrypoint[DepsT, ConfigT: BaseModel]:
    definition: AppDefinition[DepsT, ConfigT]
    lifespan: Lifespan[DepsT, ConfigT]
```

This does not weaken ADR-021. The declaration still holds no factory; the entrypoint is a
separate object, is not a declaration, and exists precisely to hold the pairing that a
declaration must not.

An App declares it in its own `pyproject.toml`:

```toml
[project.entry-points."vibepy.apps"]
todo = "todo_app.entry:app"
```

No manifest file is invented. The group is standard metadata, written to `entry_points.txt` in
the distribution's `*.dist-info` at build time, and pytest's `pytest11` is the same pattern in
the same place.

The group name claims no PyPI name and creates no dependency on one. PyPA's advice to prefix a
group with a name the consumer owns is collision avoidance, and `pytest11` shows how loosely the
ecosystem follows it. A group name is read as a string out of metadata and imports nothing, so
two projects using one group name would at worst list each other's entry points — which the
loader rejects, because the resolved object would not be an `AppEntrypoint`. Group names admit no
hyphen, which is the only hard rule here, and `vibepy.apps` satisfies it.

One group is defined. `vibepy.skills` and `vibepy.mcp_servers` are the same mechanism applied to
other capability kinds and belong to M19; leaving them undefined costs nothing, because a group
is added by declaring it.

## Inspection and loading are two operations

```text
discover_apps()   metadata only, no import   ->  AppRef
describe_app()    imports, in this process   ->  AppDescription
```

`discover_apps` selects the `vibepy.apps` group and returns one `AppRef` per entry point, built
from `.name`, `.value`, `.module`, `.attr` and the providing distribution's name and version.
Nothing is imported. An optional `path` is forwarded to `DistributionFinder.Context`, so an
environment other than the running interpreter's can be enumerated. That parameter is what makes
the invariant implementable: a Host inspects an App's environment without installing anything
into its own, and without importing anything from the App's.

`describe_app` loads one reference and projects it. `.load()` imports, so this is the operation
that must run inside the App's own environment. It rejects two distinguishable failures and
succeeds otherwise, which is M9's second criterion:

| Failure | Code |
| --- | --- |
| the module does not import, or the attribute does not exist | `package.entrypoint_unloadable` |
| the resolved object is not an `AppEntrypoint` | `package.entrypoint_invalid` |

There is no third code for an App that is not there, because no operation asks for one by name:
discovery returns what an environment declares, and an environment declaring nothing is not a
failure. M10 introduces such a lookup if a Host needs one.

The description is a value and carries no type parameters, so an unparameterized entrypoint
never reaches the public API:

```python
@dataclass(frozen=True)
class AppDescription:
    app_id: str
    name: str
    version: str
    config_schema: Mapping[str, object]
    tools: Sequence[ToolDescription]
    pages: Sequence[PageDescription]
```

`AppEntrypoint.describe()` produces it, and the loader narrows the loaded object with
`isinstance(loaded, AppEntrypoint)` — the concrete class rather than a structural Protocol, so
an unrelated object carrying a `describe` attribute is rejected rather than called. `Any` and
`cast` appear nowhere: the loaded value is annotated `object`, and the generic parameters stay
inside the App's own module where they are known statically.

Determinism is a property of the result, which M9's first criterion requires: references are
ordered by entry point name, and diagnostics by the order the references were visited.

## Self-description is a command

A Host cannot import an App, so the framework provides the command that describes one from
inside its environment:

```bash
<app environment>/bin/python -m vibepy.describe
```

It discovers its own environment's `vibepy.apps`, describes each one, and writes the descriptions
to standard output as JSON. The App declares nothing to obtain this: the framework is already a
dependency in that environment. Nor does it depend on the executable directory, which matters for
a `uv tool` environment, whose exposed scripts are the tool package's own and not its
dependencies' — so the interpreter path is the only thing a Host needs, and it needs no framework
of its own.

The command reads configuration schemas; it does not read configuration values and does not
enter a lifespan. Describing an App runs its module's import, and nothing else.

## Package layout

```text
src/vibepy/
  app/
    model.py          AppDefinition, NoConfig
    composition.py    Lifespan, tool_runtime_for, page_runtime_for, config validation
    entrypoint.py     AppEntrypoint, AppDescription, ToolDescription, PageDescription
    package.py        AppRef, discover_apps, describe_app
  describe.py         the python -m entrypoint
  errors.py           four exceptions added
  tool/, page/, adapters/   unchanged but for the new type parameter
```

## Public API

```python
class NoConfig(BaseModel):
    """An App that requires nothing of its host."""


@dataclass(frozen=True)
class AppDefinition[DepsT, ConfigT: BaseModel]:
    app_id: str
    name: str
    version: str
    config: type[ConfigT]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]


type Lifespan[DepsT, ConfigT] = Callable[[ConfigT], AbstractAsyncContextManager[DepsT]]


def tool_runtime_for[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> AbstractAsyncContextManager[ToolRuntime[DepsT]]: ...


def page_runtime_for[DepsT, ConfigT: BaseModel](
    definition: AppDefinition[DepsT, ConfigT],
    lifespan: Lifespan[DepsT, ConfigT],
    /,
    *,
    config: Mapping[str, object],
) -> AbstractAsyncContextManager[PageRuntime]: ...


@dataclass(frozen=True)
class AppEntrypoint[DepsT, ConfigT: BaseModel]:
    definition: AppDefinition[DepsT, ConfigT]
    lifespan: Lifespan[DepsT, ConfigT]

    def describe(self) -> AppDescription: ...


@dataclass(frozen=True)
class ToolDescription:
    name: str
    description: str
    input_schema: Mapping[str, object]
    output_schema: Mapping[str, object]


@dataclass(frozen=True)
class PageDescription:
    name: str
    route: str
    title: str


@dataclass(frozen=True)
class AppDescription:
    app_id: str
    name: str
    version: str
    config_schema: Mapping[str, object]
    tools: Sequence[ToolDescription]
    pages: Sequence[PageDescription]


@dataclass(frozen=True)
class AppRef:
    app_name: str
    distribution: str
    distribution_version: str
    module: str
    attr: str


def discover_apps(*, path: Sequence[Path] | None = None) -> Sequence[AppRef]: ...


def describe_app(ref: AppRef, /) -> AppDescription: ...
```

`build_mcp_server` builds a window, so it takes the same keyword argument:
`build_mcp_server(definition, lifespan, config=raw)` replaces the two-argument form.
`register_pages` is unchanged, because it reads declarations only.

## Data flow

```text
Inspection, in the Host's process
  distributions(path=...) ──▶ entry_points ──▶ AppRef            no import

Description, in the App's process
  AppRef ──load()──▶ AppEntrypoint ──describe()──▶ AppDescription ──▶ JSON on stdout

Execution, in the App's process
  raw mapping ──validate(definition.config)──▶ ConfigT
                                                 │
                                    lifespan(config) ──▶ DepsT ──▶ ToolRuntime ──▶ ToolContext
```

## Errors

Three codes are added. None is retired.

| Code | Category | Exception |
| --- | --- | --- |
| `config.invalid` | caller | `AppConfigInvalidError` |
| `package.entrypoint_unloadable` | declaration | `AppEntrypointUnloadableError` |
| `package.entrypoint_invalid` | declaration | `AppEntrypointInvalidError` |

`config.invalid` is a caller failure: the same App with a corrected mapping succeeds. Its
`details` name the App and the rejected field paths, so a Host can point at the fields rather
than reproduce a sentence. The two entrypoint failures are declaration failures, raised while
reading what a package declared, which is where `page.route_invalid` already sits.

No category is added. The existing three remain closed and exhaustive.

## Testing

| File | Change |
| --- | --- |
| `tests/test_app_config.py` | new. A valid mapping reaches the lifespan as a validated model; an invalid one raises `AppConfigInvalidError` and the lifespan is never entered, proven by a flag the fixture sets on entry; `NoConfig` requires no mapping content; a `SecretStr` field does not appear in the object's representation; two windows over one definition with different configurations do not observe each other |
| `tests/test_app_composition.py` | rewired for the new signature. Its existing claims — the window's two sides, what a Tool receives, isolation between two compositions, release ordering on failure — are unchanged and cover M8's second and third criteria |
| `tests/test_app_package.py` | new. `discover_apps` finds an App from a `dist-info` fixture written into a temporary directory and passed as `path`, imports nothing, and orders its results; `describe_app` returns a description whose schemas match the declarations; both failure codes are provoked and distinguished, including an entry point resolving to an object that merely carries a `describe` attribute; a distribution with no `vibepy.apps` group yields nothing |
| `tests/test_app_isolation.py` | new. The invariant is proven, not assumed: `discover_apps` over a `path` fixture leaves the fixture's module absent from `sys.modules`, so inspection imports nothing; and a description obtained through the subprocess command holds for an environment the test process never imported |
| `tests/test_describe_command.py` | new. `python -m vibepy.describe` runs as a subprocess against an environment containing the Todo fixture and writes parseable JSON carrying the App's identity, configuration schema, Tool schemas and Page routes |
| `tests/test_mcp_adapter.py`, `tests/test_nicegui_adapter.py`, `tests/test_dual_channel.py`, `tests/test_execution_semantics.py` | fixture rewiring only. No claim changes; the two constitutional tests keep their barrier and their divergence proof |
| `tests/test_errors.py` | catalogue grows by three |
| `tests/test_package.py` | `__all__` |
| `tests/todo_fixture.py` | declares a configuration model and a lifespan that takes it; the Todo App's store path becomes configuration rather than a literal |

The `dist-info` fixture is written by the test rather than installed, so no test builds a wheel
or reaches the network, and `distributions(path=...)` is exercised exactly as a Hub would use it.

## Compatibility

The public API changes without a deprecation path: `AppDefinition` gains a required field and a
type parameter, `Lifespan` gains a parameter, and both window functions gain a required keyword
argument. The framework is pre-release and has no consumer outside this repository, which is the
ground ADR-016 and ADR-020 already took.

## Documentation

Two ADRs are written.

| ADR | Content |
| --- | --- |
| ADR-022 configuration is a declaration validated before the window opens | why configuration is a readable type on the declaration rather than a factory's private business, why the declaration is required rather than optional, why validation belongs to the window and not to the App, why the raw mapping's origin is left to the installation model, and that per-invocation resource scope is not introduced |
| ADR-023 a package points at its App through a Python entry point | why no manifest file is invented, why `vibepy.apps` claims no distribution name, why inspection and loading are separated, why pluggy's in-process loading does not transfer, and why one group is defined rather than three |

ADR-022 closes the question `docs/architecture/app-model.md` left open: no per-invocation
resource scope is introduced, because no milestone requires one and a request-scoped dependency
would be a second dependency mechanism beside `ToolContext`.

Three architecture documents change. `app-model.md` takes the configuration declaration and the
entrypoint; `runtime.md` records that a window validates configuration before acquiring
anything; `lifecycle.md`'s `configure` step gains the sentence that says who validates. A new
document, `docs/architecture/packaging.md`, owns discovery, description and the entry point
groups, because no existing document owns packaging. `docs/architecture.md` gains its link.

`AGENTS.md` gains two invariants: an App declares what it requires of its host, and a channel
validates that declaration before opening a window; and an App is installed into an environment
of its own, which the Host reads without importing and loads through that environment's own
interpreter.

ADR-023 records the second as the dependency dimension of ADR-017, and why the framework neither
renames itself nor detects collisions to obtain it.

## Out of scope

- a configuration file format, an environment-variable convention, and where secret values are
  stored. The installation model owns these
- scanning `uv tool` environments, enumerating installed Apps across environments, and
  registering capabilities with a Host. That is M10's control plane
- enforcing environment isolation. M17 owns dependency, process, filesystem and resource
  isolation; this milestone fixes the contract those mechanisms must satisfy, so that no Hub
  design may put two Apps in one environment
- blocking or disabling discovery. pytest shows that automatic discovery eventually needs an
  off switch, but the policy belongs to the Host that discovers
- `vibepy.skills` and `vibepy.mcp_servers`, and reading non-Python payloads out of an installed
  distribution. M19 owns capability declaration
- per-invocation resource scope. ADR-022 records the decision not to introduce one
- validating an App's conformance beyond resolving and describing it. M16 owns conformance
- exposing description through MCP. M12 and M13 own the authoring surface
