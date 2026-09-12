# ADR-037: An App declaration validates itself at construction

Status: Accepted; supersedes ADR-012's statement that the adapter validates route format and
uniqueness

Amendment, appended: the "Rejected: pyright in Studio's dependencies" entry below has been
reversed. The reason given there — that the checker belongs to the project being checked, at
the project's version — did not hold: a project has no pyright of its own, and Studio was
choosing the version anyway, through an unpinned `--with` that resolved the newest pyright at
every run. That put a dependency outside the lockfile and made a verdict depend on the day,
against the acceptance criterion that conforming Apps validate deterministically. pyright is now
Studio's declared dependency, pinned by `uv.lock`, run with `--pythonpath` at the project's own
interpreter so import resolution still comes from the project's environment. Upgrades now travel
the path every dependency travels: `uv lock --upgrade-package pyright`, the gate, a commit.

## Context

As of 2026-09-12 the rules an App must satisfy all existed, but each lived where its failure
happened to surface, and each stopped at the first violation it met:

| Rule | Where it was enforced |
| --- | --- |
| Tool names unique, Page names unique | `tool_registry_for`, `page_registry_for`, as a window opened |
| a route starts with `/`, routes unique | the NiceGUI adapter, as it registered routes — the Web channel only |
| configuration values valid | the window, before the lifespan |
| the entrypoint loads and is an `AppEntrypoint` | `load_app` |
| a Page refers to a Tool that exists and is exposed to it | nowhere; `tool.not_found` or `tool.forbidden` at first render |
| a Tool is exposed on at least one channel | nowhere; `channels=frozenset()` was accepted |
| handler, `config` and lifespan satisfy the framework's typed contracts | pyright, if the author happened to run it |

An agent authoring an App therefore learned one problem per run; learned two of them only if it
opened a Web window, because route checking sat in one channel's adapter; learned nothing about
a Page's Tool references or a Tool exposed nowhere until something failed at render, or never;
and learned the type-level ones only by choosing to type-check. `docs/architecture/authoring.md`
named `validate_app` as where this is answered and deferred it to this milestone.

The conventions consulted: Python `dataclasses` post-init processing, and attrs, which places
invariants in `__init__` and the cross-attribute ones in the post-init hook; pydantic, whose
`ValidationError` collects every error of a parse rather than the first; PEP 484's non-goals,
which place type checking offline in opt-in checkers and leave the runtime unchanged; Django's
system checks, which are static, inspect declarations only — a declared relation is checked, a
`reverse()` in view code is not — and carry a level on each `CheckMessage`; Angular's `imports`
and Relay's fragments with data masking, where a component declares what it uses and cannot
reach what it did not declare; Next.js's `next build`, which runs the project's own type checker
with the project's own configuration and fails the build on its errors; uv's `--with`, which
adds a tool to one invocation without touching the project; and LSP's `Diagnostic`, which
carries a severity where a failure carries none.

## Decision

A rule is placed by what can express it:

| Rule kind | Where |
| --- | --- |
| a value the type cannot constrain | the declaring dataclass's `__post_init__` |
| a relationship between declarations | `AppDefinition.__post_init__`, collected and raised once |
| a type-level contract | the type checker, run by `validate_app` |

`ToolDefinition.__post_init__` refuses an empty `channels`: a Tool is an operation an external
actor invokes, and one exposed nowhere is a contradiction — unlike an empty `required_roles`,
which means anyone. `AppDefinition.__post_init__` runs every cross-declaration rule — Tool and
Page name conflicts, route format, route conflicts, and each Page's Tool references — collects
every violation in declaration order and raises one `AppDefinitionInvalidError` whether it found
one or five. The member exceptions keep their own types and codes: they say *which* rule broke,
the aggregate says *that* the declaration is invalid. `tool_registry_for`, `page_registry_for`
and the NiceGUI adapter's `register_pages` no longer check anything; they register. The codes
are `docs/architecture/errors.md`'s.

`PageDefinition.tools` is required, with no default: a Page that invokes nothing declares
`frozenset()` and the framework does not guess. It is both a declaration a reader can use — the
validator, `describe`, an agent — and the allow-list `PageRuntime` binds into the invoker the
Page receives at render, so a name outside it is `page.tool_undeclared` before `ToolRuntime` is
reached. This is Relay's masking: an App the validator passed cannot fail at render for a Tool
its Page never named.

Nothing checks a handler, a `config` class or a lifespan at runtime. `ToolHandler` is a Protocol
admitting a callable object, so `iscoroutinefunction` would refuse a legal handler; these are
the type checker's, and the type checker is run.

`report` writes an aggregate as one line and then one line per member, in order. `describe`
therefore reports every violation and no fifth command exists: `describe` already imports the
entrypoint, and its failure path *is* the validation.

Studio's `validate_app` (Agent channel) runs two authorities independently in the project's
environment and concatenates what they report: `describe`, and
`uv run --with "pyright[nodejs]" pyright --outputjson` over the project. Configuration
resolution stays pyright's. Each finding is a `Diagnostic(severity, error: ErrorInfo)` and
nothing pyright reports is dropped; `conforms` is the absence of an `error`-severity diagnostic, stated as a
field so an agent does not recompute it. A `Diagnostic` is not an `ErrorInfo`: a failure
happened and has no degree, a finding about a declaration may be advisory. It lives in Studio's
authoring vocabulary, where its only producer is.

Rejected:

- **A rule registry or `check()` methods, Django-style** — the framework's declarations are
  frozen dataclasses, not classes with behaviour, so a registry would need a two-way conversion
  and would put behaviour on values that have none.
- **Parsing handler bodies for the Tool names they invoke** — a static reading of code, which is
  what Django's checks decline to do; the declaration states it instead.
- **Runtime `iscoroutinefunction` / `issubclass` guards** — PEP 484 places this offline, and the
  Protocols admit callable objects that such a guard would refuse.
- **A severity on `ErrorInfo`** — it would give every framework failure a degree it does not
  have, to serve one consumer.
- **A fifth command** — `describe` already imports the entrypoint; a second importer would be a
  second answer to one question.
- **pyright in Studio's dependencies** — the checker belongs to the project being checked, at
  the project's version and configuration; `--with` supplies it for one invocation.

## Consequences

- An invalid declaration cannot exist. Windows and adapters register what they are handed, and
  nothing checks twice.
- Route validation is channel-neutral: it is the declaration's, not the Web adapter's.
- Every App declaring a Page adds `tools=`. Pre-production, every App in this repository is
  changed in the same commit; `AGENTS.md`'s backward-compatibility rule applies to the API once
  it is a product.
- A Page cannot reach an undeclared Tool at runtime, whatever its body attempts.
- `describe` may write several lines where it wrote one, and every reader of a command's stderr
  parses line by line.
- `validate_app` downloads pyright and Node into uv's cache once per machine. Offline, that
  authority fails as `authoring.environment_failed` while the declaration diagnostics still
  arrive, because the two are run independently.
- A project nested under a parent that sets a pyright mode inherits that mode. This is pyright's
  own resolution rule and is not overridden; the framework imposes no checking mode.
- Should the framework itself one day report an advisory finding, `Diagnostic` moves to
  `vibepy_core` unchanged.
- A generation-time violation — `tool.channels_empty` — fails the import before the aggregate can
  collect it, so an author may see it alone and the cross-declaration ones on the next run. That
  is the price of making the state unrepresentable at the object that owns it.
