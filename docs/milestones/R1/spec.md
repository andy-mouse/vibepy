# R1 - One address per App

R1 is not a `docs/roadmap.md` milestone. Its scope and its place in the sequence come from
`docs/milestones/code-review-roadmap.md`. It acts on no finding: it carries out D6, D7 and D8 in
`docs/milestones/code-review/decisions.md`, and it precedes `docs/roadmap.md` M11, which renders
the addresses it creates.

One sentence states the whole of it: **an App's address is decided when it is installed, not
when it is started.** Today `Processes.start` asks the operating system for a free port at every
start, so an App has no address that outlives a run, and nothing can be placed in front of it.
Fixing that is not a proxy — the proxy is Traefik, adopted whole — it is giving the Hub the two
facts a proxy needs: which port an App serves on, and which hostname reaches it.

## Acceptance criteria

- two Apps are served concurrently through one static proxy configuration
- `RunningApp` answers with an address rather than a port, and `free_port` is gone
- an App's own code contains nothing that exists because of how it is served

## Sources

| Contract | Source |
| --- | --- |
| a reverse proxy, a process supervisor and a state store are things to adopt, not to write; the Hub owning any of them requires an argument | `docs/decisions/ADR-025` |
| an App is addressed by its canonical distribution name | `docs/decisions/ADR-028` |
| a canonical name is lowercase letters, digits and `-`, and a project name begins and ends with a letter or a digit | PyPA, *Project name normalization* (<https://packaging.python.org/en/latest/specifications/name-normalization/>) |
| Traefik separates the install configuration from the routing configuration, and the routing configuration "can change and is seamlessly hot-reloaded, without any request interruption or connection loss" | Traefik, *Configuration overview* (<https://doc.traefik.io/traefik/getting-started/configuration-overview/>) |
| the file provider watches a directory with `watch` defaulting to true, and reports changes through fsnotify | Traefik, *File provider* (<https://doc.traefik.io/traefik/reference/install-configuration/providers/others/file/>) |
| Traefik ships one static binary per platform, `darwin_arm64`, `darwin_amd64` and `windows_amd64` among them | Traefik, *Releases* (<https://github.com/traefik/traefik/releases>) |
| nginx for Windows "is considered to be a _beta_ version", and of several workers "only one of them actually does any work" | nginx, *nginx for Windows* (<https://nginx.org/en/docs/windows.html>) |
| Caddy serves local hostnames over HTTPS with self-signed certificates and attempts to install its root certificate into the system trust store, prompting for a password if it lacks permission | Caddy, *Automatic HTTPS* (<https://caddyserver.com/docs/automatic-https>) |
| Caddy's routes are mutated at runtime through an admin HTTP API on `/config/[path]` | Caddy, *API* (<https://caddyserver.com/docs/api>) |
| a name resolution API "SHOULD recognize localhost names as special and SHOULD always return the IP loopback address", and should not query DNS for them | RFC 6761 §6.3 (<https://www.rfc-editor.org/rfc/rfc6761>) |
| Firefox hardcodes localhost names to the loopback address without consulting the system resolver | Mozilla, *bug 1220810* (<https://bugzilla.mozilla.org/show_bug.cgi?id=1220810>) |
| Safari on macOS did not resolve localhost subdomains; it was resolved at the operating system level in macOS 26 | ipfs, *in-web-browsers#206* (<https://github.com/ipfs/in-web-browsers/issues/206>) |
| a control plane owns route lifecycle behind `add_route`, `delete_route` and `get_all_routes`, and a proxy it does not run sets `should_start = False` | JupyterHub, *Proxy* (<https://jupyterhub.readthedocs.io/en/stable/howto/proxy.html>) |
| the file provider is the backend for "smaller, single-node deployments" | jupyterhub-traefik-proxy (<https://jupyterhub-traefik-proxy.readthedocs.io/en/latest/>) |
| serving a NiceGUI Page under a path prefix requires `root_path` and manual prefixing inside the App's own markup; subdomain routing requires nothing of the application | `docs/milestones/code-review/decisions.md`, D6 |
| an App author pays nothing for the deployment shape | `docs/milestones/code-review/decisions.md`, P3 |
| `os.replace` overwrites the destination and the rename is atomic where POSIX requires it | Python, *os* (<https://docs.python.org/3/library/os.html#os.replace>) |
| filesystem paths are `pathlib.Path`, the framework runs on macOS and Windows, and a change is done when `make lint typecheck test` passes | `AGENTS.md` |

## Problem

**An address that does not outlive a run.** `free_port()` binds a socket to port 0, reads back
what the operating system chose, closes it, and hands the number to the child. Every start
therefore produces a different address. A user cannot bookmark an App, and no configuration
written in front of one can name it.

**The internal port is what the Hub publishes.** `RunningApp.url` and `AppRow.url` are both
`http://127.0.0.1:<port>` — the address of the child process itself. There is nowhere to insert
anything, because the answer the Hub gives *is* the child's own socket.

**The alternative that was rejected costs the App author.** Serving each App under a path prefix
of one origin needs no per-App port, but D6 verified that NiceGUI requires `root_path` plus
manual prefixing of `html.img`, `ui.markdown` links, `.props()` URLs and redirects. That is a
cost paid inside every App's own code, which P3 forbids and which the third acceptance criterion
states as a property to be preserved.

## Decisions

One record, ADR-031: **the proxy is Traefik, and the Hub writes its routing configuration
without owning it.**

Three candidates were named by D7, and the repository's own constraints eliminate two.

*nginx is eliminated by the platforms.* AGENTS.md states that the framework runs on macOS and
Windows. nginx's own documentation calls the Windows build a beta version and lists as a known
issue that only one worker does any work; running as a service is listed among possible future
enhancements. A default deployment shape cannot rest on a platform its own project does not
recommend. nginx is otherwise the closest fit to the phrase in the acceptance criterion — a
`map` reading an external file leaves `nginx.conf` literally unchanged forever — and it would
still require the Hub to invoke `nginx -s reload`, which the documentation says must run as the
user that started nginx.

*Caddy is eliminated by what the Hub would have to hold.* Routes reach Caddy through an admin
HTTP API, so the Hub would carry an HTTP client and an endpoint setting, and an install would
fail when the proxy is not running. Caddy also serves local hostnames over HTTPS by default and
attempts to install its root certificate into the system trust store, prompting for a password.
Both are assets outside a single developer machine and costs inside one.

*Traefik is what remains, and it is chosen for the interaction it does not require.* The file
provider watches a directory, `watch` defaulting to true, and the routing configuration is
hot-reloaded without connection loss. The Hub's entire interaction with the proxy is writing a
file: no signal, no HTTP client, no privilege, and no requirement that the proxy be running when
an App is installed. That is the least the Hub can hold and still give each App an address, and
it is what keeps ADR-025's demand unanswered rather than answered — the Hub owns no proxy, so no
argument for owning one is needed. `jupyterhub-traefik-proxy` names the file provider as the
backend for single-node deployments, which is this shape.

P3 is recorded here. No record owns it, and `code-review/decisions.md` says R1's ADR is where it
lands. It is the criterion that rejected the path prefix, and it survives this stage as the third
acceptance criterion.

What the record does not decide: the Hub does not run, supervise, install or health-check the
proxy. JupyterHub's own documentation treats an externally managed proxy as ordinary, and this
is that case.

## Scope

1. **A port per installed App that declares Pages.** `install_app` allocates the lowest port at
   or above 9000 that the Hub's state does not already hold, and stores it under the App's
   canonical name. `remove_app` releases it. Installing an App that is already installed is
   refused as `hub.already_installed`: what installing over an installation means is nobody's
   decision yet, no milestone owns updating an App, and the remedy is two operations that
   already exist -- remove it, then install it. An App declaring no Pages has no Web
   channel (ADR-017) and is refused by `start_app`, so it is given no port, no route and no
   address.
2. **The Hub writes both halves of the proxy's configuration.** A window writes
   `<root>/traefik.yml` when it opens: one entry point on the port the Hub was configured with
   and a file provider watching `<root>/routes`, with `watch` true. It does not change as Apps come and go. `install_app`
   writes `<root>/routes/<app>.yml`, one router matching `Host(<app>.localhost)` and one service
   pointing at `http://127.0.0.1:<port>`; `remove_app` deletes it.
3. **An address replaces a port in every answer.** `AppRow.url` and `RunningApp.url` become
   `http://<app>.localhost:<proxy port>` for an installed App that holds a port, whether it is
   running or not, `stop_app`'s
   answer included: the address belongs to the installation, and a stopped App is one whose
   address does not answer. The child's own port stops leaving the Hub.
4. **`free_port` is gone.** `Processes.start` takes the port it is to serve on and returns
   nothing. `Processes.running` answers whether an App is serving, not on which port.
5. **`make install` obtains the proxy.** It fetches a pinned Traefik release for the running
   platform into the workspace through a `tools` target, so `make test` means the same thing on a
   contributor's machine and on CI. CI runs that target: `uv sync` does not bring a proxy, and a
   test that cannot run there is the skip this stage refused, arriving by another door.

## Public API

| Change | Kind |
| --- | --- |
| `HubConfig.proxy_port`, an `int` defaulting to `8080` | added |
| `HubState.ports`, a `dict[str, int]` | added |
| `AppRow.url` is the App's proxy address, present whenever the App holds a port | changed |
| `RunningApp.url` is the App's proxy address | changed |
| `Processes.start` takes `port` and returns `None` | changed |
| `Processes.running` answers `bool` | changed |
| `hub.already_installed`, refusing an install of an installed App | added |
| `free_port` | deleted |

`HubState` is a stored model, so a state file written before this stage validates against it: a
missing `ports` is an empty mapping, and every installed App is allocated a port the next time it
is installed. An App installed before this stage has no port and therefore no address, which
`AppRow.url` reports as absent — the same shape a caller already handles. `start_app` refuses it
and names the remedy: remove the App and install it again.

No new `hub.*` code. A route file the Hub cannot write is the same class of failure as a state
file it cannot write, which this Hub does not catch either, and inventing a diagnostic for it
here would be the only place in the Hub where a filesystem failure inside its own root is
expected.

## Where each thing lives

**The address is derived, not stored.** State holds the App's port; the hostname is the App's
canonical name and the entry point comes from the Hub's own configuration. Storing the full URL
would put the same fact in two places and let a state file disagree with the proxy configuration
the Hub itself wrote.

**What is published is declared; what is internal is allocated.** The entry point is part of
every address the Hub answers with, and a Hub that hardcoded it would assert a fact about its
host that it cannot know: when the port is taken, Traefik does not bind, the Hub is not told —
it owns no proxy — and it goes on publishing addresses that reach nothing, or reach whatever
else holds that port. `HubConfig` is documented as what the Hub requires of its host and already
declares `root` for this reason; a port on that host is the same kind of fact as a directory on
it, and ADR-022 makes an App's configuration its declaration rather than something hidden in its
code. It defaults to 8080, so nothing is configured in the ordinary case. An App's own port is
not published, is reached only by the proxy, and fails loudly as `hub.start_failed` when it is
taken, so it is allocated rather than declared.

**The name is already a valid label.** ADR-028 addresses an App by its canonical distribution
name, and the normalization specification leaves only lowercase letters, digits and `-`, with a
letter or digit at each end. That is a DNS label as written, so nothing is escaped, mapped or
sanitized between the App's name and its hostname.

**`.localhost` needs no configuration and no hosts file.** RFC 6761 has resolvers return the
loopback address for localhost names, and Chrome, Edge and Firefox hardcode it. Safari was the
exception until macOS 26 resolved it at the operating system level. What is not covered is a
non-browser client: a test that asks the system resolver for `todo-app.localhost` fails on
Windows. The tests therefore connect to `127.0.0.1` and send the hostname in the `Host` header,
which is what the proxy routes on and is a stricter check than a resolver's answer.

**Writing routes lives in `internals/routing.py`.** One module holds the address constants, the
two writers and the deleter, so the Hub's knowledge of Traefik is one file that a different proxy
would replace. A route file is written to a neighbour and moved into place with `os.replace`, so
the provider's watch never sees a half-written file.

**Port allocation lives with the state that holds it**, inside the same `update_state` critical
section as the rest of the install's state change, so two concurrent installs cannot be handed
one port.

## Errors

`hub.already_installed` joins the Hub's code table in `vibepy_hub/models.py`, in the `caller`
category. No row joins `errors.md`.

A start whose port is already taken by something else is a child that exits, which
`hub.start_failed` already reports. This is the cost D8 accepted when it replaced `free_port()`:
the operating system no longer guarantees the port is free, and the failure surfaces at start
rather than being avoided. It is stated in ADR-031's consequences.

Not observing the proxy has a second cost, and it is stated there too. An address is published as
soon as its route file is written, and nothing tells the Hub when the proxy has read one, so an
address begins answering shortly after an install rather than at the moment the Hub answers with
it. Traefik publishes no readiness signal — `/ping` answers before the dynamic configuration is
loaded and the request for an endpoint that does not is open
(<https://github.com/traefik/traefik/issues/10458>) — so the alternative is the Hub waiting on a
proxy it deliberately does not observe, which would also make an install fail whenever the proxy
is not running. That property is kept on purpose, and this is what it costs.

## Testing

`make test` collects 229 tests where R1 begins.

- **WebSocket through the proxy, first.** Traefik's documentation does not state that it proxies
  WebSocket connections, and NiceGUI's Pages do not work without one. Because a negative answer
  invalidates the choice of proxy rather than a detail of it, this is the first task: one App
  behind Traefik, and a NiceGUI socket that opens and exchanges a frame through the proxy. A
  `GET /` returning 200 does not settle it and is not accepted as settling it.
- **Two Apps, one configuration** — the acceptance criterion as written. Both example Apps are
  installed, Traefik runs against the `traefik.yml` the Hub wrote, and each App answers on its
  own `Host`. The configuration is written once, before either App is installed, and is not
  touched again.
- **An address that outlives a run** — an App started, stopped and started again answers with the
  same URL each time, and the URL is present in `list_apps` while the App is not running.
- **Allocation** — two installs take two ports; removing the first and installing a third leaves
  the second where it was. Installing an installed App is refused, and the refusal leaves both
  the environment and the address where they were.
- **The route file** — installing writes a route naming the App's host and its port; removing
  deletes it. Read as YAML and asserted by content, not by string.
- **`free_port` is gone** — the existing tests of `Processes` supply a port. The test helper of
  the same name in `tests/test_serve_command.py` is a different function and stays: it chooses a
  port for a command the test itself runs, which is not the Hub allocating one.
- **The third criterion** is a property of the examples rather than a behaviour: neither example
  App gains anything, and the Traefik tests exercise the same unmodified Apps that the existing
  tests do. Nothing is added that could assert it and not fail; it is checked in review.

Traefik is required, not skipped when absent. A skipped test cannot fail, and `make test`
passing has to mean the same thing everywhere; `make install` is what makes that reasonable.

## Compatibility

`AppRow.url` and `RunningApp.url` change meaning. Nothing outside this repository consumes the
Hub, and `docs/hub-ui-mockup.html` renders whatever URL it is given.

`make test` now requires the Traefik binary. `make install` fetches it, so the documented
sequence is unchanged; a contributor who has not re-run `make install` sees a failure naming what
to run.

## Documentation

- `docs/decisions/ADR-031`, new: the proxy is Traefik, the Hub writes routing configuration and
  owns no proxy, and P3.
- `vibepy_hub/models.py` — what an App's address is and where the port comes from, beside the
  code table, until CR3 gives the Hub a document to carry both.
- `docs/milestones/code-review-roadmap.md` — CR2 is marked merged, which it is, and `## Order`
  names CR3 as next.

No existing record changes. ADR-025 is applied rather than amended: the Hub adopts a proxy and
owns none.

## Out of scope

- **Rendering the address.** M11 owns the Hub's UI.
- **HTTPS, certificates and any origin that is not `.localhost`.** A single developer machine is
  the shape this stage serves.
- **Running, supervising or health-checking the proxy.** The Hub writes files.
- **A configurable base domain.** `.localhost` is what needs no resolver configuration on any
  supported platform, and an origin that is not local is out of scope with the certificates it
  would require.
- **A second Hub window.** Two windows over one root would allocate ports against one state file
  and write into one routes directory; cross-process coordination is not opened here, as CR2
  already stated for the state file.
- **A distribution name longer than a DNS label permits.** No sample approaches it and no
  criterion mentions it.
- **Detecting that an allocated port is occupied before starting.** D8 accepted the start-time
  failure; a pre-flight bind would be `free_port()` under another name.
- **Every CR3 finding**, the Hub's missing architecture document among them.
