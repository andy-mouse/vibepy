# ADR-013: Application-scoped dependencies reach handlers through ToolContext

Status: Accepted

## Context

A Tool handler needs the App's shared resource — its repository, connection pool or API
client — and nothing delivers one.

Two mechanisms are available. The app can bind the resource into its handlers as closures
while assembling the App, leaving ToolContext unchanged. Or the app can declare a factory for
the resource and receive it as a field of the context the runtime already creates, leaving
handlers as plain functions.

## Decision

The resource reaches a handler through ToolContext, typed by a parameter the app supplies.

The deciding argument is that an App must be a value rather than a procedure. A handler bound
to a live resource puts one inside the declaration, and package validation, App inspection
and conformance validation all read an App's declarations without running it. An assembly
function has nothing to read.

## Consequences

- the dependency type parameter threads through the Tool types, without `Any` or `cast`,
  because it is one type per App rather than one per Tool
- the Page model is untouched: a Page reaches Tools by name, so no Page type carries it
- a handler still receives no access to AppRuntime, only one value of a type the app declared
- closures remain legal; the framework simply no longer requires them
- an App with no shared resource declares that explicitly, because the framework does not
  guess that an App is stateless
