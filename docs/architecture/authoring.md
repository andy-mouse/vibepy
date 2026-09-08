# Agent Authoring Architecture

## Goal

The framework is designed so a coding agent such as Codex can implement Plugin domains through an iterative development loop.

The agent is not merely a one-shot code generator.

```text
inspect -> design -> implement -> validate -> run -> test -> observe -> repair
```

## Framework responsibility

The framework should provide deterministic feedback surfaces for agents:

- structural validation
- type validation
- runtime errors
- policy/conformance errors
- plugin status
- Tool invocation tests
- package validation

Diagnostics should be machine-readable whenever practical.

## Authoring core before Authoring MCP

Authoring semantics should exist as a channel-neutral Python service/API before being exposed through MCP.

Conceptual capabilities:

- inspect_framework
- inspect_plugin
- validate_plugin
- validate_package
- start_plugin
- stop_plugin
- plugin_status
- invoke_tool
- run_conformance_tests
- get_plugin_errors
- get_runtime_logs
- package_plugin
- install_package

`start_plugin`, `stop_plugin` and `plugin_status` describe the Web channel window the Hub owns. A
process the agent platform spawned is not one the Hub started. See
`docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md`.

## Authoring MCP

Authoring MCP is an adapter over the Authoring core.

It should not duplicate Codex's native file/code editing capabilities.

Avoid generic Tools such as:

- write_file
- create_method
- edit_python

The Authoring MCP should provide framework-specific introspection, validation, runtime control, testing, packaging, and diagnostics.

## North-star dogfooding test

A fresh Codex session should be able to use repository documentation plus Authoring MCP to build a new Plugin, validate it, run it, test both channels, package it, and install it with minimal human intervention.
