# M6 - Runtime lifecycle: Design

## Acceptance criteria

From `docs/roadmap.md`:

- runtime transitions through the defined lifecycle states predictably
- lifecycle hooks execute at the intended transition boundaries
- startup/shutdown failures perform deterministic cleanup

## Problem

`AppRuntime` has no lifecycle. Its constructor calls `create_dependencies()` and the App is
live from the moment the object exists. There is no boundary at which an App has been
started, and none at which it has been stopped, so nothing can release what startup acquired.

M5A created the resource in the constructor deliberately, recording that
`docs/architecture/lifecycle.md` places initialization at startup step 2 and that this
milestone moves it.

`docs/architecture/lifecycle.md` states the requirement in one line: "Partial startup failure
must result in deterministic cleanup." It does not say what is unwound.

## The structural principle

The startup order in `docs/architecture/lifecycle.md` is a stack, not a list. Each step
acquires something, and shutdown pops the steps in reverse. Deterministic cleanup has one
meaning under that reading:

> Unwind the steps that completed, in reverse order. A step that did not complete has nothing
> to unwind.

This is the discipline `contextlib` already implements.
`AsyncExitStack.enter_async_context` "Asynchronously enters an asynchronous context manager
and registers its `__aexit__()` method on the stack" — the release is registered only after
the acquisition succeeded. `close()` "unwinds the callback stack in reverse registration
order". The documented example is exactly the partial-failure case:

> All opened connections will automatically be released at the end of the async with
> statement, even if attempts to open a connection later in the list raise an exception.

The language reference makes the pairing explicit. The semantic expansion of `async with`
places the acquisition outside the `try`:

```python
value = await aenter()
hit_except = False
try:
    SUITE
...
```

An `__aenter__` that raises therefore never reaches `__aexit__`. An acquisition step is
responsible for leaving nothing behind when it fails.

Sources:

- <https://github.com/python/cpython/blob/main/Doc/library/contextlib.rst>
- <https://github.com/python/cpython/blob/main/Doc/reference/compound_stmts.rst>

## Decision: the app-scoped resource is an async context manager

The principle rules out the shape `docs/roadmap.md` names for M6.

Paired `on_start`/`on_stop` hooks over a plain `create_dependencies` factory cannot satisfy
it. The framework does not know how to close `DepsT`, so release has to live in `on_stop`.
`on_stop` is then the pop of two different steps at once, and the case where dependencies
were created and `on_start` failed has no correct answer: `on_stop` must not run, because its
step never completed, and it must run, because it is the only code that can release the
resource. The resource leaks under either reading.

Binding acquisition and release into one declaration removes the case:

```python
lifespan: Callable[[], AbstractAsyncContextManager[DepsT]]
```

An App writes one function. What precedes `yield` runs during `STARTING`, what follows runs
during `STOPPING`, and the two cannot be declared apart.

```python
@asynccontextmanager
async def todo_lifespan() -> AsyncIterator[TodoStore]:
    store = TodoStore()
    yield store
    store.close()
```

The `yield` boundary is what the second acceptance criterion asks for. No separate `on_start`
or `on_stop` field is introduced.

This is the shape the reference implementation of the same problem converged on. Starlette's
lifespan handler is an async context manager that yields the application-scoped state, and
Starlette 1.0.0 removed the paired hooks that preceded it:

> Remove `on_startup` and `on_shutdown` parameters from `Starlette` and `Router`. Use the
> `lifespan` parameter instead

Sources:

- <https://github.com/kludex/starlette/blob/main/docs/lifespan.md>
- <https://github.com/kludex/starlette/blob/main/docs/release-notes.md>

Departing from the wording in `docs/roadmap.md` was put to the owner and approved. The
roadmap is not edited. Its acceptance criteria are met: the `yield` boundary is the hook
boundary.

## Public API

### AppDefinition

`create_dependencies` becomes `lifespan`. Its return type changes, so the name is corrected
to what the field now is.

```python
@dataclass(frozen=True)
class AppDefinition[DepsT]:
    app_id: str
    name: str
    version: str
    lifespan: Callable[[], AbstractAsyncContextManager[DepsT]]
    tools: Sequence[Tool[DepsT]]
    pages: Sequence[Page]
```

`contextlib.AbstractAsyncContextManager` is the ABC's own name. `typing.AsyncContextManager`
is a deprecated alias and is not used.

The field remains a factory rather than a live context manager, for the reason M5A gives: a
definition holding a live resource would not be a declaration, and one definition would yield
runtimes that shared state.

An App with no resource declares a context manager that yields `None`. The framework ships no
helper for it; whether one is worth adding is not decided here.

### AppRuntimeState

```python
class AppRuntimeState(StrEnum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
```

`StrEnum` because the value is a state an operator and a log read, and M10's Hub reports it.

### AppRuntime

```python
class AppRuntime[DepsT]:
    def __init__(self, definition: AppDefinition[DepsT]) -> None: ...

    @property
    def state(self) -> AppRuntimeState: ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

The constructor fills the two registries from the declarations and enters `CREATED`. It
acquires nothing.

`start()` enters the lifespan, builds `ToolRuntime` and `PageRuntime` over the resource it
yielded, and enters `RUNNING`.

`stop()` unwinds and enters `STOPPED`.

### What is readable when

| Property | Available |
| --- | --- |
| `definition`, `tool_registry`, `page_registry` | always; built from declarations, needing no resource |
| `tool_runtime`, `page_runtime` | `RUNNING` only; built over the resource |

Channel adapters read `tool_runtime`, so **an adapter is built after `start()`**. ADR-015
still holds — an adapter is constructed from one AppRuntime — and gains an ordering
constraint.

The application-scoped resource stays unexposed. A Tool handler receives it through its
ToolContext.

## State rules

`STOPPED` is terminal. `docs/roadmap.md` draws no edge back, and an unwound runtime has no
resource to re-enter. Restarting means a new `AppRuntime`, which M5A already established is
isolated from its predecessor.

Concurrent `start()` needs no lock. The transition to `STARTING` is synchronous and happens
before the first `await`, so a second caller observes a state that forbids starting and fails
deterministically. The same holds for `stop()`.

The stop path reaches `STOPPED` whatever happens on it. A runtime stuck in `STOPPING` is one
the Hub can never finish cleaning up.

## Failure rules

Derived from the principle, not chosen:

| Failure | Unwound | Final state |
| --- | --- | --- |
| entering the lifespan raises | nothing was acquired | `STOPPED`, error propagates |
| a nested resource inside the lifespan raises after an earlier one was acquired | the app's own `async with` releases the earlier one | `STOPPED`, error propagates |
| the lifespan raises on exit | nothing further is owned | `STOPPED`, error propagates |

The framework does not catch these. The caller of `start()` or `stop()` sees the error, and
`state` is accurate when it does.

## Errors

Two new exceptions derive from `VibepyError`. The types are the contract.

- a transition the current state forbids: `start()` twice, `start()` after `STOPPED`,
  `stop()` before `start()`
- reading `tool_runtime` or `page_runtime` while not `RUNNING`

They are distinct because they are distinct failures: one is a caller driving the lifecycle
wrongly, the other is a caller using the App outside its running window.

Machine-readable error codes are M7 and are not introduced here.

## Testing

The acceptance criteria are the tests.

### Transitions are predictable

- `state` is `CREATED` after construction, `RUNNING` after `start()`, `STOPPED` after
  `stop()`
- `start()` twice raises the transition error, and the state is unchanged
- two concurrent `start()` calls: one succeeds, the other raises
- `start()` after `stop()` raises
- `stop()` before `start()` raises
- `tool_runtime` raises outside `RUNNING`, and is the same object throughout one `RUNNING`
  window

### Hooks execute at the boundaries

- a lifespan that records events proves the pre-`yield` body ran during `STARTING` and the
  post-`yield` body during `STOPPING`, in that order
- a Tool invoked while `RUNNING` receives the value the lifespan yielded
- two AppRuntimes from one AppDefinition enter two independent lifespans

### Failures clean up deterministically

- a lifespan that raises before `yield`: `start()` propagates it and `state` is `STOPPED`
- a lifespan holding two nested resources where the second acquisition raises: the first is
  released, `state` is `STOPPED`
- a lifespan that raises after `yield`: `stop()` propagates it and `state` is `STOPPED`

### Existing tests

The M5B execution-semantics test and the M4 dual-channel test build adapters, so they gain a
`start()` and a `stop()`. What they prove is unchanged. The Todo fixture's `TodoStore`
factory becomes a lifespan.

## Out of scope

- **Channel adapter startup.** `docs/architecture/lifecycle.md` places adapter start at
  startup step 4, and ADR-012 anticipates `ui.run()` there. `docs/roadmap.md` names no adapter
  in M6, and the shape that startup would take depends on ADR-017, which is `Proposed` and
  leaves port ownership, authentication and the proxy's home undecided. Startup stays at the
  resource and the lifespan; step 4 remains future work.
- **Timeouts, cancellation and graceful shutdown.** M20.
- **Structured error codes.** M7.
- **Typed configuration.** M8.
- **Hub-driven start/stop/status.** M10.

## Compatibility

`AppDefinition.create_dependencies` is renamed to `lifespan` and its type changes. Every
existing construction site is updated in the same change; nothing is deprecated, because the
old field cannot express a release and keeping it would leave two ways to declare one
resource.

`AppRuntime`'s constructor keeps its signature, but its behaviour narrows: an App is no
longer usable the moment it is constructed. Nothing is removed, so there is nothing to
deprecate, but M5A's spec records that AGENTS.md's backward-compatibility rule applies to the
surface it left behind, and this is the change that rule asks to be recorded. The narrowing is
not avoidable: if `CREATED` and `RUNNING` were indistinguishable to a caller, the first
acceptance criterion would be unmeetable.

## Documentation

Updated:

- `docs/architecture/lifecycle.md` — the owning document. States, the lifespan contract, the
  unwinding rule, and the failure table become concrete. Startup step 4 is marked as future
  work pointing at ADR-017.
- `docs/architecture/app-model.md` — the `lifespan` field, `start`/`stop`/`state`, and the
  resource being acquired at startup rather than in the constructor.
- `docs/architecture/adapters.md` — one line: an adapter is built from a started AppRuntime.

New ADR:

- the app-scoped resource is declared as an async context manager, and no paired start/stop
  hooks are introduced

No ADR is superseded. ADR-013 decides that the resource reaches a handler through ToolContext,
typed by a parameter the app supplies, and that decision is untouched: only the shape of the
declaration changes. ADR-013 mentions a factory in its Context, which is the record of what
was true when it was taken and is not rewritten. ADR-015 keeps its decision and gains the
ordering constraint as a consequence recorded in the new ADR.
