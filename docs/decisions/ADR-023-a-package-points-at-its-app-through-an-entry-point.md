# ADR-023: A package points at its App through an entry point

Status: Accepted

## Context

Nothing connects an installed distribution to the App inside it. `docs/architecture/lifecycle.md`
names `Package -> install -> configure -> open a channel`, and ADR-010 defers the executable
entrypoint to this layer, but no document owns it and no code implements it. A Host that has
just run `uv tool install my-app` has no way to ask what it installed.

A Host also cannot import an App to find out. `uv tool install` creates one virtual environment
per tool, whose `pyvenv.cfg` records `include-system-site-packages = false`
(<https://docs.astral.sh/uv/concepts/tools/>), and ADR-017 puts each channel in its own process.
Importing an App into the Host would put that App's dependency set in the Host's process and
undo both.

Python packaging cannot prevent two distributions from claiming one top-level import name. Core
metadata has no field for declaring a conflict; `Obsoletes-Dist` exists but "popular
installation tools ignore them completely"
(<https://packaging.python.org/en/latest/specifications/core-metadata/>), and
`packages_distributions()` maps one import name to a *list* of distributions
(<https://docs.python.org/3/library/importlib.metadata.html>), so the collision is representable
rather than excluded. Neither renaming our import package nor detecting a collision at runtime
removes that class of failure. Environment isolation does.

Python already has the declaration mechanism. Entry points are written to `entry_points.txt`
inside a distribution's `*.dist-info` at build time, a group name is any `^\w+(\.\w+)*$` string,
and a value is `importable.module:object.attr`
(<https://packaging.python.org/en/latest/specifications/entry-points/>). `importlib.metadata`
reads `.name`, `.group`, `.value`, `.module` and `.attr` from that metadata, while `.load()` is
the one operation that imports (<https://docs.python.org/3/library/importlib.metadata.html>).
`distributions(path=...)` points the search at an environment other than the running
interpreter's.

pytest and pluggy are the precedent for the declaration and the counter-example for the loading.
pytest finds third-party plugins through the `pytest11` group
(<https://docs.pytest.org/en/stable/how-to/writing_plugins.html>), and pluggy's
`load_setuptools_entrypoints(group)` "loads the associated modules into the current process"
(<https://pluggy.readthedocs.io/en/stable/api_reference.html>). That is right for pytest, whose
plugin is an extension of pytest itself. An installed App is a separate program.

## Decision

An App declares itself in the `vibepy.apps` entry point group, whose value names an
`AppEntrypoint` — the pairing of a definition with a lifespan that ADR-021 identified as the
composition root.

Inspection and loading are two operations, on the two sides of one line:

> What can be read without running is read from metadata. What requires an import happens in
> the App's own environment.

`discover_apps` reads `vibepy.apps` declarations out of distribution metadata and imports
nothing. `describe_app` loads one and projects it, and therefore runs in the App's own
interpreter — which a Host reaches by executing `python -m vibepy.describe` with that
environment's interpreter and reading JSON from its standard output.

## Consequences

- no manifest format is invented. An App's declaration is three lines in its own
  `pyproject.toml`, and every packaging tool already writes it
- the group name is metadata read as a string. It imports nothing and claims no distribution
  name on any index, so an App built on this framework acquires no dependency on any name being
  available on PyPI
- one group is defined. M19's Skill and MCP-server payloads declare further groups the same way,
  and this decision fixes how
- an entrypoint that cannot be resolved and an entrypoint that resolves to the wrong kind of
  object are different failures with different codes, so a Host can tell a broken installation
  from a wrong declaration. See `docs/architecture/errors.md`
- the isolation invariant has three parts and two enforcement boundaries. The framework
  guarantees the second and third — it publishes no operation that imports an App into its
  caller's process, and description runs under the App's own interpreter — and
  `tests/test_app_isolation.py` proves both. The first, one environment per App, is a
  requirement on the installation model that packaging cannot enforce: `uv tool install`
  satisfies it by construction, M10's Hub must install through such a mechanism, and M17 owns
  hardening it. This is the division ADR-017 already made — the framework states the contract,
  the host implements it
