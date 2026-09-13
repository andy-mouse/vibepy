# ADR-021: A declaration holds no resource factory

Status: Accepted

## Context

`AppDefinition` is a frozen value whose purpose is to be read without being run. Package
validation, app inspection and conformance validation all depend on that, which is the
argument ADR-013 used to put the resource in `ToolContext` rather than in a closure.

One of its fields does not belong to that purpose. `lifespan` is a factory: an instruction for
assembling something, not a statement about what the app is. Every other field can be read,
projected and validated; this one can only be called. A reader that wants to know what a app
declares learns nothing from it, and a reader that wants to know what resource it needs learns
nothing either, because `DepsT` is a type the app chose and the framework only carries.

The field was introduced because `AppRuntime` needed somewhere to find a resource, and the
definition was the only object it held. ADR-020 removes that runtime, so the reason is gone.

Composition is a known place, and it is not the declaration. Seemann's rule is that only
applications should have Composition Roots, and that libraries and frameworks should not
(<https://blog.ploeh.dk/2011/07/28/CompositionRoot/>). An App's entrypoint is such an
application: it is the one place that knows both which app this is and what its resource is
made of.

## Decision

`AppDefinition` declares no resource factory. It declares identity, Tools and Pages.

An entrypoint pairs a definition with a lifespan, and that entrypoint is the composition root.
ADR-010 already places an entrypoint in package metadata rather than in runtime behaviour.

## Consequences

- ADR-013 is satisfied exactly as before. Tools and Pages remain values inside the definition, and
  `DepsT` was never inspectable, so nothing that could be read has stopped being readable
- the definition stays generic in `DepsT`. It declares that its Tools require a resource of that
  type and not where one comes from, so a mismatch is rejected by the type checker at the single
  site where the two meet
- a definition can be constructed, inspected and compared without acquiring anything, and two
  channels built from one definition are isolated because each opens its own window
- M9 must resolve an entrypoint and not only a definition. Its acceptance criterion is unaffected:
  inspecting a package still means reading declarations, and running one was always going to mean
  executing something the package names
- what a app may declare *about* its host — configuration schema, secret names, required
  capabilities — is a different kind of statement and a real declaration. It is M8 and M21
  territory, and this decision leaves room for it by keeping the definition free of assembly
