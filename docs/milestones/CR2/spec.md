# CR2 - Hub defects

CR2 is not a `docs/roadmap.md` milestone. Its scope and its place in the sequence come from
`docs/milestones/code-review-roadmap.md`, and the findings it acts on are I2, I7, I8, I9, I10,
I11, I16, I17, I18, I19, I21, I22 and I24 in `docs/milestones/code-review/findings.md`.

Thirteen defects in the Hub, one shape: **a failure or a resource that crosses a boundary loses
the guarantees that hold inside one.** The boundary is a name in five of them, a process in
three, a file in two, and the loop in one. The happy path of every Hub Tool was thought through;
the failure paths were not.

The root is identity. One App has four names today — a source folder's name, its distribution
name, the name it declares itself under, and its `app_id` — and the Hub accepts two of them,
files the environment under whichever arrived, and keys its listing by a third. Unifying that
dissolves I11 and I18 together, and every remaining defect is a failure path that becomes
statable once there is one name to state it about.

## Acceptance criteria

- an App is addressed by one name across install, configure, start, stop and list; installing by
  a project name and by a folder name cannot produce two rows
- the App a Hub starts is the App its facts describe, joined by identity rather than by position
- no Hub Tool handler performs filesystem, process or metadata work on the event loop
- a child process is owned from the moment it exists, so cancellation or a broken stdin cannot
  leave one the window cannot release
- a failed install leaves no environment behind, and a source folder that has disappeared yields
  a diagnostic rather than an exception
- `config.invalid` and the fields that failed survive the process boundary into the Hub's answer
- one failure model reaches an agent, carrying the category that says whether a retry can succeed
- Hub state survives a concurrent write and an interrupted one
- `start_app`'s `secrets`, `hub.already_running` and `hub.declaration_missing` have tests, and
  the Hub tests that assert less than their names claim assert what they claim
- the Todo example writes to the path it declares, ships no test scaffolding, and narrows a Tool
  result by validation rather than by `assert`

## Sources

| Contract | Source |
| --- | --- |
| an installed distribution is addressed by its name, and two names are compared by normalizing: lowercase, with runs of `.`, `-` and `_` replaced by a single `-` | PyPA, *Project name normalization* (<https://packaging.python.org/en/latest/specifications/name-normalization/>) |
| `packaging.utils.canonicalize_name` is that specification's implementation | PyPA, *packaging* (<https://packaging.pypa.io/en/stable/utils.html>) |
| one environment per installed package, named after the package, with what was installed recorded beside it | pipx, *How pipx works* (<https://pipx.pypa.io/latest/explanation/how-pipx-works.html>) |
| the name on the left of a `vibepy.apps` entry point is the App's name inside its distribution | `docs/architecture/packaging.md` |
| an `AppRef` carries the declared name, the distribution and its version, and reading it imports nothing | `docs/architecture/packaging.md` |
| the self-description command writes one JSON object per declared App, and a failure writes the framework's code and message to standard error and exits 1 | `docs/architecture/packaging.md` |
| a window validates the App's configuration before it enters the lifespan, and raises `config.invalid`, category `caller`, naming every field that failed | `docs/decisions/ADR-022`, `docs/architecture/app-model.md` |
| a window that refuses to open exits the process with a non-zero status, which is what makes a refusal legible to whatever started it | `docs/decisions/ADR-026` |
| `caller` means the call itself was wrong and a different call may succeed; a caller reads the category to learn whether a different call could succeed | `docs/architecture/errors.md` |
| an exception raised by an App's own code is described, not classified; `app.unhandled` belongs to no exception class | `docs/architecture/errors.md` |
| a Tool's expected, actionable failure travels as a `Diagnostic` field, because an output model is revalidated and no exception instance can travel in one | `docs/decisions/ADR-007`, `vibepy_hub/models.py` |
| ToolRuntime permits concurrent invocations and must not serialize them; overlapping mutation of domain state is the App's own responsibility | `docs/architecture/runtime.md` |
| overlap is proven by a barrier and not by a duration; a passing run asserts nothing about elapsed time | `docs/architecture/runtime.md` |
| a handler that blocks the event loop serializes every channel in its process, so blocking calls are wrapped in `asyncio.to_thread` | `docs/architecture/runtime.md`, `AGENTS.md` |
| the Hub is an App and is subject to every rule an App is subject to, and its Tools are its whole public surface | `docs/decisions/ADR-024` |
| an App declaring no Pages has no Web channel and therefore no runtime for the Hub to start | `docs/decisions/ADR-017` |
| the Hub holds an App's values per installation, secrets included, and gives a secret's value back to no channel: it reports such a field as set | `docs/architecture/lifecycle.md` |
| a secret is distinguished by its declared type, and `SecretStr` projects as `format: password` | `docs/decisions/ADR-022` |
| `os.replace` overwrites the destination and the rename is atomic where POSIX requires it | Python, *os* (<https://docs.python.org/3/library/os.html#os.replace>) |
| a subprocess's `stderr` accepts a file-like object, so a child's diagnostics need no pipe the parent must drain | Python, *asyncio event loop* (<https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.subprocess_exec>) |
| `[project].name` is required, is one of the keys that must be defined statically, and a build back-end must raise an error if it appears in `dynamic` | PyPA, *pyproject.toml specification* (<https://packaging.python.org/en/latest/specifications/pyproject-toml/>) |
| a child that fills a pipe's buffer blocks, which is why a parent that does not drain one does not use one | Python, *subprocess* (<https://docs.python.org/3/library/subprocess.html#subprocess.Popen.communicate>) |
| a process supervisor puts one program's standard error in a file of its own | supervisord, *Configuration* (<http://supervisord.org/configuration.html>) |
| a keyed digest over stored bytes is `hmac` with `compare_digest`, not a scheme of ours | Python, *hmac* (<https://docs.python.org/3/library/hmac.html>) |
| a duplicate name fails at registration rather than disappearing silently | `docs/decisions/ADR-012`, `ADR-027` |
| filesystem paths are `pathlib.Path`, the public API is a product, and tests verify public contracts | `AGENTS.md` |

## Problem

**I11, I18 — one App, four names.** `_candidate_folder` matches a name against either a
distribution name or a folder name, `install_app` files the environment under whichever string
arrived, and `list_apps` keys its available rows by folder name alone. Installing `vibepy-notes`
therefore lists the same folder twice: `vibepy-notes` installed and `notes` available, and every
later Tool is keyed on the caller's accidental choice. One level down, the facts written at
install time join two lists — what the child's `describe` command reported and what
`discover_apps` read from the environment — **by index**, and they line up only because both
happen to sort the same way. `declared_name` is what `start_app` hands `vibepy_core.serve`, so a
mispairing starts a different App than the one whose facts were recorded. The same line drops
every App after the first without a word.

**I2 — the rule the Hub knows and applies once.** `asyncio.to_thread` appears twice in the whole
repository, one of them inside the Hub. `rmtree`, `iterdir`, `mkdir`, `read_text`, `write_text`,
`os.chmod` and TOML parsing run directly under roughly twenty `async def` handlers that
ToolRuntime explicitly permits to overlap. `list_apps` walks every environment and every
registered source synchronously, and M11 will put a Page on this same loop.

**I7 — a child owned by nobody.** The stdin write sits outside the `try` that kills the child,
and the child enters `_running` only after it answers. A `CancelledError` or a `BrokenPipeError`
therefore leaves a process neither killed nor owned, so `aclose()` cannot reach it — against
`entry.py`'s own promise that a window leaves no child behind.

**I8 — a code that becomes an integer.** The framework raises `config.invalid` inside the
lifespan, naming every field that failed. The Hub inherits the child's stderr and reports `"the
App exited with N"`. The `caller` category — the one that says a different call could succeed —
is lost at exactly the failure most likely and most fixable, and the Hub's own mockup renders
that field list to a human (`docs/hub-ui-mockup.html`).

**I9 — two failure vocabularies through one edge.** `Diagnostic` carries code, message and
details and rides inside a successful result; `ErrorInfo` carries those plus a category and
rides inside a failure. Eight `hub.*` codes answer no retryability question, and an agent
calling `start_app` must read `isError` *and* an optional `diagnostic` field to learn what
happened.

**I10 — state that a second call or a crash can lose.** `write_state` truncates the file in
place, with no temporary file and no lock, while the Hub is the one App in this repository
guaranteed to receive concurrent calls. What is lost is configuration, secrets included.

**I16, I17 — failure paths that escape the module's own vocabulary.** `purelib(env)` sits
outside the `except InstallFailed` block and can itself raise it, leaving an environment with no
facts file; the next `list_apps` takes the branch that calls `purelib` again and raises out of
the listing Tool. And `candidates()` calls `source.iterdir()` unguarded, so a source folder that
has been moved or unmounted makes `list_apps`, `install_app` and even `remove_package_source` —
the Tool that would fix it — raise `FileNotFoundError`. `hub.source_unreadable` already exists
for this.

**I19 — an output type that is unsafe as an input type.** A held secret reads back as the literal
string `set`, and there is no read-only configuration Tool, so the natural round trip writes
`set` over the real secret. The Hub deliberately does not validate, so the corruption surfaces
later as a failed start. The Hub's mockup performs exactly this round trip
(`docs/hub-ui-mockup.html:876-878` sends the stored value when an untouched secret's input is
left blank, and the stored value is `set`).

**I21, I22 — tests that assert less than their names claim.** "leaves its data" checks a file
that lies outside the tree `remove_app` deletes, and which `TodoStore` never writes. "so a
restart needs no one" never restarts and reads the state file's internals instead of the public
contract. "a description is obtained without this process loading the App" never asserts that
this process did not load it. `start_app`'s `secrets` is passed `{}` by all six invocations,
because the only secret-declaring sample declares no Pages and cannot be started.

**I24 — the file an app author copies.** `TODO_CONFIG` ships a POSIX `"/tmp/..."` string inside a
distributed module, `TodoStore` declares `db_path` and keeps a list in memory, and the Page
narrows a Tool result with `assert isinstance`, which `python -O` strips.

## Decisions

Two are recorded. Every other change applies a record that already exists.

**ADR-028 — an App is addressed by its distribution name.** The Hub needs one name for an App,
readable before installation and after it, and the candidates were the source folder's name, the
name declared in the entry point, and the distribution name. The distribution name is the only
one readable on both sides: it is `[project].name` before, dist-info metadata after, and the
specification for comparing two of them is published. The declared name is not statically
reliable — a build backend may add entry points — and a folder with no visible declaration is
still offered here, so an identity taken from the entry point would leave such a folder with no
address at all. The folder's name is not packaging metadata; it is the accidental choice I11
complains about. The precedent is exact: pipx installs one environment per package named after
the package and records what it installed beside it, which is the shape the Hub already has.
axis 4's own fix proposed the folder name, and this record says why it was not taken.

The cost is stated: a user installs `vibepy-todo` rather than `todo`. It costs nothing on screen
— the Hub's mockup keys its rows by identity and displays the App's declared `name` and version
— and it is what R1 will key a stable port by.

**ADR-029 — an App's expected failures travel as data carrying a category.** `Diagnostic` was
invented without a record, and axis 4 and axis 7 both reached the same question from opposite
sides: is an App's expected failure data or an exception? It is data, for the reason ADR-007
already gives — an output model is revalidated, so no exception instance can travel in one — and
it carries `ErrorCategory`, because a category is what says whether a retry can succeed and an
agent should not have to hand-code that per code. The alternative, an App raising for an expected
failure, would make every actionable Hub answer a protocol error on the Agent channel.

This record is a gap A0 named and did not close. `code-review/decisions.md` lists the Hub's
`Diagnostic` vocabulary among three decisions that were live and undocumented, and states that
such a decision is written; no record in `docs/decisions/` mentions `Diagnostic`. CR3's criterion
that the unrecorded decisions are recorded therefore carries one fewer item.

Applied records, not decisions:

- one name for one addressable thing is ADR-016's principle at the Hub's own seam.
- wrapping blocking calls is `runtime.md`'s rule and AGENTS.md's convention.
- owning a child from birth is ADR-018's acquisition bound to release.
- reporting `config.invalid` with its fields is ADR-022's contract, carried across a boundary
  ADR-026 already says exits non-zero.
- refusing the masked sentinel as a value is ADR-012's "fails loudly rather than disappearing
  silently" applied to a field.

## Scope

1. **One name.** A candidate is addressed by its canonical distribution name. `install_app`
   resolves that name to a folder, files the environment under it, and `list_apps` keys every
   row — available, installed and running — by it. A project file's `name` is read as the
   specification defines it: required and static. A project file carrying none is not a
   candidate, which is how an unreadable one is already treated.
2. **Joined by identity.** `python -m vibepy_core.describe` reports the declared name and the
   distribution beside each description, and the Hub joins on them. A distribution declaring
   more than one App is refused with a diagnostic rather than truncated.
3. **Off the loop.** Every filesystem, subprocess and metadata call moves behind an `async`
   function in `internals/`, which wraps its synchronous body in `asyncio.to_thread`. No Hub
   handler and no lifespan calls one directly.
4. **Owned from birth.** A child enters the window's ownership immediately after it exists, and
   everything after the spawn is guarded so that any exception — `CancelledError` included —
   kills and reaps it. A stdin failure becomes `StartFailed`.
5. **A failure that survives the boundary.** The `serve` command validates configuration against
   the declaration before it hands the application to the server, and writes one JSON object of
   `code`, `category`, `message` and `details` to standard error for every failure it reports. A
   child's standard error goes to a file the Hub owns, and a failed start answers with the code
   the child reported.
6. **One failure model.** `Diagnostic` carries a category. Every `hub.*` code declares one.
7. **State that survives.** One `asyncio.Lock` in `HubDeps` guards read-modify-write, and the
   file is written to a temporary neighbour and moved into place.
8. **Failure paths inside the vocabulary.** A failed install removes its environment and answers
   with a diagnostic; an environment that cannot be interrogated becomes a row with a diagnostic
   rather than an exception out of `list_apps`; an unreadable source yields
   `hub.source_unreadable`.
9. **The masked sentinel is refused.** `configure_app` answers with a diagnostic when a declared
   secret field's incoming value is the masked form.
10. **The Todo example.** Its store writes its todos to the path it declares and stamps the
    file with an `hmac` digest keyed by the secret it declares, refusing a file whose stamp does
    not match under `compare_digest`. The secret it declares is therefore a secret it uses, and
    the mechanism is the standard library's rather than ours. It ships no configuration constant,
    and its Page narrows a Tool result by validation.

## Public API

| Change | Kind |
| --- | --- |
| `Diagnostic.category`, an `ErrorCategory`, required | added |
| `AppListing.diagnostic` | added |
| `hub.multiple_apps_declared`, category `declaration` | added |
| `hub.facts_unreadable`, category `execution` | added |
| `hub.secret_masked_value`, category `caller` | added |
| a category on each of the eight existing `hub.*` codes | added |
| `ServeConfigInvalidError`, code `serve.config_invalid`, category `caller` | added |
| the `describe` command's objects carry `app_name`, `distribution` and `distribution_version` | added |
| the name every Hub Tool takes for an App is now the canonical distribution name | changed |
| `packaging` becomes a dependency of `vibepy-hub` | added |
| `TodoConfig.db_key`, a required `SecretStr` the store keys its file's `hmac` digest with | added |
| `CandidateRow.name` narrows from `str \| None` to `str` | changed |
| `TODO_CONFIG` | deleted |

`serve.config_invalid` is a string the command already writes with no exception class behind it.
CR1 recorded it as CR2's, being the same path as I8; it becomes a framework exception under
ADR-019's rule, keeping the code it has already published.

The `describe` command's object gains three members and loses none, so a reader of the existing
members is unaffected. `AppDescription` itself is untouched: an entrypoint does not know the name
it is declared under, and the command does — it is iterating `AppRef`s already.

`Diagnostic.category` is required rather than defaulted, so that every construction site states
what kind of failure it is rather than inheriting a guess.

## Where each thing lives

**The canonical name.** `packaging.utils.canonicalize_name` is the specification's own
implementation, and P1 delegates where an authoritative library covers the problem rather than
writing a fourth normalizer. A canonical name contains only lowercase letters, digits and `-`,
so it is always one path segment and CR1's gate on the environment path is unaffected.

There is no folder this leaves unaddressable. `name` is required, is one of the keys the
specification says must be static, and a build back-end must raise if it appears in `dynamic`, so
a project file without one is not a project. The Hub read it as optional and carried a nameless
folder as a candidate anyway; reading it as required is the fix, and `CandidateRow.name` stops
being nullable with it. `version` stays optional, because a version may be dynamic.

**The identity join.** The Hub asks the environment two questions and joins their answers on the
distribution: `describe` reports what each declared App projects, and `discover_apps` reports
where each is declared. `AppFacts.declared_name` keeps its meaning — the name
`vibepy_core.serve` is addressed by — and is now read from the entry whose distribution is the
App being installed, rather than from index zero.

**The thread boundary.** `internals/` is where it sits, one `async` function per operation,
because pushing it to twenty call sites is what produced the defect. The handlers keep their
shape: an `await` replaces a call.

**The child's standard error.** A file rather than a pipe, which is what a process supervisor
does: supervisord gives each program its own `stderr_logfile`. The reason not to use a pipe is
the standard library's own: a child that fills the pipe's buffer blocks until the parent drains
it, so a parent that will not drain for the life of the child must not hand it one. A file object
is an accepted value for a subprocess's `stderr`, so no mechanism is written here. The file is
truncated at each start, and the Hub reads its tail when a start fails.

**The state lock.** In `HubDeps`, which is what a window owns, because that is where
`app-model.md` puts application-scoped state. It serializes the Hub's own state file and nothing
else, which is the domain row of `runtime.md`'s concurrency table and not a lock ToolRuntime
takes. Two Hub windows in two processes still race; that is a cross-process concern this stage
does not open.

## Errors

One row joins the framework's table in `errors.md`:

| Code | Category | Exception |
| --- | --- | --- |
| `serve.config_invalid` | caller | `ServeConfigInvalidError` |

`errors.md` also gains what ADR-029 decides: an App may publish an expected, actionable failure
as data inside its own output model, provided it carries the same `code`, `category`, `message`
and `details` an `ErrorInfo` carries. The framework's table stays the framework's; an App's codes
are the App's.

The Hub's own thirteen codes and their categories are tabled in `vibepy_hub/models.py`'s module
docstring, beside the `Diagnostic` they belong to. The Hub has no architecture document to carry
them — that is I13, and CR3 gives the Hub a document and promotes this table into it.

| Code | Category |
| --- | --- |
| `hub.candidate_absent` | caller |
| `hub.install_failed` | execution |
| `hub.no_app_declared` | declaration |
| `hub.multiple_apps_declared` | declaration |
| `hub.declaration_missing` | declaration |
| `hub.facts_unreadable` | execution |
| `hub.source_unreadable` | caller |
| `hub.not_installed` | caller |
| `hub.no_web_channel` | caller |
| `hub.already_running` | caller |
| `hub.not_running` | caller |
| `hub.secret_masked_value` | caller |
| `hub.start_failed` | execution |

`hub.source_unreadable` is `caller` in both places it is answered: removing the source and
calling again succeeds, which is what `errors.md` defines the category by.

A start that failed because the App refused its configuration answers with `config.invalid`,
category `caller`, and the failing fields in `details` — the child's own code, carried through,
rather than the Hub's. `hub.start_failed` remains for a child that failed for a reason it did not
describe.

## Testing

`make test` collects 189 tests where CR2 begins. What CR2 adds, per acceptance criterion:

- **one name** — installing by the distribution name and listing shows exactly one row for that
  App; installing by the folder name is refused as `hub.candidate_absent`; a name differing only
  in case or in `_` versus `-` addresses the same App. The existing test that makes the point
  that a folder's name is not a declaration keeps its subject and changes its name.
- **joined by identity** — an environment holding two distributions, each declaring one App,
  yields facts whose `declared_name` belongs to the App installed and not to whichever sorted
  first. A distribution declaring two Apps answers `hub.multiple_apps_declared`.
- **off the loop** — the ordering assertion `runtime.md` permits: a slow Hub Tool is started as
  a task and a light one is awaited, and the light one answers while the slow one is still
  pending. No elapsed time is asserted. On today's code the light call cannot answer first.
- **owned from birth** — a start cancelled while it waits for the child leaves no live child,
  and a child that dies before reading its stdin answers `hub.start_failed` rather than raising
  `BrokenPipeError` out of the Tool. The cancellation test drives `Processes` directly: no public
  surface can observe an orphan, which is the defect itself. AGENTS.md has tests verify public
  contracts, and this is stated as a departure, as CR1 stated its own.
- **config.invalid across the boundary** — the Todo App is configured with its path and started
  without its secret; the answer carries `config.invalid`, category `caller`, and names the
  missing field. Started with the secret in `start_app`'s `secrets`, it runs.
- **one failure model** — every `Diagnostic` a Hub Tool can answer with carries a category, and
  a test walks the Hub's Tools' output models to assert the field is not optional.
- **state survives** — two overlapping `configure_app` calls for two Apps both survive, so no
  update is lost. A write that fails as it moves the file into place leaves the previous state
  readable; this reaches `internals/state.py` directly, and is the second stated departure.
- **failure paths** — an install whose description step fails leaves no environment and answers
  with a diagnostic; a registered source that has been removed makes `list_apps` answer rows
  plus `hub.source_unreadable` rather than raising; an environment whose facts are unreadable is
  a row carrying `hub.facts_unreadable`.
- **the sentinel** — configuring a secret field with the masked value answers
  `hub.secret_masked_value` and leaves the stored secret intact.
- **`hub.already_running`** — starting a running App answers it. **`hub.declaration_missing`** —
  an environment whose App declaration has been removed lists with it.
- **the vacuous three** — "leaves its data" writes through the App's own Tool and asserts the
  file survives `remove_app`, which is now a real file at the declared path. "so a restart needs
  no one" opens a second window over the same root and starts the App without supplying the
  secret again, asserting through Tools and not through the state file. "a description is
  obtained without this process loading the App" asserts that the App's module is absent from
  `sys.modules`.
- **the Todo example** — a created todo survives a new store over the same path; a file stamped
  under a different key is refused rather than read; and the configuration the tests use is built
  from `tmp_path` rather than imported from the sample.

## Compatibility

The name every Hub Tool takes changes for any caller that installed by a folder name. Nothing
outside this repository consumes the Hub, and the change replaces a defect rather than a working
contract: the old behaviour produced two rows for one App and keyed later Tools on an accident.

`Diagnostic.category` is a required field on an output model, so an App reading a Hub answer
gains a member and loses none. `TodoConfig` gains a required field, which is a compatibility
event for the sample rather than for the framework — the mockup's Todo entry and the tests that
configure it are updated with it.

`TODO_CONFIG` is deleted from a distributed module. Its only consumers are two framework tests.

## Documentation

Only what CR2 makes false, plus the two records:

- `docs/decisions/ADR-028` and `ADR-029`, new.
- `docs/architecture/packaging.md` — the `describe` command's objects carry the identity of what
  they describe; the `serve` command reports every failure as one JSON object of code, category,
  message and details.
- `docs/architecture/errors.md` — one row in the table, and what ADR-029 decides about an App's
  own expected failures.
- `vibepy_hub/models.py` — the Hub's code and category table, until CR3 gives the Hub a
  document.
- `docs/hub-ui-mockup.html` — the key its rows join on becomes the distribution name, and the
  Todo entry declares the secret the sample now declares. Its own premise, that the
  self-description command reports an identity, is what Scope 2 makes true.
- `docs/milestones/code-review-roadmap.md` — L1 and CR1 are marked merged, which they are.

No existing record changes. ADR-024 is unaffected: the Hub stays an App, and CR2 makes it obey
two more of the rules an App obeys.

## Out of scope

- **R1's ports and addresses.** `free_port`, `RunningApp.url` and the proxy are R1's, and the
  identity this stage settles is what R1 keys a stable port by.
- **A read-only configuration Tool.** I19 is answered by refusing the sentinel, which is what
  the owner chose; a Tool that reads held configuration without writing it is new public surface
  no criterion asks for.
- **`AppRow.state` as a typed union** (axis 4, F9), the version stated twice in the Todo sample
  (F12), the entry-point group restated in the Hub (F13), `uv venv` pinning no interpreter
  (F14), no timeout on installation subprocesses (F15), `remove_app` calling a Tool handler
  directly (F16), `installed_facts` conflating two answers (F17), and `AppFacts.purelib` holding
  an absolute path (F18). The coordinator did not promote these to `findings.md`, and this stage
  implements its acceptance criteria and no more.
- **Every CR3 finding**, including the Hub having no architecture document, `authoring.md`, and
  the two import surfaces.
- **Cross-process locking of the Hub's state.** One window is what a lock in `HubDeps` covers.
- **The mockup's own save handler**, which sends the masked sentinel back for an untouched
  secret. The Hub refuses it after this stage; the screen that stops sending it is M11's, and
  `docs/hub-ui-mockup.html` is a design artifact whose home is Q4's open question.
