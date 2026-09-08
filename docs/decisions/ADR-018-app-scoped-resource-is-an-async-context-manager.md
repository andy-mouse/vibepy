# ADR-018: The app-scoped resource is an async context manager

Status: Superseded by ADR-021

## Context

AppRuntime acquires an App's shared resource and must release it. It cannot close that
resource itself: `DepsT` is a type the app declared, and the framework only carries it.

Startup is a stack and shutdown pops it, so deterministic cleanup means unwinding the steps
that completed, in reverse. The standard library already implements that discipline.
`AsyncExitStack.enter_async_context` registers a context manager's `__aexit__` only after
`__aenter__` returns, and `close()` unwinds in reverse registration order, so connections
already opened are released when a later one fails
([CPython - contextlib](https://github.com/python/cpython/blob/main/Doc/library/contextlib.rst)).
The expansion of `async with` places the acquisition outside its `try`, so an acquisition
that raises never reaches its release and is itself responsible for leaving nothing behind
([CPython - compound statements](https://github.com/python/cpython/blob/main/Doc/reference/compound_stmts.rst)).

Paired `on_start`/`on_stop` hooks over a dependency factory cannot express this. Release has
nowhere to live but `on_stop`, which makes `on_stop` the pop of two steps at once. When the
resource was acquired and `on_start` raised, `on_stop` must not run, because its own step
never completed, and must run, because nothing else can release the resource.

A third declaration beside the factory restores the pairing without enforcing it: an app that
declares a factory and no release still type-checks. Hooks that receive the AppRuntime
instead are ruled out by ADR-013.

Starlette answered the same question for ASGI applications. Its lifespan handler is an async
context manager that yields the application-scoped state, and 1.0.0 removed the paired hooks
that preceded it
([Starlette - lifespan](https://github.com/kludex/starlette/blob/main/docs/lifespan.md),
[Starlette - release notes](https://github.com/kludex/starlette/blob/main/docs/release-notes.md)).

## Decision

AppDefinition declares `lifespan`, a factory returning an `AbstractAsyncContextManager[DepsT]`.
What precedes the `yield` runs while the runtime is STARTING, what follows runs while it is
STOPPING. No `on_start` or `on_stop` field is introduced.

AppRuntime enters the lifespan through an AsyncExitStack at startup and closes that stack at
shutdown.

## Consequences

- acquisition and release cannot be declared apart, so an App cannot declare a resource it
  never releases
- the resource is acquired at startup rather than at construction, so ToolRuntime and
  PageRuntime exist only while the App is RUNNING and a channel adapter is built from a
  started AppRuntime; ADR-015 is unchanged and gains that ordering constraint
- route validation runs behind startup, because `register_pages` reads the AppRuntime.
  Validating an App without running it needs a path that reads PageRegistry alone, which no
  milestone has required yet
- STOPPED is terminal, so a restart is a new AppRuntime and is isolated from its predecessor
- ADR-013 is untouched. The resource still reaches a handler through ToolContext, typed by a
  parameter the app supplies; only the shape of the declaration changes
- later startup steps, such as the in-process adapters ADR-017 proposes, are pushed onto the
  same stack rather than adding unwinding code of their own
- `docs/roadmap.md` names `on_start` and `on_stop` for this milestone. The departure was put
  to the owner and approved, and the `yield` is the transition boundary its acceptance
  criterion asks for
