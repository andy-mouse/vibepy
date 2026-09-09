# ADR-029: An App's expected failures travel as data

Status: Accepted

## Context

The Hub answers a caller who asked for something it will not do — an App that is not installed, a
source that offers nothing, an environment that is already serving — with a `Diagnostic` carried
inside its own output model. That vocabulary was invented without a record.
`docs/milestones/code-review/decisions.md` lists it among three decisions that were live and
undocumented, and no record in `docs/decisions/` mentions it.

`docs/architecture/errors.md` defines the framework's failure model: an exception derived from
`VibepyError`, normalized to an `ErrorInfo` of `code`, `category`, `message` and `details`, which
each channel renders in its own idiom. That document is silent on an App's own expected failures.
So the review reached one question from two sides — axis 4 asking what a Hub diagnostic is, and
axis 7 asking why a Hub failure has no category — and neither had a document to answer it.

A `Diagnostic` also carried no category, which is the field a caller reads to learn whether a
different call could succeed. Nothing distinguished "you asked for the wrong App" from "the
installer broke".

## Decision

An App's expected, actionable failure travels as data inside its own output model, carrying the
same `code`, `category`, `message` and `details` an `ErrorInfo` carries. The category is required
rather than defaulted.

The framework's code table stays the framework's. An App publishes its own codes.

## Consequences

- a renderer and an agent read one shape for both kinds of failure, whether it arrived as an
  exception the framework normalized or as data an App returned
- an App publishes codes the framework's table does not own, and is responsible for documenting
  them
- a category is required, so no construction site inherits a guess. Every existing Hub diagnostic
  had to state one
- raising for an expected failure was rejected. Every actionable Hub answer would become a
  protocol error on the Agent channel, and per ADR-007 an exception instance cannot travel inside
  a revalidated output model at all
- an unexpected failure is unaffected: it is still an exception, still normalized by the
  framework, still rendered by the channel
