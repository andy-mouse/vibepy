# ADR-032: Authoring is Studio's Agent channel

Status: Accepted; supersedes the distribution table of ADR-025

## Context

ADR-025 fixed the product as three distributions: `vibepy-core`, `vibepy-hub`, and a
`vibepy-builder` to carry authoring when M12 arrived. ADR-024 had already placed authoring in the
Hub's position — a platform-tier App built on the framework.

Two platform-tier Apps would each be one App with one channel in use: the Hub consumed through
Pages by humans, the builder consumed through Tools by agents. The framework's own claim — one
App, one set of Tools, two first-class channels — would be true of neither.

An App's life has two halves, authoring and consumption (`docs/architecture/authoring.md`,
`docs/architecture/lifecycle.md`). They share what a host needs to read an App without importing
it: running the framework's commands in the App's environment and reading one shape of report.

## Decision

One platform-tier App, `vibepy-studio`, carries both halves. Consumption is its Web channel —
the board, for humans. Authoring is its Agent channel — Tools over MCP, for coding agents. Its
`app_id` is `vibepy-studio`, which is also the name its MCP server answers to.

The product is two distributions: `vibepy-core` and `vibepy-studio`. `vibepy-builder` is not
created. `vibepy-hub` is renamed, not kept beside it.

## Consequences

- the Hub's Tools, state and vocabulary are Studio's consumption role and keep the name Hub where
  a human sees it; the Studio's package is organised by role, `consumption` and `authoring`
- until per-channel exposure exists (`docs/roadmap.md` M14), every Studio Tool appears on both
  channels; M14 decides exposure with the authoring loop of M18 as its measure
- an installed App's environment holds the framework and that App, and never Studio — as ADR-024
  already required of the Hub
- the mechanisms both roles share — a child-process runner, a describer, a failure reader — are
  written once in Studio's shared internals, which is what having one App buys
