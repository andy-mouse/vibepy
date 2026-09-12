# Agent Authoring Architecture

## Goal

The framework is designed so a coding agent such as Codex can implement App domains through an iterative development loop.

The agent is not merely a one-shot code generator.

```text
inspect -> design -> implement -> validate -> run -> test -> observe -> repair
```

Authoring is one half of an App's lifecycle. `docs/architecture/lifecycle.md` owns both layers of
that life, and the package layer is where an App that exists is installed, addressed, started and
reached.

## Framework responsibility

The framework should provide deterministic feedback surfaces for agents:

- structural validation
- type validation
- runtime errors
- policy/conformance errors
- Tool invocation tests
- package validation

Diagnostics should be machine-readable whenever practical.

## Authoring Core

Authoring is the Agent channel of Studio, the platform-tier App that also carries operation; see
`docs/decisions/ADR-032-authoring-is-studios-agent-channel.md`. Its capabilities are Tools, so
they are channel-neutral like every Tool and reach an agent through MCP as any App's Tools do.

The App being authored is a source project: a directory holding a `pyproject.toml`, with no wheel
and no installation. Studio never imports it. It runs the framework's own commands in the
project's environment — `uv run --project <dir> python -m vibepy_core.describe|invoke` — and
reads what they write; `docs/architecture/packaging.md` owns those commands. The Apps a project
answers for are those its `[project].name` declares.

| Tool | Answers |
| --- | --- |
| `inspect_framework` | what `vibepy_core` asserts about itself: version, entry point group, channel extras, error catalogue. Read by import; carries no documentation |
| `inspect_app` | the project's Apps with every Tool schema, Page and configuration schema — or the framework's own diagnostic when the declaration will not load |
| `invoke_tool` | one Tool of one App, invoked once through the framework's invocation window, with configuration supplied by the caller |

All three are declared on the Agent channel alone. Studio's operating Tools —
`list_apps`, `describe_config`, `install_app`, `remove_app`, `update_app`, `configure_app`,
`start_app`, `stop_app`, `register_package_source`, `remove_package_source` — are declared on
the Web channel alone, so an agent connected to Studio neither sees them nor can call them by
name. This is the outcome
`docs/decisions/ADR-032-authoring-is-studios-agent-channel.md` deferred: exposure is a field of
each declaration, and `docs/architecture/tool-model.md` owns what it means.

`invoke_tool` names its App explicitly and does not filter by the project's `[project].name` as
`inspect_app` does, so in a workspace whose members share one environment it can reach a sibling's
App; the environment is still the project's.

`invoke_tool` forwards its own `ctx.channel` and `ctx.principal` to the command it runs, so a
call an agent verifies through Studio is authorized exactly as the agent's own call would be,
and Studio grants nothing it was not given.

Inspection and validation are one Tool: what the framework validates today is that a declaration
loads, and that is the failure path of describing. A failure the project's environment reports
travels with its own code and category; authoring's own diagnostics are the `authoring.*`
vocabulary that `vibepy_studio/authoring/models.py` defines.

Studio keeps no authoring state. The Web channel of a project is opened by the agent with
`python -m vibepy_core.serve` under `uv run`; the Agent channel's server command is
`python -m vibepy_core.mcp`.

| Conceptual capability | Where it lives |
| --- | --- |
| inspect_framework, inspect_app, validate_app, invoke_tool | Studio, M12 (`validate_app` is `inspect_app`'s failure path until M16) |
| validate_package, package_app | `uv build`, the agent's own; M9's `describe` reads the result |
| run_conformance_tests | M16 |
| get_app_errors, get_runtime_logs | M15 |

## Authoring MCP

Authoring MCP is Studio's Agent channel served over MCP. It exists: an agent platform launches
`python -m vibepy_core.mcp studio`, the entry-point name the App is declared under, with
Studio's own interpreter and reaches these Tools as it reaches any App's. The configuration that
command takes, and what each platform's own file looks like, are `docs/architecture/packaging.md`'s.

It should not duplicate Codex's native file/code editing capabilities.

Avoid generic Tools such as:

- write_file
- create_method
- edit_python

The Authoring MCP should provide framework-specific introspection, validation, testing and
diagnostics. Building a package is not among them: an App is a standard distribution and
`uv build` is the agent's own command, as the table above records. What the framework owns is
reading and validating what a build produced.

## North-star dogfooding test

A fresh Codex session should be able to use repository documentation plus Authoring MCP to build a new App, validate it, run it, test both channels, package it, and install it with minimal human intervention.
