# ADR-016: Tool invocation has one name

Status: Accepted

## Context

The Page model describes its ToolInvoker as a Protocol carrying ToolRuntime's invocation
signature, so that the core Page model depends on the shape of Tool invocation and not on the
Tool runtime.

The Protocol's method carries a different name from the runtime's. One operation therefore has
two names, ToolRuntime does not satisfy the Protocol written to describe it, and a private
bridge and a second Protocol exist to cover the gap — leaving the Page package with two
Protocols for one operation and an adapter between them.

The framework's own vocabulary settles which name is canonical: a ToolContext carries an
invocation id, ToolRuntime is the canonical invocation path, and the narrowest state scope is
invocation scope.

## Decision

The Protocol's method takes the runtime's name, so ToolRuntime satisfies the Protocol
structurally, the bridge and the second Protocol are removed, and PageRuntime takes the
Protocol.

## Consequences

- one operation has one name across the Page model, the Tool runtime and the documents
- two types are removed and none is added
- the Page package imports nothing from the Tool package
- Page code that used the old name must be updated; the framework is pre-release and no
  deprecation path is offered
- an alternative invocation path, a test double or a decorating invoker, stays expressible
