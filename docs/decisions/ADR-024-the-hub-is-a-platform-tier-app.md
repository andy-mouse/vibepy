# ADR-024: The Hub is a platform-tier App

Status: Accepted

## Context

The Hub installs, starts, stops and lists other Apps. Nothing said what the Hub itself is, and
ADR-017 names it as an actor outside the App model because no other reading existed when it was
written.

Building a control plane beside the framework would mean a second way to declare an operation, a
second place for application-scoped state, and a second error model — each one an answer the
framework already has.

## Decision

The Hub is an App, built on the framework like any other. Its capabilities are Tools, its state
is what a lifespan yields, and what it requires of its host is a configuration declaration.

It is a platform-tier App rather than a domain one: it depends on the framework, and the
framework never depends on it. It therefore ships as its own distribution, so that an installed
App's environment holds the framework and that App and never a control plane.

Authoring takes the same position when it arrives.

## Consequences

- the Hub's Tools are its whole public surface, and the work behind them — installing, reading a
  folder, holding a child process — is domain internals that no channel reaches
- a Hub UI consumes those Tools as any Page consumes Tools, so it cannot duplicate control-plane
  logic
- an installed App's dependency tree never grows a control plane's
- the Hub is subject to every rule an App is subject to, including that an application-scoped
  resource is share-nothing
