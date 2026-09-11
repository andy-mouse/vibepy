# M11 - Hub UI

## Acceptance criteria

From `docs/roadmap.md`:

- Hub UI exposes Hub Core lifecycle capabilities without duplicating control-plane logic
- displayed App/package state reflects Hub Core state
- Hub UI remains a thin management interface over Hub Core

The screen is `hub-ui-mockup.html` in this folder: one board with a summary, one package
folder, and one row per App carrying a four-stage rail (Available, Installed, Configured,
Running), its actions, its diagnostic and its configuration panel.

## Sources

| Contract | Source |
| --- | --- |
| a Page consumes Tools through `ctx.tools.invoke` and owns no business logic; Tool errors are not translated | `docs/architecture/page-model.md` |
| a Hub UI consumes the Hub's Tools as any Page does, so it cannot duplicate control-plane logic | `docs/decisions/ADR-024-the-hub-is-a-platform-tier-app.md` |
| the Hub owns install, remove and upgrade | `docs/decisions/ADR-006-runtime-vs-package-lifecycle.md`, `docs/architecture/lifecycle.md` |
| an installed App is read from the file system, not from a record the Hub keeps | `vibepy_hub/tools/installation.py` |
| an App is addressed by its canonical distribution name | `docs/decisions/ADR-028-an-app-is-addressed-by-its-distribution-name.md`, `vibepy_hub/models.py` |
| an expected failure travels as data with a code and a category | `docs/decisions/ADR-029-an-apps-expected-failures-travel-as-data.md`, `vibepy_hub/models.py` |
| an App's window validates configuration as it opens and raises `config.invalid` | `docs/decisions/ADR-022-configuration-is-a-declaration.md` |
| prefer meaningful business operations over generic data mutation Tools | `AGENTS.md` |
| a wheel's file name is `{distribution}-{version}(-{build tag})?-{python tag}-{abi tag}-{platform tag}.whl`, and its `.dist-info` holds `entry_points.txt` | [Binary distribution format](https://packaging.python.org/en/latest/specifications/binary-distribution-format/) |
| entry points are read from `entry_points.txt` in the `vibepy.apps` group | [Entry points specification](https://packaging.python.org/en/latest/specifications/entry-points/), `docs/architecture/packaging.md` |
| `uv pip install` takes a path to a wheel; `uv build` builds a wheel into `dist/` | [uv: managing packages](https://docs.astral.sh/uv/pip/packages/), [uv: building](https://docs.astral.sh/uv/guides/package/) |
| installing and upgrading are separate operations, and an upgrade keeps what the install was given | [uv tools](https://docs.astral.sh/uv/concepts/tools/) (`uv tool install` replaces, `uv tool upgrade` "will retain the settings provided when installing"), [helm upgrade](https://helm.sh/docs/helm/helm_upgrade/) (`--reuse-values`), [Nextcloud occ](https://docs.nextcloud.com/server/latest/admin_manual/occ_apps.html) (`app:install`, `app:update`) |
| `ui.refreshable` redraws a builder's output; `ui.timer` calls a coroutine on an interval; `ui.dialog` awaits a result; `ui.notify` shows a message | [NiceGUI refreshable](https://nicegui.io/documentation/refreshable), [timer](https://nicegui.io/documentation/timer), [dialog](https://nicegui.io/documentation/dialog), [notify](https://nicegui.io/documentation/notify) |
| the `User` fixture drives a page without a browser | [NiceGUI user fixture](https://nicegui.io/documentation/user), `tests/conftest.py` |

## Problem

The Hub is headless: `HUB_APP.pages` is empty, and every operation is reached through the Agent
channel. The owner's direction is that App consumption is a human's work on the Web channel, so
this Page is the consumption Tools' only consumer, and the shape of Hub Core is judged by what the
Page needs.

Laid over Hub Core, the mockup shows four gaps. The Page cannot learn what an App declares or
holds, because `configure_app` writes and nothing reads. The mockup's Update has no Tool, although
ADR-006 gives upgrade to the Hub. Hub Core registers many folders where the mockup registers one,
and the only thing the plurality buys is the `hub.candidate_ambiguous` diagnostic. And the folder
holds built wheels, where Hub Core reads source folders with a `pyproject.toml`.

## Decision recorded separately

None. That the Hub owns upgrade is ADR-006's. The wheel source, the single folder and the shape
of the two new Tools are internal mechanisms with no contract outside the Hub, and go in commit
messages.

Two things raised here are not M11's and are recorded where they belong. Installing what else a
wheel carries — an MCP server registration, Skills — and observing the platforms that own them is
M19's, and `docs/roadmap.md` says so. A Tool declaring which channel exposes it is a framework
declaration the authoring milestones add; M11's Tools go to both channels as every Tool does.

## Scope

Hub Core changes first, so that the Page has something to be thin over; then the Page.

| Concern | Change |
| --- | --- |
| package source | one folder of wheels, replacing a list of source folders |
| installation | install from a wheel; `update_app`; `available_version` on a row |
| configuration | `describe_config` reads what `configure_app` writes |
| Page | `board`, at `/`, over the Tools above |

Not in scope: anything a wheel carries besides its Python package (M19); per-Tool channel
exposure (authoring milestones); restarting a running App on update (refused instead).

## Package source

`HubState.sources: list[Path]` becomes `source: Path | None`. `register_package_source(path)`
replaces whatever was registered; `remove_package_source()` takes nothing and clears it. In-house
deployment is one folder of built wheels, and two folders offering one App is a mistake to
prevent, not a case to explain. `hub.candidate_ambiguous` and its branches are removed.

`internals/projects.py` becomes `internals/wheels.py`. A candidate is a `*.whl` file directly
inside the source. Its distribution name and version are parsed from the file name; a file whose
name does not parse is not a candidate and is logged. When several wheels share one distribution
name, the highest version is the candidate — a wheelhouse keeps old versions, and that is not a
diagnostic. `declares_app` is read from `*.dist-info/entry_points.txt` inside the archive; a
wheel is a finished build, so this is a fact and no longer a hint.

`SourceListing` becomes `source: Path | None`, `candidates`, `diagnostic`. `CandidateRow.folder`
becomes `wheel: Path`.

## Installation

`install_app` installs the candidate wheel with `uv pip install --find-links <source>`, so the
wheel's dependencies — the framework first — resolve from the same folder: a wheelhouse carries
the framework's wheel beside the Apps', which is what makes it installable offline. Because
`declares_app` is a fact, `hub.no_app_declared` is answered before an environment is created. Everything after the
install — `describe`, `write_facts`, port and route — is unchanged, except that a port already
held in state for this name is reused rather than allocated, which is what lets an update keep
its address.

`update_app(app_name) -> Installation` replaces what the wheel installs with what the candidate
wheel installs, and keeps everything the Hub holds for the App: its configuration values, its port,
its route, and the data the App wrote elsewhere. Refusals, all `caller`:

| Code | When |
| --- | --- |
| `hub.not_installed` | no environment |
| `hub.candidate_absent` | the source offers no wheel of this name |
| `hub.up_to_date` | the offered wheel's version equals the installed `distribution_version` |
| `hub.already_running` | the App is running; the user stops it first |

The update itself is remove-environment then the install path above. If the install fails, the
environment is gone and the answer is the install's diagnostic; the row is `available` again with
its configuration and port still held, so the next `install_app` restores it. This is one
operation to a user and two to the Hub, which is what `update_app` exists to hide.

`AppFacts` and `AppRow` gain `distribution_version`, the version of the wheel that was installed,
which `vibepy_core.describe` already reports beside the App's own `version`. The two differ: an
App declares its version in its definition, a wheel carries its distribution's, and what an update
changes is the second. The board shows the second. `AppRow` gains `available_version: str | None`,
set only for an installed App whose candidate wheel's version differs from its `distribution_version`. `list_apps` already reads both; today it discards the
candidate once the App is installed.

`AppListing` gains `source: Path | None`, the registered folder. The board shows the folder and
its Unregister from one read rather than from what its own tab last registered, so a folder
registered through another window shows as the path it is.

## Configuration

`describe_config(app_name) -> ConfigDescription`:

```text
fields: list[ConfigField]   name, type, required
values: dict[str, object]   held values, secrets excluded
secrets_set: list[str]      secrets that have a value
diagnostic                  hub.not_installed
```

`type` is one of `string | path | integer | secret | other`, read from the projected schema's
`type` and `format` (`format: password` is a secret, `format: path` a path). The Page needs no more
of the schema than this, and reading more would make it the second validator ADR-022 places in the
App's own window.

`configure_app` is unchanged: an omitted secret is kept, and nothing the Page sends can blank one.

## Page

```text
packages/vibepy-hub/src/vibepy_hub/pages/
  board.py          the Page: layout, NiceGUI elements, Tool calls
  presentation.py   pure functions: a row's stage, marks and actions; a save request
```

`HUB_APP.pages = [Page(PageDefinition(name="board", route="/", title="Hub"), board)]`.

The mockup is an HTML/JS document; the implementation is Python on NiceGUI, as every other App's
Page is. Its JS rules — `stageIndex`, `renderActions`, `needsConfiguration`, `saveConfig` — become
`presentation.py`, which imports no NiceGUI. Its CSS is approximated with NiceGUI's Tailwind
classes: layout, states and wording match, pixels need not.

`board.py` draws three things: the summary (Available, Installed, Running counts), the source
card (a path input and Register when nothing is registered; the path and Unregister when
something is), and the App list. One `ui.refreshable` redraws all of it from one `list_apps`
result. It is refreshed after every action, and a `ui.timer` refreshes it every 3 seconds, so a
child that dies or an action taken elsewhere reaches the screen: displayed state is Hub Core state,
not the last thing this tab did.

Per row: name and version; the rail, with `!` on Configured when configuration is required and
`↑` on Installed when `available_version` is set; the diagnostic's code and message when there is
one; and the actions the mockup gives each state — Install for `available`; Stop for `running`;
Uninstall, Configure (when the App declares fields), and Update or Start otherwise. Start is
disabled while `configured` is false, because the App's window would only refuse. Uninstall and
Unregister confirm through `ui.dialog`. Every action's outcome, success or diagnostic, is a
`ui.notify`.

The configuration panel opens for one row at a time and calls `describe_config` when it opens.
A secret field is a password input, with a "(set)" placeholder when held. Save builds a
`configure_app` request through `presentation.py`: an empty secret is omitted, and a required field
with no value and no held secret is named in the panel and nothing is sent.

## Errors

The Page renders `Diagnostic` rows and never raises for one. A framework exception from a Tool
(`ToolInputValidationError` for a malformed path, say) propagates as `docs/architecture/page-model.md`
says, and NiceGUI renders it.

New Hub codes: `hub.up_to_date` (caller). Removed: `hub.candidate_ambiguous`. The table in
`vibepy_hub/models.py` is the authority and is updated.

## Testing

- `presentation.py`: one test file. The mockup's rules are the cases — which actions a state
  gets, when Start is disabled, what a save sends and what it withholds.
- Hub Core: existing shape, `hub(root)` and the `installed` fixture. `conftest.py`'s template
  root builds the three fixture Apps into one wheelhouse with `uv build` once per session and
  registers that folder. Update is tested by building a fixture again at a higher version into a
  second wheelhouse and registering it; the test asserts the held configuration, port and address
  survive.
- Page: the `User` fixture over a `page_runtime_for` of the Hub. The screen shows what `list_apps`
  answers; Install moves a row to installed; a save with a missing required field names it and
  calls nothing. Starting an App is a Tool test's subject and the Page tests do not start one.

## Compatibility

The Hub's Tools are its public API and this is a breaking change to two of them:
`register_package_source` replaces rather than appends, `remove_package_source` takes nothing,
and both answer with a single `source`. The Hub is `0.1.0` and its only consumer is this Page;
the change is made without a deprecation period and said so in the commit.

A Hub root written before this milestone is not migrated: an environment whose facts lack
`distribution_version` is reported as `hub.facts_unreadable`, and the App is uninstalled and
installed again. A state file's former `sources` list is ignored, so the folder is registered
once more.

## Documentation

- `docs/architecture/lifecycle.md`: the Hub Tool table gains `describe_config` and `update_app`;
  the source is one folder of wheels.
- `docs/architecture/packaging.md`: the isolation table's third row says the Hub installs with
  `uv venv` then `uv pip install` per App; it stays true and is left alone. "A static reading is
  a hint" lives in `vibepy_hub/internals/projects.py` and its tests, which this replaces.
- `vibepy_hub/models.py`: the code table.
- No ADR.

On integration, promote what is still true and delete this folder, mockup included.
