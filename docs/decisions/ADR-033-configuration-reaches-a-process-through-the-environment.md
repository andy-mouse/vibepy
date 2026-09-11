# ADR-033: Configuration reaches a process through the environment

Status: Accepted; answers the question ADR-022 left open, and supersedes ADR-026's stdin sentence

## Context

ADR-022 made an App's configuration a declaration and stopped there: "Where that mapping comes
from is not decided here … choosing among them belongs to the installation model." Two commands
answered it in code without a record. ADR-026 gave `serve` its configuration on standard input as
a consequence of deciding something else, with no alternative weighed; `invoke` followed it; and
Studio kept it for a reason of its own, written in `Processes.start`: standard input carried the
configuration "so that a secret reaches the child without a file, an environment variable or an
argument vector."

Opening the Agent channel closes the question, because over stdio standard input is the
transport. The MCP specification says the client "launches the MCP server as a subprocess", that
the server "**MUST NOT** write anything to its `stdout` that is not a valid MCP message", that
the client likewise must not write anything but MCP messages to the server's `stdin`, and that
`stderr` "MAY be used ... for logging purposes"
(<https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>). The channel this
framework most wants to reach cannot be configured the way the other two are, and a rule that
holds for two commands out of three is not a rule.

The ecosystem the Agent channel joins has already answered. Codex configures a server as
`[mcp_servers.<name>]` with `command`, `args` and `env`
(<https://learn.chatgpt.com/docs/extend/mcp?surface=cli>). Claude Code configures the same three
keys in `.mcp.json`, expands `${VAR}` in them, and recommends that secrets be passed through
`env` (<https://code.claude.com/docs/en/mcp>). The MCP Registry's `server.json` has a server
declare its configuration as `environmentVariables[]` — each with a name, `isRequired` and
`isSecret` — and `packageArguments[]`, one entry per value
(<https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/generic-server-json.md>).
Twelve-factor states the same shape for the same reason: configuration belongs in the
environment, and each variable is "fully orthogonal to other config vars" rather than grouped
into one blob (<https://12factor.net/config>).

The counter-argument is the one Studio wrote down. OWASP's Secrets Management Cheat Sheet §5.1
says environment variables are "generally accessible to all processes and may be included in
logs or system dumps", and that their use is "not recommended unless the other methods are not
possible"
(<https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html>). The
other methods it names are a mounted secrets file and a secret store. A stdio server that an
agent platform launches on a developer's machine has neither: there is no orchestrator to mount
a file and no store the client knows how to read, and the clients that would launch it document
`env` as the way to hand it a secret.

## Decision

Every framework command reads its App's configuration from its own environment, one variable per
declared field, named `VIBEPY_<FIELD>`.

The reading is pydantic-settings', not the framework's. It is Pydantic's own answer to the
question ADR-022 left open, and it covers the whole of it: one variable per field, a prefix,
environment variable names that are case-insensitive by default, complex types and sub-models
read "by treating the environment variable's value as a JSON-encoded string", and a defined
priority in which initialisation keyword arguments stand above the environment, which stands
above a dotenv file, secrets and defaults
(<https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/>). Because that
behaviour belongs to `BaseSettings` and not to `BaseModel`, the framework owns the base class an
App subclasses — `AppConfig`, carrying `env_prefix="VIBEPY_"` in its `model_config` — and
`ConfigT`'s bound narrows from `BaseModel` to it. The prefix is part of the declaration rather
than of a call site, so a declaration reads the same variables wherever it is instantiated and
no caller can forget the policy.

A window instantiates the declaration instead of validating a mapping against it, so what a
caller hands it explicitly stands above the environment field by field, in the library's
documented order. `vibepy-core` depends on `pydantic-settings`.

Configuration on standard input is removed for `serve` and `invoke`. `invoke`'s `input` is
per-call data and is unaffected. The command that opens the Agent channel has no stdin channel at
all.

Rejected, and why:

- **standard input**, the incumbent: unavailable to the one channel that most needs a rule.
- **one JSON object in one variable or one argument**: grouped configuration, which 12-factor
  argues against and which no client or registry schema models. Every one of them declares
  configuration as individual variables.
- **a file path**: reintroduces a file a host would have to write and clean up, when the
  platforms already offer `env`.
- **a reader written by the framework**: pydantic-settings is the library's own, and writing a
  second one would put two answers to the same question in a project that already depends on
  Pydantic.
- **the prefix given at each call site** (`_env_prefix=` on instantiation, which the library
  also offers): the policy would then live at every call site instead of in the declaration.

## Consequences

- one configuration channel serves all four commands, and the Agent channel can be configured at
  all
- a declaration reads its host when it is instantiated. ADR-022's statement that the framework
  "reads no environment" no longer holds; that is what this record changes
- secrets reach a child through the environment, against OWASP's preference and with the MCP
  ecosystem's. What bounds the exposure is what a launcher lets a child inherit, which in this
  repository is Studio's `child_environment`
- a value for a field an App does not declare is now refused where it was silently ignored,
  because `BaseSettings` forbids extra keys; a misspelt field fails when the window opens
- `vibepy-core` depends on `pydantic-settings`, a Pydantic project already in the tree's shape
- the `VIBEPY_` namespace of an App process's environment belongs to configuration, and the
  framework claims no other variable in it
- the stdin channel is removed with this decision rather than deprecated, no installation of
  this framework existing outside this repository to have sent it
