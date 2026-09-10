# T1 - What a test may build

T1 is not a `docs/roadmap.md` milestone and it acts on no code review. It exists because the gate
grew slow on a platform none of us runs, and the cost was measured rather than guessed: this
document carries the measurement, and the stage removes what it found.

One sentence states the whole of it: **an App's environment is built once a session and every test
that needs one is handed a copy; only a test whose subject is installing installs.** No test is
skipped, no marker excuses a test from the gate, and nothing that was measured is hidden.

## The measurement

`scripts/bench_hub.py`, run once on each CI runner, times the operations a Hub test performs. The
run is `34501780568` on branch `bench-hub-cost`.

| Operation | macOS | Windows | Ratio |
| --- | --- | --- | --- |
| `install_app`, an App declaring Pages (`vibepy-todo`, `[web,agent]`) | 2.85s | **22.11s** | 7.8× |
| `install_app`, an App declaring none (`vibepy-notes`, `[agent]`) | 0.87s | **12.45s** | 14× |
| hardlinked copy of one built environment (4.8k entries) | 0.78s | **5.04s** | 6.5× |
| `start_app`, spawn until the child answers | 0.55s | 1.66s | 3.0× |
| `stop_app` | 0.11s | 0.00s | — |
| the child's `import nicegui` | 0.40s | 0.87s | 2.2× |

The unit of that cost is files created: `vibepy-todo`'s environment holds 3601 files in 65
distributions, `vibepy-notes`'s 1105 in 30, and Windows charges for each. Installing is the whole
of it — starting, stopping and the child's imports together are under three seconds there, where
one install of a Pages-declaring App is twenty-two. The Windows job runs `make test` in 400s
against macOS's 131s.

The suite performs that install 29 times, 21 of them for an App declaring Pages, and copies an
already-built environment 8 times. Counted test by test, almost every install is by a test whose
subject needs an installed App — addresses arise from installing, starting needs an environment —
so removing installs that no subject requires would recover only three or four of the twenty-nine.
The cost is not needless installs; it is that each test builds for itself what the suite could
build once.

Two things the measurement rules out. It is not the readiness poll: `READY_INTERVAL` is 0.1s and a
start costs 1.66s there. It is not a cold uv cache asymmetry: both jobs missed the action cache
identically, and `uv sync` alone is 241ms against 1.07s, the same ratio as everything else.

## Acceptance criteria

- a test whose subject is not installing, removing or a failed install does not call
  `install_app`; it is handed a Hub root in which the Apps it needs are already installed
- that root is built once a session by the real `install_app`, through a Hub window like any
  caller's, and each test receives a hardlinked copy of it — no test reaches into the installer's
  internals to build one
- the tests that cross the distribution or process boundary are marked `integration`, the marker is
  registered, and a typo in it fails the run
- `make test` and CI run every test, marked or not; no test is skipped and no test is deselected by
  default
- the same 252 tests pass, and each still fails for the reason it was written for
- the Windows job's `make test` time is reported against the 400s baseline above

## Sources

| Contract | Source |
| --- | --- |
| the numbers above, and the run they came from | `scripts/bench_hub.py`, CI run 34501780568 |
| a fixture whose setup is expensive is created once per session, and "the fixture is destroyed at the end of the test session" | pytest, *How to use fixtures* (<https://docs.pytest.org/en/stable/how-to/fixtures.html>) |
| "The safest and simplest fixture structure requires limiting fixtures to only making one state-changing action each, and then bundling them together with their teardown code" | pytest, *How to use fixtures* |
| pip's own suite builds one virtual environment per session (`virtualenv_template`, `scope="session"`) and hands each test a copy of it (`virtualenv`: "a virtual environment which is unique to each test function invocation") | pypa/pip, `tests/conftest.py` (<https://github.com/pypa/pip/blob/main/tests/conftest.py>) |
| that copy is `shutil.copytree(self._template.location, self.location, symlinks=True)`, with no path in the environment rewritten | pypa/pip, `tests/lib/venv.py` (<https://github.com/pypa/pip/blob/main/tests/lib/venv.py>) |
| "environments are inherently non-portable, in the general case", because installed scripts' shebangs carry the absolute path of their interpreter | Python, *venv* (<https://docs.python.org/3/library/venv.html>) |
| a marker is registered in the `markers` ini option, selected with `-m`, and "Typos in function markers are treated as an error if you use the strict_markers configuration option" | pytest, *Working with custom markers* (<https://docs.pytest.org/en/stable/example/markers.html>) |
| a skipped test cannot fail, so the proxy is required rather than skipped | R1, in git history; `packages/vibepy-hub/tests/tests_support.py` |
| tests verify public contracts, not internals | `AGENTS.md` |
| the Hub regenerates `traefik.yml` every time a window opens, and it is the only root artifact that records the root's own path | `vibepy_hub/entry.py` (`write_install_config` in `hub_lifespan`), `internals/routing.py` |

## Problem

**Each test builds what the suite could build once.** Twenty-nine installs of three fixture Apps,
each one creating the same 1105 or 3601 files again in a directory of its own. pytest's guidance
for a resource that is expensive to build is a broader scope, and pip — the authority on the
environments in question — applies exactly that guidance to virtual environments in its own suite:
one template per session, a copy per test.

**The suite already has the pattern and uses it for eight tests.** `conftest.py` builds an
environment per fixture App once a session and hardlinks it into a test's root. It cannot serve the
other twenty-one because it places an environment and nothing else: no state row, no port, no
route, so any test that starts an App or asks for its address has to install for real to obtain
them. And it builds that environment by calling the installer's internals — `describe`, `install`,
`purelib`, `write_facts` — rather than the Tool a caller uses, which `AGENTS.md`'s rule about
public contracts does not allow a test to do.

**Nothing marks the tests that pay.** A test that builds an environment looks like any other, so
the cost grows without anyone deciding to spend it. `--durations=15` had to be switched on to see
which tests carried the 400 seconds.

## Decisions

**The template is a Hub root, not an environment.** Once a session, a Hub window is opened over a
fresh root and the real `install_app` installs each fixture App into it — `vibepy-notes`,
`vibepy-todo` and `vibepy-timer`, exactly as a user would, ports allocated and routes written. That
root is the template. A test that needs installed Apps is handed a hardlinked copy of the whole
root: environments, state, routes. This is pip's device applied one level up, and it is what lets
the tests about starting and addresses use it, because a copied root carries the port and the
route the environment alone did not.

**The copy rewrites one path and regenerates none.** Of everything a root records, two things name
the root's own location: `traefik.yml`, which `hub_lifespan` rewrites every time a window opens over
the root, so a copy is corrected the moment a test opens it; and each environment's facts file,
whose `purelib` the Hub recorded as an absolute path, which the copy rewrites as `_place` already
does. State records ports, names and the registered source paths, none of which is inside the root.
An environment's own `pyvenv.cfg` records the base interpreter, which is outside the root and does
not move.

**Copying an environment is standard practice for a test, and CPython's caveat is read for what it
covers.** The `venv` documentation calls an environment non-portable because installed scripts'
shebangs carry the absolute path of their interpreter. The Hub never runs one: it invokes
`<env>/bin/python -m`, which reads no shebang. pip's suite copies whole environments per test
without rewriting anything and is the reference implementation of the tool that created them.
An earlier draft of this stage proposed removing the placement on the strength of the `venv`
sentence alone; checking the authority's own practice reversed it, and this record says so.

**`install_app` is called only where installing is the subject.** Installing, removing, a failed
install, a folder that installs no App, one name spelled two ways — those tests drive `install_app`
because it is what they test, and they keep the cost. Everything else takes the copy.

**No channel-free fixture.** An App declaring no channel would be the lightest thing to install,
and it was considered: it is an App nothing can reach, because the Agent channel's adapter lives in
`vibepy-core[agent]`, so it would be a fixture that exists only for the test — the shape
`c5a3a2c` retired `plain-app` for. The three fixture Apps stay as they are.

**The marker is `integration`.** It names what those tests are — the ones whose subject crosses
into a real distribution or a real child process — rather than what they do to get there.
`installation` names the mechanism and `slow` names the symptom; pytest's own examples (`webtest`,
`slow`) are the test's nature, and its verb-form markers (`skip`, `parametrize`) are the ones that
change how a test runs, which this does not. It is registered in `markers` with `strict_markers`
on, so a mistyped marker fails rather than silently marking nothing.

**The marker selects; it never excuses.** `make test` and CI run everything. The documented
`--runslow` pattern, which skips marked tests unless a flag is passed, is rejected: a skipped test
cannot fail, which is the rule R1 set when it refused to skip the proxy, and a marker that hides
this measurement would answer the owner's instruction with the opposite of it. What the marker buys
is a name for the cost and `-m "not integration"` while developing.

**`--durations=15` stays.** It is what made this stage possible.

## Scope

1. **A session-scoped template root.** `conftest.py` opens a Hub window over a directory from
   `tmp_path_factory`, registers `fixtures/` as a source and calls `install_app` for each of the
   three fixture Apps, then closes the window. `_build`, its use of `describe`, `install`,
   `purelib` and `write_facts`, and the per-App template fixtures are deleted.
2. **A per-test copy.** A fixture hands each test a hardlinked copy of the template root, with each
   environment's `purelib` rewritten to the copy — `_place` generalised from one environment to a
   root. Which Apps a test needs no longer chooses a fixture: every copy holds all three, and a
   test that must show an App *absent* removes it or starts from an empty root.
3. **Every test that installs without installing being its subject takes the copy instead.** Each
   of the 29 `install_app` calls is judged: kept where installing, removing or a failed install is
   the subject; replaced by the copy everywhere else, the test's assertions untouched.
4. **The `integration` marker**, registered in `pyproject.toml` under `[tool.pytest.ini_options]`
   with `strict_markers = true`, applied to every test that builds an environment or starts a child.
   The framework's own `tests/test_serve_command.py`, `test_describe_command.py`,
   `test_channel_extras.py` and `test_dual_channel.py` are checked for the same boundary rather
   than assumed either way.
5. **The measurement is reported.** The Windows job's time after the change, against 400s, in the
   merge commit message, with its `--durations=15` list.
6. **`scripts/bench_hub.py` and `.github/workflows/bench.yml` are deleted** with the
   `bench-hub-cost` branch. Their numbers live in this document, and a benchmark nobody runs goes
   stale.

## What must not change

- **No test's meaning.** A test that installed keeps its assertions; only how the installed App
  got there changes. Where the arrangement was load-bearing in a way the copy cannot reproduce, the
  test keeps its install and gains the marker.
- **No test count.** 252 before, 252 after, none skipped and none deselected in the gate.
- **No timeout raised, no poll widened, no assertion loosened.** The measurement says these are not
  where the time goes; touching them would hide rather than fix.
- **The Hub's public surface.** No configuration is added to the Hub for a test's benefit. The
  template is built through `install_app` and read through the same Tools every test already uses.
- **The three fixture Apps.** No fixture is added or reshaped.

## Testing

The suite is the subject, so the verification is the suite's own behaviour:

- `make lint typecheck test` passes, 252 tests; `strict_markers` turns an unregistered marker into
  an error, so a passing run proves the marker is registered
- `uv run pytest -m "not integration"` passes and starts no child and builds no environment;
  `uv run pytest -m integration` passes and is where the time is
- every test whose arrangement changed is run once with its assertion inverted, to prove it still
  fails for its own reason; a test that passes either way has lost its subject and is restored
- the template root is built by `install_app` and by nothing else: `conftest.py` imports no name
  from `vibepy_hub.internals.installer`
- the Windows job's `make test` time and its `--durations=15` list, read from CI rather than
  predicted

No test is added. This stage removes work, and the work it removes is what the numbers above name.
