# ADR-002: Pages consume Tools

Status: Accepted

## Context

The Web channel must not create a second backend business-logic path separate from the Agent channel.

## Decision

Pages implement human interaction and compose/invoke Tools through a framework Tool invocation interface.

Pages do not bypass Tools for business state mutation.

## Consequences

- Web and Agent channels converge on ToolRuntime
- Page code remains presentation/interaction oriented
- shared backend behavior is testable across channels
