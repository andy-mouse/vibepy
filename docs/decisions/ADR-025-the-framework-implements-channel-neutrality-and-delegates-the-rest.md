# ADR-025: The framework implements channel neutrality and delegates the rest

Status: Accepted

## Context

Nothing states what this framework builds for itself and what it adopts, so every milestone
answers that question again and answers it differently. A full review of the repository found
both answers side by side: package discovery delegates to `importlib.metadata`, installation
shells out to `uv`, and the Agent channel is the MCP SDK's own server — while the Hub supervises
child processes, chooses free ports and persists its state through mechanisms written here, none
of which has a stated reason for existing.

The same silence has a second cost. `vibepy-core` depends on the SDKs of both channels, so an App
declaring no Pages installs a web stack it never serves. A framework whose core has no channel
cannot express that, because no document says the core has no channel.

There is one capability no library supplies. A Tool that is defined once and is equally native to
a human channel and an agent channel is what this framework exists for; `docs/architecture.md`
carries what that means. Everything else it does — serving HTTP, speaking MCP, rendering a page,
creating an environment, reading distribution metadata — is a solved problem with an owner.

FastAPI and FastMCP are the shape to aim at, and the reason is not their feature lists. Each is
authoritative because it is small enough to hold in mind, starts without ceremony, and does not
ask its user to learn a private mechanism where a standard one exists.

## Decision

The framework implements channel neutrality. Where an authoritative library or the standard
library already covers a problem, the framework delegates to it rather than writing its own, and
a mechanism written here carries the argument for why no library covers it.

The product is three distributions, and no more:

| Distribution | Import package | Installed with an App |
| --- | --- | --- |
| `vibepy-core` | `vibepy_core` | yes |
| `vibepy-hub` | `vibepy_hub` | no |
| `vibepy-builder` | `vibepy_builder` | no |

`vibepy-core` declares no channel. A channel's SDK is an extra of it: `vibepy-core[web]` carries
the Web technology, `vibepy-core[agent]` carries MCP, and an App declares the channels it offers.

## Consequences

- ADR-009 stands, and for this reason rather than in spite of it. The SDK's high-level server
  derives a Tool's schema from a Python function signature, which would make the SDK the source
  of truth for what a Tool is — the one thing this decision protects. Delegation stops where it
  would take channel neutrality with it, and that is the only place it stops
- an App declaring no Pages installs no Web technology, which is what makes `samples/notes` an
  Agent-only App in its dependency tree and not merely in its declaration
- the environment-per-App model stays. `docs/architecture/packaging.md` states what it buys, and
  it is `uv venv` and `uv pip install` — delegation already. What is worth removing around it is
  the mechanism written here, not the delegation
- a reverse proxy, a process supervisor and a state store are things to adopt, not to write. The
  Hub owning any of them requires the argument this decision now demands
- the extras split is a published interface. An App that names `vibepy-core` alone gets neither
  channel, so the split is a compatibility event for every existing App and is taken while there
  are three
- `vibepy-builder` does not exist yet; `docs/roadmap.md` M12 and M13 own it. This decision fixes
  its name and its place, and creating it before those milestones would be building ahead
