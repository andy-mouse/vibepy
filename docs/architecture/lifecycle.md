# Lifecycle Architecture

## Runtime lifecycle

Runtime lifecycle is distinct from package installation lifecycle.

The framework owns no runtime lifecycle object and no lifecycle state. A channel's runtime exists
for the duration of an `async with` block and cannot be reached outside it, so there is no state
in which an App is constructed but not running, and no transition to validate. See
`docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md`.

Each channel opens its own window, and neither depends on the other. The Agent channel's window
is opened by the MCP SDK, which enters the lifespan inside `run()`; over stdio the client launches
one server process, so that window is the process. The Web channel's window is opened by whatever
entrypoint the Hub runs. See
`docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md`.

## The lifespan

An App's application-scoped resource is declared as a factory returning an async context
manager, supplied to a channel at composition time rather than inside the declaration. What
precedes the `yield` runs as the window opens; what follows runs as it closes.
`docs/architecture/app-model.md` carries the signatures.

There are no separate start and stop hooks. Binding acquisition to release is what lets a channel
release a resource whose type it does not know. See
`docs/decisions/ADR-018-app-scoped-resource-is-an-async-context-manager.md`.

## Cleanup

Cleanup is the language's, not the framework's. Entering a window is a stack and leaving it pops
that stack: `async with` places an acquisition outside its own `try`, so an acquisition that
raises never reaches its release and is itself responsible for leaving nothing behind, and an
`AsyncExitStack` registers a release only after its acquisition returns.

| Failure | Unwound |
| --- | --- |
| entering the lifespan raises | nothing was acquired |
| a resource inside the lifespan fails after an earlier one was acquired | the lifespan releases the earlier one |
| the lifespan raises on exit | nothing further is owned |

The error reaches the caller in every row. The framework neither swallows it nor classifies it: a
failing lifespan is the host's to report, and the host's own contract already covers that.

## Package lifecycle

Package lifecycle is a later layer:

```text
Package -> install -> configure -> open a channel
```

`configure` is the host supplying the values the App declared it requires; the Hub holds those
values per installation, secrets included, and gives a secret's value back to no channel: it
reports such a field as set. What it holds is readable by its owner and by no one else. The App's
own window validates them as it opens, so a configuration failure happens before anything is
acquired;
`docs/architecture/app-model.md` carries that boundary. `docs/architecture/packaging.md` owns the
step before it — how a Host learns which App a distribution contains and what it requires.

Operations such as install, remove, upgrade, and version migration belong to the package/Hub
control plane. The Hub also owns the Web channel's window, which it opens by running
`python -m vibepy.serve` with the App environment's interpreter, and which is what its start,
stop and status describe. See `docs/decisions/ADR-006-runtime-vs-package-lifecycle.md` and
`docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md`.
