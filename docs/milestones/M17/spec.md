# M17 — Enterprise isolation

Date: 2026-09-13

## Acceptance criteria

From `docs/roadmap.md`, verbatim:

- installed Apps can execute without unintended dependency or process sharing
- failure of one isolated App does not compromise another App runtime
- isolation does not change the App / Tool / Page programming contract

The milestone's own statement, also verbatim: *Define and implement appropriate isolation modes
for multiple installed apps: dependency, process, filesystem, network, resource limits as
required.*

## Sources

| Contract | Source |
| --- | --- |
| The framework states the isolation contract; the host implements it. Environment isolation is a contract the Hub keeps by construction, and M17 owns hardening it | `docs/architecture/packaging.md`, The isolation invariant; ADR-017; ADR-025 |
| A channel's runtime exists only inside the host's window; there is no state in which an App is constructed but not running | ADR-020; `docs/architecture/lifecycle.md`, Runtime lifecycle |
| Each channel runs in its own process; a process the agent platform spawned ends when that client ends it; Hub start/stop/status describe the Web channel runtime | ADR-017 |
| Only a parent observes its own children; `subprocess` documents no way to observe an arbitrary pid | `vibepy_studio/operating/internals/processes.py`, module docstring; Python `subprocess` docs |
| A launcher hands a child the environment the child is entitled to and nothing that describes the launcher | `vibepy_studio/internals/processes.py`, module docstring |
| `serve` reads nothing from standard input; the environment is the only configuration channel | `docs/architecture/packaging.md`, Configuration and Running a channel; ADR-033 |
| `remove_app` deletes an App's environment and leaves the data it wrote elsewhere; `update_app` remakes only the environment | `docs/architecture/lifecycle.md`, This layer's capabilities; `vibepy_studio/operating/tools/installation.py` |
| An App is addressed by its canonical distribution name, one path segment | ADR-028; `installer.environment` |
| `-I`: "Run Python in isolated mode. This also implies -E, -P and -s options. In isolated mode sys.path contains neither the script's directory nor the user's site-packages directory. All PYTHON\* environment variables are ignored, too." | Python docs, Command line and environment, `-I` |
| A virtual environment is recognised by the file next to the interpreter, not by the environment: "If home is not set and a pyvenv.cfg file is present in the same directory as executable, or its parent, prefix and exec_prefix are set that location" | Python docs, Python Initialization Configuration, Python Path Configuration |
| File descriptors Python creates are non-inheritable by default, so a pipe handed to one child is not held open by another | PEP 446 |
| stdio: "The client launches the MCP server as a subprocess" and ends it by "Close stdin, terminate subprocess" | MCP specification 2025-06-18, Transports, stdio |
| "While open handles to kernel objects are closed automatically when a process terminates" — a parent that dies by any means closes its end of a pipe | Microsoft Learn, Terminating a Process |
| uvicorn's server loop exits when `should_exit` is set; the documentation exposes no other programmatic stop, so the code is the authority | `uvicorn/server.py`, `Server.should_exit`, `main_loop`, `on_tick` |
| A supervisor runs each program in a working directory of its own | systemd `WorkingDirectory=`; supervisord `directory=`; Docker `WORKDIR` |
| Installed artifacts are immutable and are shared from one store by hardlink; modifying them in place is misuse of the store | pnpm (content-addressable store, hardlinked `node_modules`); Nix (read-only store); uv `link-mode` ("Defaults to clone … on macOS and Linux, and hardlink on Windows") |
| A process manager gives a service `/dev/null` as standard input unless told otherwise | systemd `StandardInput=` ("Defaults to null"); `nohup` |
| Hardlink was chosen here for measured cause: a second environment 4.0s → 1.37s, `make test` 170s → 123s, because macOS assesses a `.so` by inode | commit `65c8f70`; `installer.install` docstring; astral-sh/uv#18577 |
| Processes of one user account are one security principal; separating them needs another principal or a sandbox | POSIX process model (same uid: `ptrace`, `/proc/<pid>/environ`, `ps -E`); Windows (same logon session: `OpenProcess`); Android per-app uid; systemd `DynamicUser=` |
| Comparable local package hosts run trusted code in per-app environments under one user | pipx, conda, Homebrew services, VS Code extension host |

## Problem

`packaging.md` states the isolation invariant as three rows, and says of the third — an App is
installed into an environment of its own — that it is "a contract, not a guarantee", kept by the
Hub by construction, and that M17 owns hardening it. Four gaps remain between that contract and
what the Hub does, and one half of the process model is unimplemented:

| Gap | What happens today |
| --- | --- |
| the child interpreter runs without `-I` | the user's site-packages (`~/.local/lib/python3.x/site-packages`, `~/Library/Python/…`) is on `sys.path`; `python -m` prepends the current directory; `PYTHON*` variables are dropped by a hand-kept list, so one not on the list reaches the App |
| the child inherits the Hub's current directory | every App that writes a relative path writes into the same folder, the Hub's; two Apps collide with each other and with the Hub |
| an App's folder is its environment | `envs/<app>` *is* the virtual environment, so an App has no place of its own that survives `update_app` remaking the environment |
| the Hub's death leaves its children running | `Processes.start` opens the child with `stdin=DEVNULL`; nothing binds the child's life to the Hub's. A Hub that restarts reports the App `installed`, cannot stop it, cannot start it (the port is held), and Traefik routes to a process no one owns. ADR-020 says a runtime exists only inside its host's window; this is the case where it does not |
| "failure of one App does not compromise another" is believed, not tested | no test starts two Apps and kills one |

## Design

### Principle

**A channel process lives inside its host's window and sees only its own environment.** Both
halves are already decided — ADR-020 for the lifetime, `packaging.md` for the environment — and
this milestone implements what those decisions imply for the Web channel process the Hub
starts. The Agent channel process already behaves this way: the MCP client ends it by closing
stdin, and the SDK runs it in the environment the client names. After this milestone the two
channel processes obey one rule.

Nothing here reaches the App / Tool / Page contract. An App declares what it declares, its
configuration arrives as it does, and its handlers run as they do. What changes is where the
Hub puts the App and how the Hub runs it.

### Isolated mode

Every framework command Studio runs with an App environment's interpreter runs in isolated
mode:

```text
<env>/bin/python -I -m vibepy_core.serve <app> --port <n>
<env>/bin/python -I -m vibepy_core.describe
<env>/bin/python -I -m vibepy_core.invoke <app> <tool> …
```

`-I` is what Python provides for exactly this: a program run by one party on another party's
code, which must see the environment it was installed into and nothing the launching process
happens to have. It removes the three leaks in one flag, and the removal is Python's guarantee
rather than a list this repository maintains. The virtual environment still applies, because a
venv is recognised by `pyvenv.cfg` next to the interpreter and not by any variable `-I` ignores.

One function assembles an App-environment command — interpreter, `-I`, `-m`, module, arguments
— and the three call sites use it. pyright's invocation is not one: it does not run App code.

`DESCRIBES_THIS_PROCESS` loses its `PYTHON*` entries; `-I` owns them now, and the same guarantee
is not kept in two places. It keeps `VIRTUAL_ENV`, `PYTEST_CURRENT_TEST` and the `NICEGUI_*`
variables, which describe the launcher and are not Python's to ignore, and the `VIBEPY_` prefix
is still dropped as Studio's own rendered configuration.

### An App's folder

```text
<root>/<app>/             the App's folder: install creates it, remove deletes it
<root>/<app>/env/         its virtual environment: update remakes this and only this
<root>/vibepy-studio/     Studio's own folder: logs/, routes/, traefik.yml, state.json
```

One rule for the whole root: **a direct child of the root is one distribution's folder, named by
its canonical distribution name**, and Studio is not an exception to it. Studio's folder is named
by its own `app_id`, which `entry.py` declares once and hands to `StudioRoot`; nothing writes the
string a second time. An App's folder is named for what it holds — one installed App — and the
environment is one thing inside it. `installer.environment(root, app_name)` returns
`…/<app>/env`, and the App name is still refused unless the join names a direct child of the
root. The rule is about the folder, not the lifecycle: Studio's folder holds no `env/`, because
Studio's own environment is wherever whoever installed Studio put it — an installer does not
install itself, and how Studio is installed is an open decision the owner holds. Because Studio's
folder exists, an attempt to install a distribution named `vibepy-studio` is refused as already
installed, which is true.

`install_app` creates the App folder, then the environment inside it. `update_app` removes and
recreates `env/` and touches nothing beside it. `remove_app` deletes the App folder whole. This
keeps the existing statement — remove leaves the data an App wrote *elsewhere* — exact: what the
App wrote inside its own folder is the App's, and goes with it.

Studio's four files move into Studio's folder and change in nothing else. A log is the Hub's
observation of a child, not the App's output, and it must survive `remove_app` so that why an
App failed can still be read. Supervisors keep a central child-log directory for the same reason.

The development root `.studio-dev` is recreated, not migrated; the repository is pre-production.

### The working directory

`Processes.start` runs the child with `cwd=<root>/<app>`. `describe` runs there
too when the Hub describes an installed App, so what the Hub runs for an App runs in one place. A relative path an App writes lands in its own folder; the Hub's folder receives nothing.

The folder is not announced to the App. It is the process's working directory, the same fact
`WorkingDirectory=` establishes for a systemd unit, and an App that wants a place it *knows* about
declares a path field in its configuration, as Todo does. A framework-provided data directory
would be a new field on every App's contract and is an open decision, not this milestone's.

### The child's life is the Hub's window

`Processes.start` opens the child with `stdin=PIPE`, holds the write end for as long as the Hub's
window is open, and passes `serve` one more argument:

```text
<env>/bin/python -I -m vibepy_core.serve <app> --port <n> --until-stdin-closes
```

With that flag `vibepy_core.serve` reads standard input until end-of-file and, on reaching it,
sets uvicorn's `should_exit`, so the server leaves its loop, closes the served application's
lifespan, and the process ends through its normal shutdown. Without the flag the command behaves
as today and never touches standard input.

The flag is explicit because the rule is the launcher's, not the command's. A process manager
gives a service `/dev/null` as standard input (systemd's `StandardInput=null` default, `nohup`),
and a command that ended on end-of-file regardless would end at once under exactly the
deployment an operator is most likely to choose. The Hub, which holds the pipe, says so; nothing
else is inferred from what standard input happens to be.

This is the pipe pattern the MCP stdio transport specifies — the client ends the server by closing
stdin — applied to the Web channel process. It needs no platform branch: on every platform the
Hub runs on, a process that terminates for any reason has its handles closed by the operating
system, so the child sees end-of-file whether the Hub exited, crashed or was killed. It is not pid
polling, which races pid reuse and asks the child to know its parent. PEP 446 keeps the pipe's
write end out of every other child the Hub starts, so no `uv` process keeps an App alive.

`serve` still reads no configuration from standard input. What it gains is a lifetime rule its
launcher may ask for — the process lives while its standard input is open — which is the rule
`mcp` already has, so `packaging.md` can say: a channel process ends when the host that started it
closes its standard input.

`stop_app` is unchanged: terminate, then kill. Closing the pipe is what happens when the Hub is
not there to do that.

### What this milestone does not isolate, and why

The isolation this milestone provides is against accidents, between Apps an operator chose to
install: dependency conflicts, path collisions, crashes, orphaned processes. It is not a security
boundary between mutually distrusting Apps. On both platforms the Hub runs on, processes of one
user account are one security principal — each can read another's memory, environment and
files — and separating them needs another principal per App (Android, `DynamicUser=`) or a
sandbox (snap, flatpak), which changes what a local Hub is. Comparable hosts of the local Hub's
kind — pipx, conda, Homebrew services — draw the same line. This is recorded as a decision (see
Documentation) so that what follows from it is a consequence and not an omission:

| Not provided | Follows from |
| --- | --- |
| an App cannot reach another App's port on loopback | same principal |
| an App cannot read another App's folder | same principal |
| a secret in an App's environment is invisible to other processes of the user | same principal; ADR-033's channel |
| CPU and memory limits | no mechanism common to macOS and Windows; bounding an invocation's time is M20's `timeouts` |

Shared inodes are stated rather than removed. `uv pip install --link-mode hardlink` gives every
App's environment the cache's inodes for the files it holds, for the measured reason in
`installer.install`. The premise that makes sharing correct is that installed files are immutable
— pnpm, Nix and uv itself rest on it — and the docstring states half of it, that the Hub never
writes inside an environment. The other half is the App's: an App does not modify its installed
files in place. It joins the invariant table as a contract of the same kind as the third row —
kept by convention, not enforceable by packaging.

## Package layout

| Module | Change |
| --- | --- |
| `vibepy_studio/internals/processes.py` | one function building an App-environment command with `-I`; `DESCRIBES_THIS_PROCESS` without `PYTHON*` |
| `vibepy_studio/internals/describing.py` | uses it |
| `vibepy_studio/authoring/tools/invocation.py` | uses it |
| `vibepy_studio/operating/internals/installer.py` | `<app>/env`; App folder created, removed; environment remade alone |
| `vibepy_studio/operating/internals/root.py` | takes `own` (Studio's `app_id`); `app_folder(app_name)`; `remove_app_folder`; its own files under `<root>/<own>/` |
| `vibepy_studio/operating/internals/routing.py`, `state.py` | write under the directory they are given, which is now Studio's folder |
| `vibepy_studio/entry.py` | declares `APP_ID` once; `StudioRoot(path=..., own=APP_ID)`; logs under Studio's folder |
| `scripts/run_studio.py` | waits for `traefik.yml` in Studio's folder |
| `vibepy_studio/operating/internals/processes.py` | `cwd`, `stdin=PIPE` held per child, closed on release |
| `vibepy_studio/operating/tools/installation.py` | remove deletes the folder; update remakes the environment |
| `vibepy_core/serve.py` | `--until-stdin-closes`; a thread reads stdin to EOF and sets `should_exit` on the running `uvicorn.Server`; `uvicorn.run` becomes `Server(Config(...)).run()` so the server object is reachable |
| `fixtures/timer-app` | one read-only Tool, `probe`: returns `cwd`, `sys.path` and whether a named module imports; the `home` Page declares and renders it, so the running process is what a test reads |

No new module. One new public type in `vibepy_core`: `WindowRecord` and `read_window_record`
(`vibepy_core.app.record`). The lifespan's exit has to be visible from outside the process, and the
framework already has the contract for that — a JSON record per line on standard error — so closing
a window writes one, instead of an App leaving a file behind for a test to find.

## Data flow

```text
start_app
  → Processes.start(interpreter=<root>/<app>/env/bin/python,
                    cwd=<root>/<app>, stdin=PIPE, env=child_environment()+VIBEPY_*)
  → <python> -I -m vibepy_core.serve <app> --port <n> --until-stdin-closes
       serve: load_app → build_web_app → Server.run(); a thread blocks on stdin.read()
  Hub window closes / Hub dies → OS closes the pipe → stdin.read() returns b"" → should_exit
  → uvicorn leaves main_loop → lifespan exits → process ends
```

## Errors

No new code. A child that ends because its stdin closed is a normal exit: `serve` returns 0 and
writes no report. `StartFailed`, `AlreadyStarted` and the `hub.*` refusals are unchanged.

## Testing

Acceptance, `packages/vibepy-studio/tests/test_isolation.py` (one subject: what one installed App
can and cannot reach of another and of its host):

- two Apps installed and started in one Hub; the first's process is killed from outside; the
  second still answers HTTP, `list_apps` reports the first `installed` and the second `running`,
  and `start_app` of the first succeeds again
- a module planted in a fake user site-packages and in a `PYTHONPATH` directory set on the Hub is
  not importable from a started App, and the Hub's current directory is not on the App's
  `sys.path` — read from Timer's served `/home` Page, which renders `probe` in the running process
- a started App stands in its own `<app>/`, read from inside the running process; what lies
  beside `env/` survives `update_app` (`test_update.py`) and goes with the folder on `remove_app`
  (`test_installation.py`)

`test_processes.py`: a driver process that starts a child through `Processes` and then blocks is
killed with no chance to clean up; within a bound the child has ended and its port no longer
answers. `test_child_environment_drops_vibepy_prefixed_variables` stays: `VIBEPY_` is still the
launcher's to drop. `test_a_cancelled_start_leaves_no_live_child` and
`test_closing_a_window_releases_every_child` stay as they are.

`tests/test_serve_command.py`: with `--until-stdin-closes` and a pipe on stdin, closing the pipe
ends the command with exit 0 and its lifespan's exit ran; without the flag, the existing test that
stdin is never waited on stays as it is.

`test_installation.py`, `test_update.py`, `test_addresses.py`, `test_state.py`: paths follow the new layout; update leaves a file beside `env/` in place; `traefik.yml`, `routes/` and `state.json` are read under `vibepy-studio/`.

## Compatibility

`envs/<app>` becomes `<app>/env`; an existing root is recreated. The four commands'
existing arguments are unchanged; `-I` is the launcher's flag, and `--until-stdin-closes` is
opt-in, so `run_studio.py`, the tests and a terminal user see `serve` behave as before.

## Documentation

- new ADR: *Isolation between installed Apps is against accidents, not adversaries* — records
  the trust model above, why per-App environments and processes under one principal are the
  chosen class (pipx, conda), what a security boundary would have cost, and that the same
  decision places network, filesystem and secret visibility between Apps outside the Hub
- new ADR: *A channel process lives while its host holds its standard input* — records why the
  child's life is bound to the Hub's window (ADR-020's consequence), why the pipe rather than pid
  watching or a platform facility, and that this makes the Web and Agent channel processes obey
  one rule
- `docs/architecture/packaging.md`: The isolation invariant — the third row is kept by
  construction and by `-I`, with the test that proves it; a fourth row for immutability of
  installed files; the `-I` flag in each command's invocation; a channel process ends when its
  standard input closes, when its launcher asked for that
- `docs/architecture/lifecycle.md`: the root's one rule and the folder layout, Studio's own folder
  included; the working directory; the Hub's death ends its children
- `installer.install` docstring: the App's half of the immutability premise

## Out of scope

- a data directory the framework announces to an App — a new configuration field on every
  App's contract; recorded as an open decision
- re-adopting children across a Hub restart — needs persisted child identity and a way to
  observe an arbitrary pid, which the process module already rules out
- CPU, memory or invocation-time limits — M20
- log rotation — M20
- a security boundary between Apps — the trust-model ADR
- how Studio itself is installed, updated and removed — decided as ADR-040 (Proposed) on this
  branch; its implementation (the bootstrap application, the `gui_scripts` entry point that
  retires `scripts/run_studio.py`) is a follow-up after M17, and this milestone only builds the
  root layout that implementation will use
