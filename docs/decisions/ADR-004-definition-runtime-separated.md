# ADR-004: Definition and Runtime are separate concepts

Status: Superseded by ADR-020

## Decision

Static declarations and executable state are distinct.

```text
AppDefinition -> AppRuntime
```

Later distribution layers may introduce AppPackage and AppInstallation.

## Consequences

- static metadata is not polluted by live dependencies or sessions
- multiple future runtime instances can be created from one definition
- Hub/package lifecycle can evolve separately
