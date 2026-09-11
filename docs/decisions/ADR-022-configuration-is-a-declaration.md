# ADR-022: Configuration is a declaration

Status: Accepted; the source of the mapping decided by ADR-033

Amendment, appended: `ConfigT` is bound by `AppConfig`, a `BaseSettings`, since ADR-033; the
framework reads the environment through it.

## Context

An App needs values from its host: a database path, an API token, a limit. Today it has nowhere
to say so. The only place a value can enter is the lifespan, which reads the environment inside
its own body. That has three consequences.

Nothing can answer what an App requires without running it. A lifespan is a callable, so
inspecting it yields a signature and not a statement. ADR-021 removed the factory from the
declaration precisely so that a definition could be read rather than called, and left "what an
App declares *about* its host" as the one real declaration still missing.

A missing value fails outside the error model. `os.environ["DB_PATH"]` raises `KeyError` from
inside the App's own code, after the window has begun opening. ADR-019 gives every framework
failure a stable code and a category; a configuration failure had neither.

Every App would validate differently. Reading and coercing values is the same work in every
App, and each one doing it by hand is the repetition ADR-007 rejected for Tool output.

Pydantic already models this. A `BaseModel` subclass is a readable type, `model_validate`
coerces and reports every failure at once, `model_json_schema` projects it, and `SecretStr`
separates a secret from an ordinary string by type rather than by storage
(<https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr>). The framework already
depends on it for Tool input and output.

## Decision

`AppDefinition` declares `config: type[ConfigT]`, a Pydantic model, alongside identity, Tools
and Pages. The declaration is required: an App that requires nothing of its host declares
`NoConfig`, an empty model, rather than omitting the field.

`Lifespan` takes that validated model as its only argument.

A window validates a raw mapping against the declaration before it enters the lifespan.
`tool_runtime_for` and `page_runtime_for` take `config` as a keyword-only mapping, validate it,
and raise `AppConfigInvalidError` — code `config.invalid`, category `caller` — naming every
field that failed. A window that cannot run acquires nothing.

Where that mapping comes from is not decided here. A file, an environment, a Hub's stored
settings and a test literal are all one mapping, and choosing among them belongs to the
installation model.

## Consequences

- what an App requires of its host is readable without acquiring anything, which is what an
  entrypoint's self-description projects. See `docs/architecture/packaging.md`
- one validation path serves every App, and a configuration failure carries a code and a
  category like every other framework failure
- a secret is distinguished by its declared type. `SecretStr` masks itself in `repr` and `str`,
  so an App that declares one cannot disclose it by logging its configuration. The framework
  stores nothing and reads no environment, so it defines no secret storage
- an App's configuration model is part of its public contract, and changing it is a
  compatibility question for the App rather than for the framework
- **no per-invocation resource scope is introduced.** `docs/architecture/app-model.md` left that
  decision to M8, and the answer is no. A ToolContext carries the application-scoped value, and
  adding a second resource mechanism beside it would put two answers in the codebase to the
  question of where a handler's resource comes from, which is what ADR-013 settled. No milestone
  requires one. An App that needs a session per call takes one from the pool its
  application-scoped resource holds
