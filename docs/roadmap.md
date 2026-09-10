# Implementation Roadmap

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

Implement `CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED` with optional on_start/on_stop hooks and deterministic cleanup.

Acceptance:
- runtime transitions through the defined lifecycle states predictably
- lifecycle hooks execute at the intended transition boundaries
- startup/shutdown failures perform deterministic cleanup


## M7 - Structured error model

Introduce machine-readable framework error codes and channel-neutral normalization.

Acceptance:
- framework failures are represented with stable machine-readable error codes
- Tool, Page, lifecycle, and adapter failures can be distinguished consistently
- channel adapters preserve the same framework error semantics


## M8 - Configuration and dependencies

Add typed app configuration and stable application-scoped dependency ownership. Keep secrets conceptually separable from config.

Acceptance:
- app configuration is validated before normal runtime use
- application-scoped dependencies are shared within one AppRuntime
- independent AppRuntime instances remain isolated by default


## M9 - App Package

Introduce manifest, entrypoint, source/dependency metadata, package validation, and AppDefinition loading.

Acceptance:
- valid packages can be inspected and validated deterministically
- invalid package metadata produces structured diagnostics
- a valid package can resolve and load its declared AppDefinition


## M10 - Hub Core

Implement headless package registry, installation registry, and runtime manager.

Capabilities: list/install/remove/start/stop/status.

Acceptance:
- Hub Core can manage package and installation lifecycle independently
- installed Apps can be started, stopped, and queried for status
- Hub lifecycle operations remain separate from App business logic


## M11 - Hub UI

Build NiceGUI management UI over Hub Core.

Acceptance:
- Hub UI exposes Hub Core lifecycle capabilities without duplicating control-plane logic
- displayed App/package state reflects Hub Core state
- Hub UI remains a thin management interface over Hub Core


## M12 - Authoring Core

Create channel-neutral framework authoring/introspection/validation/runtime control service.

Acceptance:
- authoring clients can inspect and validate Apps through a channel-neutral service
- runtime verification uses the canonical framework runtime path
- Authoring Core does not depend on MCP-specific types


## M13 - Authoring MCP

Expose Authoring Core through MCP for Codex and other coding agents.

Acceptance:
- Authoring capabilities are discoverable through MCP
- MCP calls delegate to Authoring Core rather than duplicating authoring behavior
- structured validation and runtime results are preserved through the MCP surface


## M14 - Permissions and security

Introduce Tool exposure, query/command or side-effect semantics, permissions, actor/principal propagation, and policy hooks.

Acceptance:
- unauthorized Tool calls are rejected before handler execution
- actor/principal and policy checks are enforced through the canonical ToolRuntime path
- Tool behavior remains channel-neutral while exposure and permission may vary by channel


## M15 - Observability and audit

Add invocation ids, channel/actor metadata, timing, status, structured logs, traces, and audit hooks.

Acceptance:
- canonical Tool invocations can be correlated through invocation identifiers
- channel, actor, timing, and execution status are observable
- observability applies consistently across Web- and Agent-originated Tool calls


## M16 - App conformance validation

Validate manifest, declarations, handlers, routes, Tool references, config, exposure, and lifecycle consistency with structured diagnostics.

Acceptance:
- conforming Apps pass validation deterministically
- invalid declarations and references produce actionable structured diagnostics
- conformance validation remains independent of channel-specific implementations


## M17 - Enterprise isolation

Define and implement appropriate isolation modes for multiple installed apps: dependency, process, filesystem, network, resource limits as required.

Acceptance:
- installed Apps can execute without unintended dependency or process sharing
- failure of one isolated App does not compromise another App runtime
- isolation does not change the App / Tool / Page programming contract


## M18 - Codex dogfooding

A fresh Codex session builds an Issue Tracker app using docs + Authoring MCP, validates, runs, tests, packages, and installs it.

Acceptance:
- a fresh coding agent can complete the intended App authoring loop using Vibepy guidance and Authoring MCP
- the resulting App follows App / Tool / Page architectural invariants
- the App can be validated, run, tested, packaged, and installed through the supported framework flow


## M19 - Connector dependencies and optional Skills

Add portable external capability metadata such as email.search/calendar.search/document.search and generate Agent/MCP guidance. Skills remain optional and outside MVP core unless proven necessary.

Acceptance:
- Apps can declare provider-neutral external capability dependencies
- required/optional capability semantics can be surfaced to Agents
- connector dependencies do not require external provider-specific logic in the core App model


## M20 - Production hardening

Add timeouts, idempotency, rate limits, retries where appropriate, graceful shutdown, health checks, migrations/compatibility, signed packages/security scanning, and operational hardening.

Acceptance:
- runtime execution is bounded and shuts down gracefully
- health, compatibility, and security failures are surfaced deterministically
- production hardening preserves the canonical ToolRuntime execution path
## Apps

The Apps this repository carries. They live in `fixtures/`, because each one is
a distribution the tests install and no document yet walks a reader through
one; an example is a documentation artifact and is derived when there is a
document to derive it from.

### Todo

Used from M1 through early Hub work to prove framework architecture. Both
channels, a secret it uses, and a store outside its environment.

Tools:

- create_todo
- list_todos
- complete_todo

Page:

- /todos

### Notes

Tools and no Pages, so no Web channel at all (ADR-017) and no Web technology
installed (ADR-025). Declares a secret. The lightest App the suite installs.

### Timer

A second App with a Web channel, because one address per App cannot be shown
with one App. Requires nothing of its host, and its lifespan holds the one
thing it knows.

### Customer

Used for richer Tool semantics, query/command, Page composition, permissions, and user context.

### Expense

Used for enterprise approval, actor/role, audit, and Agent exposure policy.
