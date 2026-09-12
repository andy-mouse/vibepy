# ADR-040: One bootstrap application installs, updates and removes Studio

Status: Proposed

## Context

Nothing decided how Studio itself reaches a user. The repository had a development script,
`scripts/run_studio.py`, run from a checkout, and the architecture documents showed an agent
platform configured by hand with the path of an interpreter inside "the studio environment".
Studio is the App that installs, addresses and starts every other App; its own install story was
the one gap left open.

The owner's requirement (2026-09-13): Studio is a GUI. It is installed and then it runs, the way
a local application does — the Hub appears in the browser — and installing it installs
everything Studio needs, the Agent channel's registration included, with no terminal command to
type. Users are on macOS and Windows; development is on macOS. Simplicity over completeness.

Facts that bound the answer, each from the authority's own documentation:

- A wheel is a file operation. The binary distribution format specifies a wheel as an archive
  that "may be installed by simply unpacking into site-packages" and defines no install-time
  code. Whatever must happen beyond placing files happens in a program that runs.
- Running code cannot replace itself, and Windows locks the files of a running process. Every
  self-updating application therefore updates from a second process.
- Registering an MCP server is writing the platform's own configuration, and both platforms
  publish a command for it: Claude Code's user scope is "stored in `~/.claude.json`" and loads
  "across all projects", written by `claude mcp add-json --scope user` and removed by `claude mcp
  remove`; Codex "stores MCP configuration in config.toml … By default this is
  `~/.codex/config.toml`", written by `codex mcp add <name> --env … -- <command>`.
- PyInstaller is the freezer in general use (sixteen million downloads a month against
  Briefcase's thirty thousand at the time of this record); `--windowed` means "do not provide a
  console window for standard i/o" on Windows and macOS; `--add-binary` carries a non-Python
  executable and `sys._MEIPASS` / `__file__` locate it at runtime. It produces an executable,
  not an installer.
- `uv tool install` puts a package in an environment of its own and exposes its entry points;
  `uv tool upgrade` or a repeated `uv tool install` remakes that environment in place.
- The operating role already judges "a newer version exists" for every App by reading one
  registered folder of wheels, with no package index.

Alternatives considered and not taken: a console script with sub-commands — a terminal
interface for a GUI application; `python -m vibepy_studio` — requires knowing which interpreter
holds Studio; a typed `uv tool install` — a terminal at the first step a GUI user meets; Studio
updating and removing itself from its own board — puts lifecycle code inside the thing being
replaced, meets the Windows lock, and adds Studio-only controls to a board that otherwise treats
every App alike; freezing Studio itself into a native application (Briefcase as Anki does,
PyInstaller with Inno Setup and dmgbuild as Kolibri does) — locks Python and every package into
the bundle so Studio can no longer be updated from the wheelhouse, and brings Apple signing and
notarization into every release. The survey of shipped Python applications behind this lives in
git history with this record's commit.

## Decision

Studio is one wheel, `vibepy-studio`, with one `gui_scripts` entry point and no
`console_scripts`, and it lives in the same folder of wheels the operating role installs Apps
from. The wheelhouse is the one supply of Studio and Apps alike; no package index is consulted.

Beside the wheels sits **one bootstrap application per platform** — `vibepy-studio-setup` for
macOS, `vibepy-studio-setup.exe` for Windows — a PyInstaller `--windowed` single file built by
the CI job that already runs on both platforms, carrying the `uv` binary. It has no state of
its own and is never copied anywhere: the user always runs the one in the wheelhouse, and a new
Studio arrives as a new wheel and a new bootstrap in the same folder.

Double-clicked, it shows one small window (the standard library's `tkinter`) with three
actions, **Install**, **Update**, **Remove**, and what it found: Studio's installed version if
any, and the newest version the folder offers. The user chooses; an action that does not apply
is disabled. Each action is a sequence, and every step is idempotent:

| Action | Steps |
| --- | --- |
| Install | `uv tool install --find-links <this folder> vibepy-studio` → register the Agent channel with every platform whose CLI is found → desktop shortcut to the `vibepy-studio` executable → launch Studio |
| Update | stop the running Studio → the same `uv tool install` at the newer version → re-register → relaunch Studio |
| Remove | stop the running Studio → unregister from every platform → `uv tool uninstall vibepy-studio` → delete the shortcut → leave the root and show its path |

Registration is the platforms' own commands, never their files: `claude mcp add-json --scope
user vibepy-studio '{"command": <tool-environment python>, "args": ["-m", "vibepy_core.mcp",
"studio"], "env": {"VIBEPY_ROOT": …, "VIBEPY_PROXY_PORT": …}}'` and `codex mcp add vibepy-studio
--env VIBEPY_ROOT=… --env VIBEPY_PROXY_PORT=… -- <python> -m vibepy_core.mcp studio`. A platform
whose CLI is not on the machine is skipped and named in the bootstrap's log; installing that
platform later and running the bootstrap again registers it, because every step is idempotent
— running the bootstrap again *is* the repair.

Studio holds no code for its own lifecycle. Its `gui_scripts` entry point does what
`scripts/run_studio.py` did and retires it: prepare the root — `~/vibepy-apps` by default, from
`Path.home()`, or `VIBEPY_ROOT` — start Traefik and Studio's Web window as children it holds
(ADR-039), write Studio's own route so the Hub is reached at
`http://vibepy-studio.localhost:<proxy port>` like every App, open the browser there with the
standard library's `webbrowser`, and write `<root>/vibepy-studio/studio.pid` while it runs. That
file is how the bootstrap stops a running Studio, and ADR-039 is why stopping Studio stops
Traefik and the Apps with it. The root is left by Remove because it is the user's data — the
installed Apps and what they hold — as `remove_app` leaves an App's data outside its folder.

Traefik reaches the root from the wheelhouse too, not from the internet: the bootstrap's folder
carries the pinned Traefik binary for each platform beside the wheels, and Install copies it to
`<root>/vibepy-studio/tools/`. The wheelhouse model exists for machines without an index, and a
first launch that fetched would contradict it.

ADR-031 stands as written for the Hub: its Tools write routing configuration and start,
supervise, signal and observe no proxy. This record decides who does — Studio's process entry
point, which is not a Tool.

## Consequences

- installing, updating and removing Studio are three buttons in one window; nothing is typed.
  The one thing the user must know is where the wheelhouse is, which they were handed
- Studio's board treats Studio like no App at all: it has no row and no controls for itself,
  and the operating role's installer has no notion of "the distribution that is me"
- the Windows file lock and "code cannot replace itself" never arise: Studio is not running
  when the bootstrap changes it
- there is no reconciliation of registration at launch and no record of it anywhere; the
  platform's configuration is written when Studio is installed or updated, and rerunning the
  bootstrap rewrites it. A platform installed after Studio is registered by that rerun
- `VIBEPY_ROOT` remains the only configuration channel (ADR-033); the default is a value the
  entry point supplies, not a new channel. The platform user-data convention (`platformdirs`)
  was considered and not taken: a dependency and three paths to explain, for a folder the user is
  meant to find
- the bootstrap depends on `uv`, which it carries, and on a Python for the tool environment,
  which uv fetches; on a machine with no route to the internet a Python distribution must be
  placed in the wheelhouse and pointed at. Which uv option does that is verified against uv's
  documentation before implementation and recorded then — the offline case is a requirement of
  the wheelhouse model, not an option
- three more facts are verified against the platforms' documentation before implementation:
  whether `claude mcp add-json` replaces an existing entry of the same name or must be preceded
  by `claude mcp remove`; whether Codex publishes `codex mcp remove`; and the documented way to
  obtain the tool environment's interpreter path from uv
- code signing and notarization are outside this decision. An unsigned executable meets the
  platforms' warnings on first open, and the owner accepts that for an in-house wheelhouse
- this record is Proposed until the bootstrap and the entry point exist and the gate proves
  them on macOS and Windows
