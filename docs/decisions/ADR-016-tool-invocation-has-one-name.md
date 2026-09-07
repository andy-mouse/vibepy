# ADR-016: Tool invocation has one name

Status: Accepted

## Context

ToolInvoker carries ToolRuntime.invoke's signature but names the method call. One operation
therefore has two names, ToolRuntime does not satisfy the Protocol written to describe it, and
a private forwarder and a second Protocol cover the gap. The framework's vocabulary is
invocation throughout: a ToolContext carries an invocation id, ToolRuntime is the canonical
invocation path, and the narrowest state scope is invocation scope.

## Decision

ToolInvoker.call is renamed to invoke.

ToolRuntime then satisfies ToolInvoker structurally, the forwarder and the second Protocol are
removed, and PageRuntime takes a ToolInvoker.

## Consequences

- one operation has one name across the Page model, the Tool runtime and the documents
- two types are removed and none is added
- the Page package imports nothing from the Tool package
- Page code calling the old name must be updated, with no deprecation path offered
- an alternative invoker, a test double or a decorator, stays expressible
