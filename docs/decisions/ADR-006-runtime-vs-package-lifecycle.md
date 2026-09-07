# ADR-006: Runtime lifecycle and package lifecycle are separate

Status: Accepted

## Decision

AppRuntime manages start/stop execution lifecycle only.

Install, upgrade, uninstall, configuration ownership, and package versioning belong to a later Hub/package control plane.

## Consequences

- AppRuntime state machine remains small
- package management can evolve independently
- Hub does not leak into core runtime concepts prematurely
