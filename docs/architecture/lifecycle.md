# Lifecycle Architecture

An App's life has two layers, and the framework owns one of them.

| Layer | What it covers | Whose it is |
| --- | --- | --- |
| runtime lifecycle | a channel's running window, from opening to closing | the channel host |
| package lifecycle | a distribution installed, configured, addressed, started and stopped | a host App built on the framework, never the framework (Studio's consumption role, called the Hub) |

What the framework implements is channel neutrality, and where a problem already has an owner it
delegates; see
`docs/decisions/ADR-025-the-framework-implements-channel-neutrality-and-delegates-the-rest.md`
and `docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md`. That is why nothing of
installation is published from it.

## Runtime lifecycle

The framework owns no runtime lifecycle object and no lifecycle state. A channel's runtime exists
for the duration of an `async with` block and cannot be reached outside it, so there is no state
in which an App is constructed but not running, and no transition to validate. See
`docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md`.

Each channel opens its own window, and neither depends on the other. The host that opens a window
is the channel's own host. The Agent channel's window is opened by the MCP SDK, which enters the
lifespan inside `run()`; over stdio the client launches one server process, so that window is the
process. The Web channel's window is opened by the ASGI server inside the process the package
layer starts. See
`docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md`.

## The lifespan

An App's application-scoped resource is declared as a factory returning an async context
manager, supplied to a channel at composition time rather than inside the declaration. What
precedes the `yield` runs as the window opens; what follows runs as it closes.
`docs/architecture/app-model.md` carries the signatures.

There are no separate start and stop hooks. Binding acquisition to release is what lets a channel
release a resource whose type it does not know, and it is why release cannot be a second
declaration an App might omit. See
`docs/decisions/ADR-020-the-channel-host-owns-the-runtime-lifecycle.md`.

## Cleanup

Cleanup is the language's, not the framework's. Entering a window is a stack and leaving it pops
that stack: `async with` places an acquisition outside its own `try`, so an acquisition that
raises never reaches its release and is itself responsible for leaving nothing behind, and an
`AsyncExitStack` registers a release only after its acquisition returns.

| Failure | Unwound |
| --- | --- |
| entering the lifespan raises | nothing was acquired |
| a resource inside the lifespan fails after an earlier one was acquired | the lifespan releases the earlier one |
| the lifespan raises on exit | nothing further is owned |

The error reaches the caller in every row. The framework neither swallows it nor classifies it: a
failing lifespan is the host's to report, and the host's own contract already covers that.
`docs/architecture/adapters.md` owns what a window reporting its own failure means, and
`docs/architecture/errors.md` owns the failure model it reports through.

## Package lifecycle

The steps run in order:

```text
Package -> install -> address -> configure -> open a channel
```

`configure` is the host supplying the values the App declared it requires; the Hub holds those
values per installation, secrets included, and gives a secret's value back to no channel: it
reports such a field as set. What it holds is restricted to its owner by whatever access control
its platform gives a file; `vibepy_studio/internals/files.py` owns the mechanism. The App's
own window validates them as it opens, so a configuration failure happens before anything is
acquired;
`docs/architecture/app-model.md` carries that boundary. `docs/architecture/packaging.md` owns the
step before it — how a Host learns which App a distribution contains and what it requires, and
what commands exist for it.

Operations such as install, remove, upgrade, and version migration belong to the package/Hub
control plane. The Hub also opens the Web channel's window, which it does by running
`python -m vibepy_core.serve` with the App environment's interpreter; starting and stopping an App
is starting and stopping that process, and no window is reached from outside itself. See
`docs/decisions/ADR-017-each-channel-runs-in-its-own-process.md` and
`docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md`.

### This layer's capabilities

Because the layer is an App rather than a capability inside the framework, its capabilities are
Tools, which makes them reachable from either channel and neutral between them. Ten exist, as
the Hub declares them.

| Tools | What they act on |
| --- | --- |
| `register_package_source`, `remove_package_source` | the one folder of wheels the Hub installs from |
| `list_apps` | what is offered, what is installed, what is running, and what is newer |
| `install_app`, `update_app`, `remove_app` | an environment of its own per App: created, remade at a newer version, destroyed |
| `describe_config`, `configure_app` | the values an App runs with, read and written |
| `start_app`, `stop_app` | the Web channel window of an installed App |

An update keeps what the Hub holds for an App — its configuration values, its port, its route —
and remakes only the environment. A running App is refused rather than restarted.

The Hub's Web channel is one Page, `board` at `/`, over these Tools and nothing else: it reads
`list_apps` and redraws on a timer, so what it shows is Hub Core's state rather than the last thing
that tab did.

### How an installed App is described

A state is one of three: `available` for an App a registered source offers, `installed` for one
whose environment exists, `running` for one whose Web channel this Hub has started. `AppRow.state`
in `vibepy_studio/consumption/models.py` publishes the three values.

An address belongs to an App only if it declares Pages. `install_app` allocates a port and
publishes a route for such an App and answers with its address; an App declaring no Pages has no
Web channel to start and no address at all. An address that exists belongs to the installation
rather than to a run, so a refusal to start still says where the App lives. See
`docs/decisions/ADR-028-an-app-is-addressed-by-its-distribution-name.md`.

An address takes the form `http://<app>.localhost:<proxy port>`: the hostname is the App's
canonical distribution name, and the port is the one `HubConfig` configures the Hub with. The Hub
writes this shape into Traefik's routing configuration and owns no proxy: it starts, supervises
and health-checks none. An App's own port — allocated at install and held in the Hub's state — is
not what is published; only the proxy port is. An address therefore answers only while a proxy is
running against that configuration, not because the Hub published it. See
`docs/decisions/ADR-031-the-proxy-is-traefik.md`;
`vibepy_studio/consumption/internals/routing.py` is the module that owns the mechanism.

A diagnostic travels in the `hub.*` vocabulary, whose codes, categories and what each reports are
defined in `vibepy_studio/consumption/models.py` and are not restated here. A failure the Hub expects travels as
data rather than as an exception. See
`docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md`
