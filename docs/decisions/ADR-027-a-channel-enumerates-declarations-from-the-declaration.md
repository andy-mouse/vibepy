# ADR-027: A channel enumerates declarations from the declaration

Status: Accepted

## Context

ADR-011 is superseded by ADR-014, and ADR-014 is deprecated with what survives it held by
`docs/architecture/tool-model.md`. Neither is read for current truth; they are read here because
the reasoning this record reverses is theirs.

ADR-011 decided that `ToolRegistry` stores each declaration and that
`ToolRegistry.definitions()` enumerates them, and its consequence was that "channel adapters
project declarations for discovery without receiving them through a second path beside the
registry". The reason was stated in its own Context: the registry "stores the bound callable
alone and discards each declaration", so discovery "has nothing to enumerate". A channel had to
go through the registry because the registry was the only thing that still held a declaration.

ADR-014 removed that premise. Binding moved into `Tool`, a `Tool` carries its own declaration,
and an `AppDefinition` holds a sequence of them. The declaration became directly readable as
`definition.tools`, and ADR-014 kept `definitions()` "unchanged" without re-examining whether an
adapter still needed it.

The two channels have since disagreed, each documented, neither wrong under its own record. The
Web channel enumerates the declaration: ADR-012's amendment records that `register_pages` "has
always taken an `AppDefinition` and enumerated `definition.pages`, never a `PageRegistry`". The
Agent channel enumerates a registry, and builds one for that purpose beside the one its window
already holds, so a running App has two tables with equal contents. A package's own
self-description enumerates the declaration too — `AppEntrypoint.describe` reads
`definition.tools` — so of three enumerating surfaces only one goes through a registry.

A stale consequence is not only waste. It splits one question — where does a channel read what an
App declares — into two answers, and a third channel would have to pick one without a reason.

## Decision

A channel enumerates what an App declares from the declaration. `ToolRegistry` and `PageRegistry`
resolve a name and store nothing else that a channel reads; `ToolRegistry.definitions()` is
removed, as `PageRegistry.definitions()` already was.

Both registries are filled from a declaration that carries each name once. Filling refuses a name
declared twice, rather than replacing the earlier registration, because enumeration and
resolution no longer read the same object: a declaration listing one name twice would publish two
Tools and answer both with one.

## Consequences

- one answer to where a channel reads a declaration, and it is the same answer for both channels
  and for self-description
- a running App holds one `ToolRegistry`
- a name declared twice is a failure at registration rather than a Tool that disappears, as it
  already is for a Page
- registering a name twice no longer replaces the earlier registration through the framework's
  own path. The registries keep that behaviour for a direct caller, and no framework path reaches
  it
- an App that declared one name twice and served the last one now fails to open its window. It
  was publishing a Tool that resolved to another, which is the failure this replaces
- what a channel needs from a registry narrows to resolution, so a later channel asks it for
  nothing else
- `ToolRegistry.definitions()` is removed rather than deprecated, and it had a caller. A
  deprecation cycle was available and was not taken: nothing has ever been published from this
  repository, and a method whose only purpose was the reading this record reverses is one a later
  channel would reach for again. That makes it a compatibility event, taken on the same ground
  ADR-025 took its own — while there is no installation to break
