# T1 - What a test may build

T1 is not a `docs/roadmap.md` milestone and it acts on no code review. It exists because the gate
grew slow on a platform none of us runs, and the cost was measured rather than guessed: this
document carries the measurement, and the stage removes what it found.

One sentence states the whole of it: **a test builds a real App environment only when its subject
requires one.** No test is skipped, no marker excuses a test from the gate, and nothing that was
measured is hidden.

## The measurement

`scripts/bench_hub.py`, run once on each CI runner, times the operations a Hub test performs. The
run is `34501780568` on branch `bench-hub-cost`.

| Operation | macOS | Windows | Ratio |
| --- | --- | --- | --- |
| `install_app`, an App declaring Pages (`vibepy-todo`, `[web,agent]`) | 2.85s | **22.11s** | 7.8× |
| `install_app`, an App declaring none (`vibepy-notes`, `[agent]`) | 0.87s | **12.45s** | 14× |
| `start_app`, spawn until the child answers | 0.55s | 1.66s | 3.0× |
| `stop_app` | 0.11s | 0.00s | — |
| the child's `import nicegui` | 0.40s | 0.87s | 2.2× |
| hardlinked placement of one built environment (4.8k entries) | 0.78s | 5.04s | 6.5× |

The unit of that cost is files created, not packages resolved:

| Environment | Files | Distributions | Install, macOS | Install, Windows |
| --- | --- | --- | --- | --- |
| an App declaring no channel (`vibepy-core` alone) | **281** | 7 | 0.76s | not yet measured |
| `vibepy-notes`, `vibepy-core[agent]` | 1105 | 30 | 1.04s | 12.45s |
| `vibepy-todo`, `vibepy-core[web,agent]` | 3601 | 65 | 2.80s | 22.11s |

An App declaring no channel holds an eighth of `vibepy-todo`'s files. Most of the Hub suite's
subjects — installing, removing, listing, configuring, refusing — need an installed App and no
channel at all.

Installing is the whole of it. Starting, stopping and the child's imports together are under three
seconds on Windows, where one install of a Pages-declaring App is twenty-two. The Windows job runs
`make test` in 400s against macOS's 131s, and the Hub suite calls `install_app` 29 times — 21 of
them for an App declaring Pages.

Two things this measurement rules out. It is not the readiness poll: `READY_INTERVAL` is 0.1s and
a start costs 1.66s there. It is not a cold uv cache asymmetry: both jobs missed the action cache
identically, and `uv sync` alone is 241ms against 1.07s, the same ratio as everything else.

## Acceptance criteria

- a test builds an App environment only if its subject requires a real distribution or a real
  child process; every other test reaches its answer without one
- a test that needs an installed App installs the lightest App its subject allows, and installs it
  where it will be used: no environment is copied or linked into a second location
- `conftest.py`'s template-and-placement fixtures are gone, and nothing in the suite relocates a
  built environment
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
| "If we aren't careful, an error in the wrong spot might leave stuff from our tests behind"; "The safest and simplest fixture structure requires limiting fixtures to only making one state-changing action each, and then bundling them together with their teardown code" | pytest, *How to use fixtures* |
| a marker is registered in the `markers` ini option, selected with `-m`, and "Typos in function markers are treated as an error if you use the strict_markers configuration option" | pytest, *Working with custom markers* (<https://docs.pytest.org/en/stable/example/markers.html>) |
| "environments are inherently non-portable, in the general case… If for any reason you need to move the environment to a new location, you should recreate it at the desired location" | Python, *venv* (<https://docs.python.org/3/library/venv.html>) |
| a skipped test cannot fail, so the proxy is required rather than skipped | R1, in git history; `packages/vibepy-hub/tests/tests_support.py` |
| tests verify public contracts, not internals | `AGENTS.md` |

## Problem

**Most of what an environment costs is paid by tests that do not need one.** The Hub's failure
paths — an App no source offers, a name that is not an App's, a start refused because nothing is
installed, a configuration for an App that was never installed — are answered before any
environment is read. Several of them install one anyway, because installing was the shortest way
to arrange a Hub that looks used.

**Where an environment is needed, the heaviest one is often the one chosen.** An App declaring
Pages pulls the web stack, which is 22.11s on Windows against 12.45s for an App declaring none.
Twenty-one of the suite's twenty-nine installs take the heavy one, and only the tests about
addresses, starting and the proxy need a Page to exist at all. The two Pages-declaring fixtures
are not meaningfully different from each other — 2.68s and 2.78s locally — so the choice that
matters is Pages or no Pages, not which Pages App.

**Nothing marks the tests that pay it.** A test that builds an environment looks like any other in
the suite, so the cost grows without anyone deciding to spend it. The 400s job is what a reader
notices; which tests spend it is what `--durations=15` had to be switched on to see.

## Decisions

**An environment is arranged only for a subject that reaches one.** The rule is the test's subject,
not its convenience: if the answer comes from the Hub's own state, its diagnostics or its
declaration, the test arranges no environment. This is what removes the 22 seconds rather than
moving them.

**An install takes the lightest App the subject allows.** A Page in the subject means a
Pages-declaring App at 3601 files; the Agent channel in the subject means `vibepy-notes` at 1105;
a subject that is the Hub's own bookkeeping means an App declaring no channel at all, at 281. The
cost is files created, so this is where the seconds are, and it is why the channel-free fixture is
part of this stage rather than a nicety.

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

1. **Every Hub test that installs is judged by its subject.** For each of the 29 `install_app`
   calls: keep it if the subject requires a real distribution or child, otherwise arrange the Hub
   without one. `test_installation.py` is where installing is the subject and will keep most of
   its own.
2. **Every kept install takes the lightest App its subject allows.** A Page in the subject means a
   Pages-declaring App; the Agent channel in the subject means `vibepy-notes`; everything else — the
   installing, removing, listing and configuring subjects — takes the new channel-free fixture.
3. **`fixtures/bare-app`**, a workspace member declaring `vibepy-core` and no extra, one Tool and
   no Pages.
4. **The `integration` marker**, registered in `pyproject.toml` under `[tool.pytest.ini_options]`
   with `strict_markers = true`, applied to every test that builds an environment or starts a
   child — including the proxy tests and the framework's own `test_serve_command.py` and
   `test_dual_channel.py` if they cross the same boundary, which is checked rather than assumed.
5. **The measurement is reported.** The Windows job's time after the change, against 400s, in the
   merge commit message.
6. **`conftest.py`'s `_build`, `_place` and the template fixtures are deleted**, with every test
   that used them installing instead.
7. **`scripts/bench_hub.py` and `.github/workflows/bench.yml` are deleted** with the
   `bench-hub-cost` branch. Their numbers live in this document, and a benchmark nobody runs is a
   file that goes stale.

## What must not change

- **No test's meaning.** A test that arranged an environment for its own reasons keeps its
  assertions; only the arrangement changes. Where an arrangement was load-bearing and the reason
  was not obvious, the test keeps its install and gains the marker.
- **No test count.** 252 before, 252 after, none skipped and none deselected in the gate.
- **No timeout raised, no poll widened, no assertion loosened.** The measurement says these are not
  where the time goes, so touching them would hide rather than fix.
- **The Hub's public surface.** Making an environment reachable from outside a Hub root would let
  tests share one, and that is a product change for a test's benefit. Not here.
- **What an environment is.** Every environment a test uses is created by the Hub, at the path it
  is used from, by the same `install_app` a user calls. No test builds one by hand.

## The placement is removed rather than widened

`conftest.py` builds an App's environment once a session and hardlinks it into each test's Hub
root. CPython's `venv` documentation says an environment is "inherently non-portable, in the
general case" and that a move should be a recreation at the new location. The placement passes
today only because the Hub invokes the interpreter as `python -m`, so no script's shebang — which
carries the absolute path of the environment it was created in — is ever read. It works for the
reason the documentation's own caveat describes, not against it, and the moment anything runs a
console script from one of those environments it stops working.

So it goes. A test that needs an installed App installs it where it will be used, which is what
the documentation prescribes, and the cost of doing so is held down by the two decisions above:
far fewer tests need an environment at all, and the ones that do install the lightest App their
subject allows.

That makes one fixture necessary: an App declaring no channel, `vibepy-core` alone, 281 files
against `vibepy-todo`'s 3601. It is also the fixture the framework's own claim asks for — the core
declares no channel, and no fixture demonstrated an App that declares none either.

The second question this leaves — whether an App's environment should be reachable from outside a
Hub root, which would let one environment serve many tests — is not opened. It is a change to the
Hub's own surface for a test's benefit, and the numbers above say it is not needed to fix this.

## Testing

The suite is the subject, so the verification is the suite's own behaviour:

- `make lint typecheck test` passes, 252 tests, and `ruff check` proves the marker is registered
  because `strict_markers` turns an unregistered one into an error
- `uv run pytest -m "not integration"` passes and builds no environment; `uv run pytest -m
  integration` passes and is where the time is
- every test whose arrangement changed is run once with its assertion inverted, to prove it still
  fails for its own reason. A test that passes either way has lost its subject and is restored
- the Windows job's `make test` time and its `--durations=15` list, read from CI rather than
  predicted

No test is added. Nothing here is a new contract; this stage removes work, and the work it removes
is what the numbers above name.
