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

## Authoring core before Authoring MCP

Authoring semantics should exist as a channel-neutral Python service/API before being exposed through MCP.

Conceptual capabilities:

- inspect_framework
- inspect_app
- validate_app
- validate_package
- invoke_tool
- run_conformance_tests
- get_app_errors
- get_runtime_logs
- package_app

Installing, starting and stopping an App are not authoring capabilities. They belong to the
package layer, which declares them as Tools of its own; see `docs/architecture/lifecycle.md`.

## Authoring MCP

Authoring MCP is an adapter over the Authoring core.

It should not duplicate Codex's native file/code editing capabilities.

Avoid generic Tools such as:

- write_file
- create_method
- edit_python

The Authoring MCP should provide framework-specific introspection, validation, runtime control, testing, packaging, and diagnostics.

## North-star dogfooding test

A fresh Codex session should be able to use repository documentation plus Authoring MCP to build a new App, validate it, run it, test both channels, package it, and install it with minimal human intervention.
