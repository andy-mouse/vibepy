# ADR-016: Tool invocation has one name

Status: Deprecated

This record documents a rename and the removal of two internal types. What survives it — the
ToolInvoker Protocol carries `ToolRuntime.invoke`'s signature, name included, and the Page
package imports nothing from the Tool package — is held by `docs/architecture/page-model.md`.

## Context

ToolInvoker is a Protocol carrying ToolRuntime.invoke's signature, so that the core Page model
depends on the shape of Tool invocation and not on the Tool runtime.

ToolInvoker names that method call. One operation therefore has two names, ToolRuntime does not
satisfy the Protocol written to describe it, and a private `_ToolRuntimeInvoker` exists whose
whole body forwards one call and renames nothing else.

ToolRuntime is generic in the app's dependency type. PageRuntime holding a ToolRuntime directly
— the one place in the Page package that imports it, against the principle the Protocol exists
for — spreads that parameter through the Page package and its tests, and a second Protocol,
`ToolInvocation`, was introduced to hold the spread back. That treats the symptom: the Page
package then carries two Protocols describing one operation, plus an adapter between them.

The framework's own vocabulary settles which name is canonical. A ToolContext carries an
invocation id, ToolRuntime is the canonical invocation path, and the narrowest state scope is
invocation scope. call is the outlier.

ToolRuntime has no public member other than that one operation.

## Decision

ToolInvoker.call is renamed to invoke, matching the signature the Protocol already claimed.

ToolRuntime then satisfies ToolInvoker structurally, `_ToolRuntimeInvoker` and `ToolInvocation`
are both removed, and PageRuntime takes a ToolInvoker.

## Consequences

- one operation has one name across the Page model, the Tool runtime and the documents
- a Page's static view of Tool invocation stays what the Protocol declares, one operation
  addressed by name, and nothing further is reachable even though AppRuntime supplies the
  runtime itself
- two types are removed and none is added
- the Page package imports nothing from the Tool package, which is stronger than before this
  decision
- a Page calls `ctx.tools.invoke(name, raw_input)`. Page code that called `ctx.tools.call` must
  be updated; the framework is pre-release and no deprecation path is offered
- an alternative invocation path, a test double or a decorating invoker, stays expressible,
  because PageRuntime takes the Protocol and not the runtime
