# ADR-006: Runtime lifecycle and package lifecycle are separate

Status: Superseded by ADR-017 and ADR-020

ADR-020 removed the `AppRuntime` this record's Decision manages. The boundary that survived —
the Hub owns install, remove and upgrade, and the framework owns none of them — is ADR-017's
Decision and ADR-024's.

## Decision

AppRuntime manages start/stop execution lifecycle only.

Install, upgrade, uninstall, configuration ownership, and package versioning belong to a later Hub/package control plane.

## Consequences

- AppRuntime state machine remains small
- package management can evolve independently
- Hub does not leak into core runtime concepts prematurely
