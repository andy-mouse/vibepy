# ADR-016: Tool invocation has one name

Status: Accepted

## Context

`docs/architecture/page-model.md` describes ToolInvoker as a Protocol whose "signature is
`ToolRuntime.invoke`'s", so that "the core Page model depends on the shape of Tool
invocation, not on the Tool runtime".

The Protocol's method is named `call` while the runtime's is `invoke`. One operation
therefore has two names, `ToolRuntime` does not satisfy the Protocol written to describe
it, and a private `_ToolRuntimeInvoker` bridges the gap by forwarding one call and renaming
nothing else.

`ToolRuntime` is generic in the app's dependency type, and `PageRuntime` holds one
directly — the one place in the Page package that imports it, against the principle the
Protocol exists for — so that parameter spreads through the Page package and its tests. A
second Protocol, `ToolInvocation`, holds the spread back, which treats the symptom: the
Page package then has two Protocols describing one operation and an adapter between them.

The framework's own vocabulary settles which name is canonical. `ToolContext` carries an
`invocation_id`; `docs/architecture/runtime.md` names ToolRuntime the "canonical invocation
path" and `docs/architecture/app-model.md` calls the narrowest state scope "invocation
scope". `call` is the outlier.

## Decision

`ToolInvoker.call` is renamed to `ToolInvoker.invoke`, matching the signature the document
already claimed for it.

`ToolRuntime` then satisfies `ToolInvoker` structurally. `_ToolRuntimeInvoker` and
`ToolInvocation` are both removed, and `PageRuntime` takes a `ToolInvoker`.

A Page's static view of Tool invocation is what the Protocol declares: one operation,
addressed by name. `ToolRuntime` has no other public member, so nothing further is reachable
even though it is the object AppRuntime supplies.

## Consequences

- one operation, one name, across the Page model, the Tool runtime and the documents
- two types are removed and none is added
- the Page package imports nothing from the Tool package, which is stronger than before
  this decision: `page/runtime.py` previously imported `ToolRuntime`
- a Page calls `await ctx.tools.invoke(name, raw_input)`. Existing Page code that called
  `ctx.tools.call` must be updated; the framework is pre-release and no deprecation path is
  offered
- an alternative Tool invocation path — a test double, or a future decorating invoker — is
  still expressible, because `PageRuntime` takes the Protocol and not the runtime
