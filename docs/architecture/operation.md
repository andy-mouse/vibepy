# App Operation Architecture

## Goal

An App that exists is not yet an App anyone can use. Operation is the half of an App's lifecycle
that begins where authoring ends: an App is installed into an environment of its own, given an
address, configured, started, stopped and reached.

`docs/architecture/authoring.md` owns the other half. Neither owns the core model, which
`docs/architecture/app-model.md`, `tool-model.md` and `page-model.md` own.

## Framework responsibility

The framework operates nothing. It provides what an operator needs and stops there:

- a declaration a host can read without importing the App
- a command that describes an environment's Apps, and a command that opens an App's Web channel
- a window that reports its own failure rather than leaving a server answering for nothing
- failures that carry a stable code and a category across a process boundary

`docs/architecture/packaging.md` owns the first two, `docs/architecture/errors.md` the last.

## Operation core before any channel

Operation is an App built with this framework, not a capability inside it. See
`docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md`. Its capabilities are therefore
Tools, which makes them reachable from either channel and neutral between them.

The capabilities that exist today, as the Hub declares them:

- `register_package_source`, `remove_package_source` — where the operator looks for Apps
- `list_apps` — what is known, what is installed, what is running
- `install_app`, `remove_app` — an environment of its own per App, created and destroyed
- `configure_app` — the configuration an App's window validates against its own declaration
- `start_app`, `stop_app` — the Web channel window of an installed App

## What an operated App is described by

Three vocabularies, defined in `vibepy_hub/models.py` and not restated here:

- **state** — `available` for an App the operator knows of, `installed` for one whose environment
  exists, `running` for one whose Web channel is serving
- **address** — derived from the App's canonical distribution name and the proxy's port, and
  present from installation rather than from start. See
  `docs/decisions/ADR-028-an-app-is-addressed-by-its-distribution-name.md` and
  `docs/decisions/ADR-031-the-proxy-is-traefik.md`
- **diagnostic** — a `hub.*` code, its category, a message and details, returned as data where a
  failure is one the operator expects. See
  `docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md`

## The current implementation

The Hub, `packages/vibepy-hub`. An environment per App, so no App's dependencies constrain
another's; a proxy in front, so an App is reached by name without knowing it is proxied.

## What operation must not become

- it must not run the business logic of the Apps it operates
- it must not import an App it operates; it reads declarations across a process boundary
- it must not own the proxy, the supervisor or the package installer it delegates to
- it must not offer generic data mutation where a business operation is what an operator means

## North-star test

An operator installs an App from a folder, configures it, starts it, and reaches it at an address
of its own — and nothing in that App's code exists because of how it was served.
