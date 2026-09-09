# ADR-002: Pages consume Tools

Status: Accepted

## Context

ADR-001 puts the canonical operation in a Tool. That settles what a Tool is and leaves open what a
Page may do, and the Web channel is where the pressure to answer differently comes from.

A Page has a session, a form and a rendering loop, none of which a Tool models. The natural place
to put the work those need is a service the Page calls directly — a repository read to fill a
table, a small write to record a preference — with Tools kept for what the Agent channel exposes.
Each such call is defensible on its own and none announces itself as a second backend. Their sum
is one: the two channels then disagree about what an operation does, and no test can catch it,
because each channel passes its own.

The alternative is to give a Page one way to reach the domain and no other, which costs the Page
the convenience above.

## Decision

Pages implement human interaction and compose/invoke Tools through a framework Tool invocation interface.

Pages do not bypass Tools for business state mutation.

## Consequences

- Web and Agent channels converge on ToolRuntime
- Page code remains presentation/interaction oriented
- shared backend behavior is testable across channels
