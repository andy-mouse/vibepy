# ADR-013: Application-scoped dependencies reach handlers through ToolContext

Status: Accepted

## Context

A Tool handler needs the App's shared resource — its repository, connection pool or API
client — and nothing delivers one.

Two mechanisms are available.

Closures: the app binds the resource into its handlers while assembling the App, as a bound
method or a nested function. ToolContext does not change.

ToolContext: the app declares a factory for the resource, handlers stay plain functions, and
the resource arrives as a field of the context ToolRuntime already creates.

## Decision

The resource reaches a handler through ToolContext, typed by a parameter the app supplies.

The deciding argument is that an App must be a value rather than a procedure. An
AppDefinition holds declarations and no live connections, and a handler bound to a live
resource puts one inside the declaration. Package validation, App inspection and conformance
validation all read an App's declarations without running it, and an assembly function has
nothing to read.

## Consequences

- the dependency type threads through ToolContext, ToolHandler, Tool, ToolRegistry,
  ToolRuntime, AppDefinition and AppRuntime
- ADR-008's variance problem does not recur. It arises because each Tool has its own input
  type, whereas the dependency type is one type per App, so a registry parameterized by it
  holds uniformly typed values with neither Any nor cast
- the Page model is untouched. A Page reaches Tools by name through ToolInvoker, so no Page
  type carries the dependency type, and PageRuntime depends on the shape of Tool invocation
  rather than on the runtime
- a handler still receives no access to AppRuntime. It receives one value of a type the app
  itself declared
- closures remain legal. An app may still bind state into a handler; the framework simply no
  longer requires it
- an App with no shared resource declares None. No default is provided, because the framework
  does not guess that an App is stateless
