# ADR-040: Studio is installed as a GUI application that completes its own installation on first launch

Status: Proposed

## Context

Nothing decided how Studio itself reaches a user. The repository had a development script,
`scripts/run_studio.py`, that starts Traefik and Studio's Web window and is run from a checkout;
the architecture documents show an agent platform configured with the path of an interpreter
inside "the studio environment", which the user is left to find. Studio is the App that installs,
addresses and starts every other App, and its own install story was the one gap left open.

The owner's requirement (2026-09-13): Studio is a GUI. It is installed and then it runs, the way a
local application does — the Hub appears in the browser — and installing it installs everything
Studio needs, the Agent channel's registration included, with no terminal command to learn.

Three facts bound the answer:

- A wheel is a file operation. The binary distribution format specifies a wheel as an archive
  that "may be installed by simply unpacking into site-packages", and defines no step that runs
  the package's code at install time. Whatever must happen beyond placing files happens when
  the application first runs, or in a native installer outside Python packaging.
- Python packaging defines two entry point groups "of special significance": `console_scripts`
  and `gui_scripts`. Both create a command usable after installation; the second exists for
  applications with a graphical interface (Python Packaging User Guide, Entry points
  specification).
- Registering an MCP server with an agent platform is writing that platform's own
  configuration (`.mcp.json` for Claude Code, `config.toml` for Codex; `docs/architecture/packaging.md`,
  Opening the Agent channel). `docs/roadmap.md` M19 gives the Hub this job for the Apps it
  installs. Studio doing it for itself is the same mechanism with Studio as its first user.

The alternatives considered: a console script with sub-commands (`vibepy-studio serve|mcp`) —
a terminal interface for a GUI application, and exactly what the owner declined; `python -m
vibepy_studio` — the `__main__` convention, which requires the user to know which interpreter
holds Studio; a native installer (`.pkg`, `.msi`) — completes installation at install time, at
the cost of a second distribution form and a build pipeline for it, for a step first launch can
do.

## Decision

Studio is distributed as one wheel, `vibepy-studio`, and installed into a tool environment
(`uv tool install vibepy-studio`, or any installer of wheels). It declares one `gui_scripts`
entry point, `vibepy-studio`, and no `console_scripts`.

Launching it completes the installation and opens the Hub:

1. the root is prepared at its default, `~/vibepy-apps` — the user's home directory, which the
   standard library's `Path.home()` answers the same way on every platform, and a folder the
   user can see and name — unless `VIBEPY_ROOT` names another;
2. the pinned Traefik is fetched into `<root>/vibepy-studio/tools/` if it is not there, as
   `scripts/fetch_traefik.py` does today;
3. Traefik and Studio's Web window are started as children of the launcher, which holds them
   the way the Hub holds an App's process (ADR-039);
4. Studio's own route is written, so the Hub is reached at
   `http://vibepy-studio.localhost:<proxy port>` like every other App, and the browser is opened
   there with the standard library's `webbrowser`;
5. Studio's Agent channel registration is reconciled with every agent platform found on the
   machine: the platform's configuration is read, and the entry is written when it is absent or
   differs from what this launch would write — the tool environment's interpreter and
   `-m vibepy_core.mcp studio` with Studio's variables. Every launch does this, not the first
   alone: a launch keeps no record of having registered, it observes the platform, which is the
   stance `docs/roadmap.md` M19 states for an App's registration, and this is the same
   registration with Studio as its first user.

Closing the launcher closes its children. The Agent channel process is still launched by the
agent platform (ADR-010, ADR-017); what changes is that its registration is written by Studio
rather than by hand.

ADR-031 stands as written for the Hub: its Tools write routing configuration and start,
supervise, signal and observe no proxy. This record decides who does — the launcher, which is
Studio's process entry point and not a Tool — and retires `scripts/run_studio.py`, which was
that launcher under a development name.

## Consequences

- installing Studio is one command an installer of wheels already provides, and using it is
  one launch; nothing is typed into a terminal after installation
- the first launch does what a native installer would have done at install time; every later
  launch finds it done or repairs it. The steps are idempotent, because a launch keeps no record
  of being the first: an upgrade, a reinstall into another environment, or a new interpreter is
  corrected at the next launch without anyone knowing it was needed
- Studio publishes an address of the same shape as its Apps, and the user sees one port
- the tool environment's interpreter path appears in the agent platform's configuration, written
  by Studio; a user who moves or reinstalls Studio's environment relaunches it, and the
  registration is rewritten. Uninstalling Studio leaves its registration behind, because there is
  no launch after an uninstall to observe it; the platform then reports a command it cannot run,
  which is the same limit M19 accepts for an App removed outside Studio
- whether `uv tool install` exposes `gui_scripts` is verified against uv's documentation before
  implementation: its tools document names "console entry points, script entry points, and
  binary scripts" and does not name GUI scripts. If it does not expose them, the record is
  amended with the installer that does, not with a console script
- an App's MCP registration (M19) and Studio's own share one implementation, so M19 widens what
  this record introduces rather than adding a second copy
- `VIBEPY_ROOT` remains the only configuration channel (ADR-033); the default is a value, not a
  new channel. The platform's user-data directory convention (`platformdirs`, as uv and pip
  follow) was considered and not taken: it is a dependency and three paths to explain, for a
  folder the user is meant to find
- this record is Proposed until the launcher exists and the gate proves it on macOS and Windows
