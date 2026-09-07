# Implementation Roadmap

Codex may read the entire roadmap for context, but must implement only the milestone in `docs/work/current-task.md`.

## M0 - Architecture baseline

Establish repository structure, core architecture documents, ADRs, test harness, and minimal importable Python package skeleton.

## M1 - Tool Core

Implement:

- ToolDefinition
- Tool
- ToolHandler Protocol
- ToolContext
- ToolRegistry
- ToolRuntime

Acceptance: raw input -> validation -> async handler -> validated output; deterministic unknown/input/output errors.

## M2 - Page Core

Implement:

- PageDefinition
- Page
- PageHandler Protocol
- PageContext
- ToolInvoker
- PageRegistry
- PageRuntime

Acceptance: a test Page invokes an existing Tool through the narrow ToolInvoker interface.

## M3 - MCP Adapter

Use the official MCP Python SDK.

Acceptance:

- framework Tools appear in MCP discovery
- MCP schema derives from ToolDefinition/Pydantic
- MCP calls go through ToolRuntime
- MCP SDK types do not leak into core Tool model

## M4 - NiceGUI Adapter

Expose framework Pages through NiceGUI.

Acceptance:

- PageDefinition becomes a Web route
- PageHandler receives PageContext
- Page interaction invokes Tools through ToolRuntime
- dual-channel Todo proof works

## M5A - AppRuntime and shared state

Implement:

- AppDefinition
- AppRuntime
- application-scoped typed dependencies
- ToolContext creation from AppRuntime

Acceptance: Web-like and Agent-like calls share the same AppRuntime state; a second AppRuntime is isolated by default.

## M5B - Execution semantics

Formalize async-first concurrent Tool execution.

Acceptance:

- concurrent independent Tool calls execute without global serialization
- each invocation has independent ToolContext
- app-scoped dependencies remain shared

## M6 - Runtime lifecycle

Implement CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED with optional on_start/on_stop hooks and deterministic cleanup.

## M7 - Structured error model

Introduce machine-readable framework error codes and channel-neutral normalization.

## M8 - Configuration and dependencies

Add typed app configuration and stable application-scoped dependency ownership. Keep secrets conceptually separable from config.

## M9 - App Package

Introduce manifest, entrypoint, source/dependency metadata, package validation, and AppDefinition loading.

## M10 - Hub Core

Implement headless package registry, installation registry, and runtime manager.

Capabilities: list/install/remove/start/stop/status.

## M11 - Hub UI

Build NiceGUI management UI over Hub Core.

## M12 - Authoring Core

Create channel-neutral framework authoring/introspection/validation/runtime control service.

## M13 - Authoring MCP

Expose Authoring Core through MCP for Codex and other coding agents.

## M14 - Permissions and security

Introduce Tool exposure, query/command or side-effect semantics, permissions, actor/principal propagation, and policy hooks.

## M15 - Observability and audit

Add invocation ids, channel/actor metadata, timing, status, structured logs, traces, and audit hooks.

## M16 - App conformance validation

Validate manifest, declarations, handlers, routes, Tool references, config, exposure, and lifecycle consistency with structured diagnostics.

## M17 - Enterprise isolation

Define and implement appropriate isolation modes for multiple installed apps: dependency, process, filesystem, network, resource limits as required.

## M18 - Codex dogfooding

A fresh Codex session builds an Issue Tracker app using docs + Authoring MCP, validates, runs, tests, packages, and installs it.

## M19 - Connector dependencies and optional Skills

Add portable external capability metadata such as email.search/calendar.search/document.search and generate Agent/MCP guidance. Skills remain optional and outside MVP core unless proven necessary.

## M20 - Production hardening

Timeouts, idempotency, rate limits, retries where appropriate, graceful shutdown, health checks, migrations, compatibility, signed packages/security scanning, and operational hardening.

## Sample apps

### Todo

Used from M1 through early Hub work to prove framework architecture.

Tools:

- create_todo
- list_todos
- complete_todo

Page:

- /todos

### Customer

Used for richer Tool semantics, query/command, Page composition, permissions, and user context.

### Expense

Used for enterprise approval, actor/role, audit, and Agent exposure policy.
