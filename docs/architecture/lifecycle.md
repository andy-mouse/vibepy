# Lifecycle Architecture

## Runtime lifecycle

Runtime lifecycle is distinct from package installation lifecycle.

AppRuntime states:

```text
CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED
```

STOPPED is terminal. An unwound runtime holds no resource to re-enter, so a restart is a new
AppRuntime.

`AppRuntime.state` reports the current state. `start()` and `stop()` are the only transitions,
and a transition the current state forbids raises rather than being ignored. The move into
STARTING and STOPPING precedes the first await, so concurrent calls need no lock: the second
caller observes a state that forbids the transition.

The framework owns state transition validation and cleanup behavior.

Framework errors are `AppRuntimeTransitionError`, raised when the current state forbids the
transition, and `AppRuntimeNotRunningError`, raised when a runtime that exists only while
RUNNING is reached outside that window. They are distinct because they are distinct failures:
one is a caller driving the lifecycle wrongly, the other is a caller using the App outside its
running window. `docs/architecture/errors.md` carries their codes.

## The lifespan

An App declares its application-scoped resource as a factory returning an async context
manager. What precedes the `yield` runs while the runtime is STARTING; what follows runs while
it is STOPPING. `docs/architecture/app-model.md` carries the field.

There are no separate start and stop hooks. Binding acquisition to release is what lets the
framework release a resource whose type it does not know. See
`docs/decisions/ADR-018-app-scoped-resource-is-an-async-context-manager.md`.

## Startup

1. validate the state transition
2. enter the lifespan and build the runtimes over what it yields
3. enter RUNNING

Channel adapters are not started. `docs/architecture/adapters.md` describes what each adapter
does instead, and whether an App's own process serves its channels is open in
`docs/decisions/ADR-017-one-process-serves-both-channels.md`.

## Shutdown

1. validate the state transition
2. unwind what startup acquired, in reverse
3. enter STOPPED

## Cleanup

Startup is a stack and shutdown pops it. Cleanup unwinds the steps that completed, in reverse;
a step that did not complete has nothing to unwind. An acquisition that fails is responsible
for leaving nothing behind, which is the contract `async with` already places on `__aenter__`.

| Failure | Unwound | Final state |
| --- | --- | --- |
| entering the lifespan raises | nothing was acquired | STOPPED |
| a resource inside the lifespan fails after an earlier one was acquired | the lifespan releases the earlier one | STOPPED |
| the lifespan raises on exit | nothing further is owned | STOPPED |

The error reaches the caller of `start()` or `stop()` in every row. The framework does not
swallow it, and `state` is accurate when the caller sees it. A runtime left in STARTING or
STOPPING is one a control plane could never finish cleaning up.

## Package lifecycle

Package lifecycle is a later layer:

```text
Package -> install -> configure -> start Runtime
```

Operations such as install, upgrade, uninstall, and version migration belong to the
package/Hub control plane, not AppRuntime.
