# Architecture Overview

## Product intent

The framework lets developers or coding agents implement one application domain once and expose it through two first-class channels:

```text
Human -> NiceGUI -> Page -> ToolRuntime -> Tool -> App Domain
Agent -> MCP     -> MCP Adapter -> ToolRuntime -> Tool -> App Domain
```

The framework provides the application contract, lifecycle policy, runtime, validation, and channel adapters. An app authoring agent supplies the domain implementation.

## Core model

```text
App
├─ Manifest / metadata
├─ Tools
│  ├─ ToolDefinition
│  └─ Tool implementation
├─ Pages
│  ├─ PageDefinition
│  └─ Page implementation
└─ App domain internals
   ├─ models
   ├─ services / policies
   └─ repositories / integrations
```

The framework runtime composes these into an executable `AppRuntime`.

## Channel model

### Web channel

```text
Human
  -> Browser
  -> NiceGUI
  -> Page
  -> PageContext / ToolInvoker
  -> ToolRuntime
  -> Tool
```

### Agent channel

```text
Agent
  -> MCP client
  -> MCP server
  -> MCP adapter
  -> ToolRuntime
  -> Tool
```

Both channels converge at `ToolRuntime` and therefore execute the same backend operation path.

## Framework ownership

The framework owns:

- App / Tool / Page declarative contracts
- validation
- ToolRuntime
- execution context creation
- channel adapters
- runtime lifecycle
- package/runtime boundaries
- future permission and audit hooks

The app owns:

- domain models
- Tool implementations
- Page implementations
- internal services and policies
- repositories and domain-specific integrations

## Key distinctions

- Tool != MCP Tool. An MCP Tool is a projection of a framework Tool.
- Page != NiceGUI Page primitive. NiceGUI is the rendering/entry technology for framework Pages.
- AppDefinition != AppRuntime.
- AppRuntime lifecycle != package install/upgrade lifecycle.
- Tool public operation != every internal Python function.

## Documents

- `docs/architecture/app-model.md`
- `docs/architecture/tool-model.md`
- `docs/architecture/page-model.md`
- `docs/architecture/runtime.md`
- `docs/architecture/lifecycle.md`
- `docs/architecture/adapters.md`
- `docs/architecture/authoring.md`
- `docs/roadmap.md`
