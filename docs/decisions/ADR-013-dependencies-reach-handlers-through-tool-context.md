# ADR-013: Application-scoped dependencies reach handlers through ToolContext

Status: Accepted

## Context

A Tool handler needs the App's shared resource. The app can bind it into handlers as closures
while assembling the App, or declare a factory and receive the resource on the ToolContext
that ToolRuntime already creates.

## Decision

The resource reaches a handler through ToolContext, typed by a parameter the app supplies.

An App stays a value rather than a procedure, so package validation, App inspection and
conformance validation read its declarations without running it. A handler bound to a live
resource would put one inside the declaration.

## Consequences

- the dependency type is one per App, so it threads through the Tool types without Any or cast
- the Page model is untouched, because a Page reaches Tools by name through ToolInvoker
- a handler receives one value of a type the app declared, never AppRuntime
- closures remain legal; the framework no longer requires them
- an App with no shared resource declares None, because the framework does not guess
