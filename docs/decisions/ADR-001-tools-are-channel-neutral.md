# ADR-001: Tools are channel-neutral canonical backend operations

Status: Accepted

## Context

The same application domain must be usable by humans through Web UI and by agents through MCP.
Which channel owns the definition of an operation decides everything after it.

Channel-first is the obvious answer and the one the ecosystem pushes toward. An MCP SDK turns a
Python function into a Tool with a decorator, so the Agent channel can define what an operation
is and the Web channel can call it through a wrapper. It is less code on the day it is written.
What it costs is the direction of the dependency: the operation's schema, its argument coercion
and its result shape all become the SDK's, and the Web channel receives a projection of a
protocol it does not speak. A second agent protocol, or a channel that is neither, then has
nowhere to attach.

Two parallel backends is the other answer and the one a Web-first team reaches by default. It
costs the same operation twice, and the two drift.

## Decision

Framework Tools are application-level backend operations independent of transport/channel.

MCP Tools are projections of framework Tools. Pages invoke the same framework Tools through ToolRuntime.

## Consequences

- business operations are implemented once
- MCP SDK types cannot define the framework Tool model
- Page business state changes must go through Tools
- future channels can reuse the same Tool surface
