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
holds Studio; a typed `uv tool install` — a terminal for the one step a GUI user meets first;
packaging Studio itself as a frozen native application (Briefcase as Anki does, or PyInstaller
with Inno Setup and dmgbuild as Kolibri does) — which freezes Python and every package into the
bundle, so Studio could no longer update itself from the wheelhouse, and which brings Apple
signing and notarization into every release; the survey of shipped Python applications behind
this is in the milestone folder of M17 while it exists, and in git history after.

## Decision

Studio is distributed as one wheel, `vibepy-studio`, placed in the same folder of wheels the
operating role installs Apps from, and installed into a tool environment from that folder:
`uv tool install --find-links <wheelhouse> vibepy-studio`. It declares one `gui_scripts` entry
point, `vibepy-studio`, and no `console_scripts`. No package index is consulted for Studio or
for Apps; the wheelhouse is the one supply of both.

That install command is not typed. Beside the wheels, the wheelhouse carries one **bootstrap
executable per platform** — `install-vibepy-studio` for macOS, `install-vibepy-studio.exe` for
Windows — built with PyInstaller, one file each, by the CI job that already runs on both
platforms. Double-clicked, it:

1. takes the folder it was launched from as the wheelhouse — no path is asked for;
2. runs the `uv` binary it carries (`--add-binary`), so the user's machine needs neither uv nor
   Python beforehand;
3. runs `uv tool install --find-links <that folder> vibepy-studio`;
4. creates a desktop shortcut to the `vibepy-studio` executable — a `.lnk` on Windows, an alias
   on macOS — and launches Studio, whose first launch does the rest (below).

The bootstrap does one thing once. It is not the application, holds no state, and is not what
updates or removes Studio. PyInstaller is the freezer because it is the one in general use
(sixteen million downloads a month against Briefcase's thirty thousand at the time of this
record) and because a single-file executable is all this step needs; it produces no installer,
and none is wanted here. Code signing and notarization are not part of this decision.

Where the machine has no route to the internet, uv cannot fetch a Python for the tool
environment. Whether a Python distribution placed in the wheelhouse can be pointed at
(`--python` with a path, or `UV_PYTHON_INSTALL_MIRROR`) is verified against uv's documentation
before implementation and recorded then; the offline case is a requirement of the wheelhouse
model, not an option.

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
   alone, because the platform's configuration is state outside Studio: a platform installed
   after Studio has no entry yet, a user may have edited or removed the entry, and a new Studio
   may register with different arguments or variables. A launch keeps no record of having
   registered; it observes the platform, which is the stance `docs/roadmap.md` M19 states for an
   App's registration, and this is the same registration with Studio as its first user.

Closing the launcher closes its children. The Agent channel process is still launched by the
agent platform (ADR-010, ADR-017); what changes is that its registration is written by Studio
rather than by hand.

Studio is a row on its own board, like any App. `list_apps` reads the registered package source
— the folder `register_package_source` recorded in Studio's own state, which is how it judges a
newer version of any App — and finds `vibepy-studio` there the same way; a newer wheel shows as
"newer" on Studio's row with the same Update, and the row has the same Remove. Its state is
`running` whenever the board is seen, and it has no Start or Stop, as an App without a Web
channel has none. No Tool and no Page is added for Studio's own sake. The one place Studio
differs is the installer, for the structural reason that Studio's environment is not one the
operating role created:

- **update**: for its own distribution the installer runs `uv tool install --find-links
  <wheelhouse> vibepy-studio==<newer>` as a child and relaunches Studio — running code cannot
  replace itself, so upgrade-then-relaunch is the shape every self-updating application has.
  The tool environment's path does not change across an upgrade, so the registration written at
  step 5 stays valid.
- **remove**: for its own distribution the installer stops the running Apps, removes the Agent
  channel registration it wrote from every platform that holds it, runs `uv tool uninstall
  vibepy-studio`, and exits. The root — `~/vibepy-apps`, the installed Apps and what they hold —
  is left in place and its path shown: it is the user's data, as `remove_app` leaves an App's
  data outside its folder.

Before a source is registered, Studio knows of no newer version of anything, itself included;
registering one is the step an App install already requires, and nothing is added for Studio.

ADR-031 stands as written for the Hub: its Tools write routing configuration and start,
supervise, signal and observe no proxy. This record decides who does — the launcher, which is
Studio's process entry point and not a Tool — and retires `scripts/run_studio.py`, which was
that launcher under a development name.

## Consequences

- installing Studio is one command an installer of wheels already provides, and using it is
  one launch; nothing is typed into a terminal after installation
- the first launch does what a native installer would have done at install time; every later
  launch finds it done or repairs it. The steps are idempotent, because a launch keeps no record
  of being the first
- Studio publishes an address of the same shape as its Apps, and the user sees one port
- the tool environment's interpreter path appears in the agent platform's configuration, written
  by Studio. Removing Studio through its own board removes it; removing Studio by hand
  (`uv tool uninstall` in a terminal) leaves it, because no launch follows to observe that, and
  the platform then reports a command it cannot run
- update and removal depend on `uv` being present, which the installer this record chooses
  guarantees
- whether uv records the `--find-links` folder of the bootstrap install where Studio could read
  it back is verified against uv's documentation before implementation; if it does, the first
  launch registers that folder as the package source and the operator registers nothing by
  hand. Not promised here
- the operating role's installer learns one distinction — the distribution it is itself — and
  nothing above it does; the board renders Studio's row with the code that renders every row
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
