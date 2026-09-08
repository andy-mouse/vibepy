# ADR-020: The Plugin replaces the App

Status: Accepted

Supersedes: ADR-004

## Context

`App` was the framework's top-level noun: the unit of definition, of packaging and of runtime
composition. Three questions asked in order left it holding none of the three.

It is not the packaging unit. What is installed, removed and updated is a package, and the Hub
owns that lifecycle. `AppDefinition` is a value inside such a package, not the package.

It is not the execution unit. ADR-017 puts each channel of an installed App in its own operating
system process, so what runs is a channel, and an installed App runs as more than one of them.
No single object can stand for "the App, running".

It is not a dependency scope either. What scopes the shared resource is the window between a
lifespan's acquisition and its release, and ADR-018 already made that window an async context
manager.

What remains under the name is a declaration and an identity: this is who I am, these are my
Tools, these are my Pages. That is what a plugin is, and it is what every Python-ecosystem
precedent calls one. The PyPA glossary keeps Distribution Package distinct from the code it
contains (<https://packaging.python.org/en/latest/glossary/>). Django states plainly that "there's
no such thing as an `Application` object" and that an application is "a Python package that
provides some set of features"
(<https://docs.djangoproject.com/en/stable/ref/applications/>). pytest discovers plugins through
the `pytest11` entry point group and calls them plugins, not applications
(<https://docs.pytest.org/en/stable/how-to/writing_plugins.html>).

`App` also collides with the word's ordinary meaning. Home Assistant reserves "Apps" for
container images that run as their own process under a supervisor
(<https://www.home-assistant.io/addons/>), which is the opposite of what an `AppDefinition` is.

## Decision

`AppDefinition` becomes `PluginDefinition` and `app_id` becomes `plugin_id`. `App` leaves the
framework vocabulary entirely; nothing it named survives without a better name.

`AppRuntime` is not renamed. ADR-021 removes it.

## Consequences

- the error code `app.unhandled` is retired and `plugin.unhandled` replaces it. A retired code is
  never reused and never redefined, which `docs/architecture/errors.md` requires
- `docs/roadmap.md` is not edited. Its "App" and "AppDefinition" are read as "Plugin" and
  "PluginDefinition", and M9's "App Package" as the Plugin's package. The owner decides the
  roadmap's wording; this ADR decides how the repository reads it
- ADR-004 is superseded. Its artifact, `AppDefinition -> AppRuntime`, no longer exists. The
  principle underneath it — a declaration is not executable state — survives in ADR-022, which
  states it about a value rather than about a pair of objects
- `docs/architecture/app-model.md` becomes `docs/architecture/plugin-model.md`
- the framework is pre-release and no deprecation path is offered, which is the ground ADR-016
  took for a smaller rename
- whether capabilities are declared and resolved across plugins remains a separate decision
  belonging to M19, exactly as ADR-017 left it. A Plugin is a packaging unit and depends on no
  other Plugin's capabilities
