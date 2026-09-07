# Lifecycle Architecture

## Runtime lifecycle

Runtime lifecycle is distinct from package installation lifecycle.

Initial AppRuntime states:

```text
CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED
```

AppRuntime may support minimal optional hooks:

- on_start
- on_stop

The framework owns state transition validation and cleanup behavior.

## Startup

Conceptual order:

1. validate state transition
2. initialize application-scoped dependencies
3. invoke optional app start hook
4. initialize/start channel adapters
5. enter RUNNING

## Shutdown

Conceptual reverse order:

1. stop channel adapters
2. invoke optional app stop hook
3. release application-scoped dependencies
4. enter STOPPED

Partial startup failure must result in deterministic cleanup.

## Package lifecycle

Package lifecycle is a later layer:

```text
Package -> install -> configure -> start Runtime
```

Operations such as install, upgrade, uninstall, and version migration belong to the package/Hub control plane, not AppRuntime.
