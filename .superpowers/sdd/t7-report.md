# T7 — handlers hold pure paths

## Path → PurePath

Tool models (what a handler receives and answers with):

- `operating/models.py`: `SourcePathField` (so `SourcePath.path`), `CandidateRow.wheel`,
  `SourceListing.source`, `AppFacts.purelib`, `AppListing.source`.
- `authoring/models.py`: `InspectRequest.project`, `InvokeRequest.project`, and the error
  factories `uv_unavailable`, `environment_failed`, `project_not_found`, `no_apps_declared`,
  `from_report`.
- `operating/internals/state.py`: `HubState.source`.
- `operating/internals/wheels.py`: `Candidate.wheel`.

Facades and internals a handler calls:

- `operating/internals/root.py`: `install(wheel=, source=)`, `purelib()`, `interpreter()`.
  The constructor still takes a concrete `Path` and keeps it private.
- `operating/internals/installer.py`: `environment`, `interpreter`, `purelib`, `install`,
  `describe`, `read_facts`, `write_facts`, `installed_facts`, `remove_environment`,
  `declarations`, `environments`.
- `operating/internals/wheels.py`: `candidates`, `readable`.
- `operating/internals/state.py`: `read_state`, `write_state`.
- `operating/internals/routing.py`: `write_install_config`, `write_route`, `remove_route`.
- `operating/internals/processes.py`: `Processes.start(interpreter=)`.
- `authoring/internals/projects.py`: `locate`, `declared_name`, `python`.
- `operating/tools/packages.py`: `_unreadable(path)`; the module imports `PurePath`, not `Path`.

`authoring/internals/framework.py` carries no path.

## Where a concrete `Path` is now made

Each is inside a synchronous function that runs under `asyncio.to_thread`:

- `installer._read_facts`, `installer._write_facts`, `installer._remove_environment` (new),
  `installer._declarations` (new, hands `discover_apps` a `Path`), `installer._environments`.
- `wheels._candidates`.
- `state._read_state`, `state._write_state`.
- `routing._write_install_config`, `routing._write_route`, `routing._remove_route`.
- `files.is_directory` (new): the one `is_dir` both `installer.installed_facts` and
  `wheels.readable` needed. It lives in `files.py`, which owns the file system for the
  operating internals, so `wheels` does not import from `installer`.

`files.write_whole` keeps its concrete `Path` parameters: every caller is already a worker.

## Core (item 2)

`vibepy_core` carries `Path` in two places, both left alone:

- `app/config.py` maps the `Path` type to `ConfigFieldType.PATH` — that is an App's declared
  configuration, read at the composition site.
- `app/package.py`'s `discover_apps(*, path: Sequence[Path] | None)` — the I/O site itself;
  Studio now builds the `Path` at the call, inside a thread.

`ToolContext`, `DescribedApp`, `ConfigFieldDescription` and `AppRef` carry no path.

## Tests

- `test_package_sources.py`: new
  `test_the_paths_a_tool_answers_with_reach_no_file_system` — a `SourceListing` that came back
  through a Tool invocation carries `PurePath` values with no `is_dir`. It fails if a model
  field goes back to `Path`.
- `test_installation.py`: the one test that acted on `AppFacts.purelib` now makes its `Path`
  in a helper run through `asyncio.to_thread` (ruff ASYNC240 flagged the blocking call once
  the type was known).

## Windows

`PurePath` is `PureWindowsPath` there and `Path(pure)` is `WindowsPath`; drive letters and
backslashes survive the round trip through pydantic as strings. Nothing in this change
branches on platform. CI runs the gate on Windows.

## Gate

```
uv run ruff check .            All checks passed!
uv run ruff format --check .   122 files already formatted
uv run pyright                 0 errors, 0 warnings, 0 informations
uv run pytest                  369 passed in 180.06s (0:03:00)
```
