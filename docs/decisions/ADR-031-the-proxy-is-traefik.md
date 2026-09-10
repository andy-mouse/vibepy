# ADR-031: The proxy is Traefik, and the Hub writes its routing configuration

Status: Accepted

## Context

An App's address changed at every start. `Processes` asked the operating system for a free port,
handed it to the child and published `http://127.0.0.1:<port>`, so nothing could be bookmarked
and nothing could be placed in front of one. Serving several Apps under one address needs a proxy,
and a proxy needs to know where each App is before it is asked.

The alternative that needs no per-App port was rejected before this record. Serving each App under
a path prefix of one origin requires NiceGUI's `root_path` and manual prefixing of image, link and
redirect URLs inside every App's own markup — a cost paid by every App author. No record owns the
principle that rejected it: **an App author pays nothing for the deployment shape.** It is stated
here, because this is the decision it decided.

ADR-025 already settled that a reverse proxy is adopted rather than written, and that the Hub
owning one requires an argument. Three candidates were named: nginx, Caddy and Traefik.

## Decision

The proxy is Traefik. The Hub writes its routing configuration and owns no proxy: it does not
start, supervise, signal or observe one.

An installed App that declares Pages is reached at `http://<app>.localhost:<proxy port>`. The
hostname is the App's canonical distribution name (ADR-028); the entry point is declared in
`HubConfig`, because it is part of every address the Hub publishes and a Hub cannot know it by
assuming it. Such an App's own port is allocated when it is installed and held in the Hub's
state, and is never published. An App declaring no Pages has no Web channel at all (ADR-017),
so it is given no port, no route and no address: an address that can never answer is the thing
this decision exists to stop publishing, not a shape of it.

## Consequences

- nginx is refused by the platforms this framework states it runs on. Its own documentation calls
  the Windows build "a _beta_ version" and lists as a known issue that of several workers "only
  one of them actually does any work" (<https://nginx.org/en/docs/windows.html>). It is otherwise
  the closest fit — a `map` reading an external file leaves `nginx.conf` unchanged forever — and
  it would still need the Hub to run `nginx -s reload` as the user that started nginx
- Caddy is refused by what the Hub would have to hold. Routes reach it through an admin HTTP API
  (<https://caddyserver.com/docs/api>), so the Hub would carry a client and an endpoint, and an
  install would fail whenever the proxy is not running. It also serves local hostnames over HTTPS
  by default and installs its root certificate into the system trust store
  (<https://caddyserver.com/docs/automatic-https>)
- Traefik is chosen for the interaction it does not require. Its file provider watches a directory
  and its routing configuration is hot-reloaded "without any request interruption or connection
  loss" (<https://doc.traefik.io/traefik/getting-started/configuration-overview/>), so writing a
  file is the whole of what the Hub does. `jupyterhub-traefik-proxy` names the file provider as
  the backend for single-node deployments, which is this shape
- a fixed port is a port something else can hold. `free_port()` asked the operating system for one
  that was free; a stored port has no such guarantee, so a start whose port is taken is a child
  that exits and is reported as `hub.start_failed`
- an address answers shortly after it is published rather than at once. The Hub writes a route
  file and answers, and nothing tells it when the proxy has read one. Traefik publishes no
  readiness signal — `/ping` answers before the dynamic configuration is loaded, and the request
  for an endpoint that does not is open (<https://github.com/traefik/traefik/issues/10458>) — so
  the alternative is the Hub waiting on a proxy it deliberately does not observe, which would also
  make an install fail whenever the proxy is down
- the Hub does not know whether a proxy is running, and installing an App succeeds either way
- Traefik's documentation does not state that it carries WebSocket connections, which every
  NiceGUI Page needs. `packages/vibepy-hub/tests/test_proxy.py` is what holds it to doing so, and
  a failure there invalidates this decision rather than a detail of it
- this is reversible at one module. `vibepy_hub/internals/routing.py` is the Hub's whole knowledge
  of Traefik, and a different proxy replaces it and nothing else
- the reasoning is local to a single machine serving one user. Caddy's automatic HTTPS and the
  swappable route interface JupyterHub publishes are costs here and would be assets elsewhere, so
  an origin that is not `.localhost` is a decision this one does not make
