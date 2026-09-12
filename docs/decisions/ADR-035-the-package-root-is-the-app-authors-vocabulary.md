# ADR-035: The package root is the App author's vocabulary

Status: Accepted

## Context

`vibepy_core`'s root `__init__` re-exported sixty-three names. Among them, next to
`AppDefinition` and `Tool`, were `discover_apps`, `load_app`, `describe_app`, `described`,
`environment_for`, `config_fields_of`, `report`, `APP_GROUP` and `AppRef` — every operation a
*host* performs, sitting in the surface an *App author* imports. `vibepy_core.app`'s `__init__`
did the same one level down.

`docs/architecture/packaging.md` already draws the line the root blurred: "What can be read
without running is read from metadata. What requires an import happens in the App's own
environment. Two operations, one on each side of that line, and nothing that spans it"
(packaging.md:37). Its isolation invariant is "the Host never imports an App" (packaging.md:255,
enforced as ADR-023 records), and `load_app`'s own docstring says "`serve`, `invoke` and `mcp`
call it there, and a host reaches it only through them" — while the root offered it to everyone.

The invariant was held instead by a test in the consuming App:
`packages/vibepy-studio/tests/test_no_blocking_handlers.py` walked Studio's Tool modules against a
closed import allowlist, and its own docstring explained that "`vibepy_core` itself is not on the
list: its root package re-exports `discover_apps`, `describe_app` and `load_app`, all blocking".
That allowlist had already been widened once to admit `vibepy_core.invoke` — a command module, not
a vocabulary — solely so a Tool module could reach the `InvocationRequest` type declared there.
`invoke.py` imports `load_app` at its line 30, so the entry admitted exactly what the guard
existed to forbid. A guard that must be widened to reach a type is evidence about where the type
lives, not about the guard.

PEP 8 settles what a re-exporting `__init__` may be relied upon for: "Imported names should always
be considered an implementation detail. Other modules must not rely on indirect access to such
imported names unless they are an explicitly documented part of the containing module's API, such
as `os.path` or a package's `__init__` module that exposes functionality from submodules"
(<https://peps.python.org/pep-0008/>). The root was exposing, as a documented API, functionality
its own architecture documents said a host may not reach directly.

Nothing in the repository depended on that: across `src/`, `packages/`, `fixtures/` and the test
suites, no file imported a host operation from the root. The mixed surface had users only in the
sentence describing how to avoid it.

## Decision

The package root is the App author's vocabulary. `vibepy_core` exports declarations
(`AppDefinition`, `AppConfig`, `NoConfig`, `AppEntrypoint`, `Lifespan`, the Tool and Page models,
`Principal`, `Channel`, the authorization types), the description models a reader validates,
every framework error with `ErrorInfo`, `ErrorCategory` and `ERROR_CATALOG`, the registries and
runtimes, and the two composition functions. `vibepy_core.app` follows the same rule with
declarations and descriptions.

A host operation is reached at its own module, and only there: `vibepy_core.app.package` for
discovery and loading, `vibepy_core.app.config` for the environment, `vibepy_core.app.group` for
the entry point group, `vibepy_core.errors` for reporting.

A boundary model lives with the vocabulary it is made of, never with the command that transports
it. `InvocationRequest` is the Tool's per-call `input`, so it is declared in `vibepy_core.tool`;
`DescribedApp` wraps an `AppDescription`, so it is declared beside it in `vibepy_core.app.entrypoint`.
This is AGENTS.md's boundary-shape rule made addressable: the rule said one model owned by
`vibepy_core`, and this says which module owns it.

The current contract is `tests/test_package.py`'s two literal lists and
`docs/architecture/app-model.md`, "The import surface".

Rejected, and why:

- **keep the mixed root and fix the allowlist**: the allowlist is the symptom. It exists because
  a name reachable through the root is invisible at the import that reaches it, and a second
  widening for the next type would be as justified as the first was.
- **a separate `vibepy_core.host` surface**: `vibepy_core.app.package` already is the
  host-operations module, and its docstring already says so. A `host` package would be a second
  name for one module with four callers, which AGENTS.md's preference for explicit implementations
  over abstraction-before-repetition rules out.
- **deprecate the host names at the root first**: pre-production, and the owner's stance is that
  a compatibility period buys nothing when every call site is in this repository — there were none.

## Consequences

- the isolation invariant is a property of the import graph rather than a sentence a reviewer
  must remember: no aggregating `__init__` a Tool module can reach holds a blocking loader, so
  reaching one requires naming `vibepy_core.app.package` in the import, where review sees it
- the import half of `packages/vibepy-studio/tests/test_no_blocking_handlers.py` became
  redundant, and the allowlist entry for `vibepy_core.invoke` disappeared rather than being
  replaced
- every later module is constrained in where it may be exported: a new operation that imports or
  blocks is not added to either `__init__`, and a new boundary model is declared with its
  vocabulary
- `ERROR_CATALOG` and the error classes stay at the root while `report` and `to_error_info` leave
  it. The codes are an author's and a reader's vocabulary (ADR-019); writing and parsing a report
  line is a command's work
- an App author writing against the root sees a smaller surface, and every name in it is one an
  App declares or raises
- ADR-017's per-channel processes are unaffected: this changes where a name is imported from, not
  what any operation does
