# ADR-013: Application-scoped dependencies reach handlers through ToolContext

Status: Accepted

## Context

`docs/roadmap.md` M5A gives the App an owner: `AppDefinition`, `AppRuntime`, application-
scoped typed dependencies, and ToolContext creation from AppRuntime. A Tool handler needs
the App's shared resource — its repository, connection pool or API client — and until this
milestone that resource was a local variable of a test helper.

Two mechanisms are available.

Closures: the app binds the resource into its handlers while assembling the App, as a bound
method or a nested function. `ToolContext` does not change.

ToolContext: the app declares a factory for the resource, handlers are plain functions, and
the resource arrives as a field of the context the runtime already creates.

## Decision

The resource reaches a handler through `ToolContext`, typed by a parameter the app supplies.

```python
async def create_todo(ctx: ToolContext[TodoStore], payload: CreateTodoInput) -> Todo:
    return ctx.dependencies.create(payload.title)
```

`docs/architecture/runtime.md` already reserved the position, listing "typed app
services/config when required" among a ToolContext's fields and preferring "typed dependency
objects over generic dictionaries".

The deciding argument is that an App must be a value rather than a procedure.
`docs/architecture/app-model.md` states that an AppDefinition holds Tool and Page
declarations and "should not contain live connections"; a handler bound to a live resource
puts one inside the declaration. `docs/architecture/authoring.md` requires deterministic
inspection and validation surfaces, and the milestones that build them — package validation
(M9), `inspect_app` and `validate_app` (M12), conformance validation (M16) — read an App's
declarations without running it. An assembly function has nothing to read.

## Consequences

- `DepsT` threads through `ToolContext`, `ToolHandler`, `Tool`, `ToolRegistry`, `ToolRuntime`,
  `AppDefinition` and `AppRuntime`. ADR-008's variance problem does not recur: it arises
  because each Tool has its own `InputT`, whereas `DepsT` is one type per App, so a
  `ToolRegistry[DepsT]` holds uniformly typed values with neither `Any` nor `cast`
- the Page model is untouched. A Page reaches Tools by name through `ToolInvoker`, so no
  Page type carries `DepsT`. `PageRuntime` depends on the shape of Tool invocation rather
  than on `ToolRuntime[DepsT]`, for the reason `ToolInvoker` itself exists
- a handler still receives no access to AppRuntime. It receives one value of a type the app
  declared, which is what `docs/architecture/app-model.md` requires
- closures remain legal. An app may still bind state into a handler; the framework simply no
  longer requires it
- an App with no shared resource declares `None`. No default is provided, because the
  framework does not guess that an App is stateless
