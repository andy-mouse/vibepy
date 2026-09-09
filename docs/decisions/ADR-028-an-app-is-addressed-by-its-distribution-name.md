# ADR-028: An App is addressed by its distribution name

Status: Accepted

## Context

Four names describe one App, and the Hub was using more than one of them as a key.

- The **folder name** inside a registered source. It is not packaging metadata. Nothing about a
  checkout's directory name survives installation, and two sources may hold folders that happen to
  be spelled alike.
- The **distribution name**, `[project].name`. It is required, must be defined statically, and a
  build back-end must raise an error if it appears in `dynamic`
  (<https://packaging.python.org/en/latest/specifications/pyproject-toml/>). After installation
  dist-info carries it. Two distribution names are compared by normalizing them — lowercase, with
  runs of `.`, `-` and `_` collapsed to one `-`
  (<https://packaging.python.org/en/latest/specifications/name-normalization/>), which
  `packaging.utils.canonicalize_name` implements
  (<https://packaging.pypa.io/en/stable/utils.html>).
- The **entry-point name**, the name on the left of a `vibepy.apps` entry. It is the App's name
  inside its distribution and is what `vibepy_core.serve` is addressed by. It is not statically
  reliable before installation, because a build back-end may add one.
- The **declared name** an App gives itself, which is display, not identity.

`install_app` matched a candidate on either the distribution name or the folder name, and then
filed the environment under whatever string the caller had passed. So one App installed twice
under two spellings produced two environments and two rows for one thing, and `list_apps` keyed
its available rows on the folder name while its installed rows were keyed on the caller's string.
An identifier that is sometimes one thing and sometimes another is not an identifier.

pipx faced the same question and answers it the same way: one environment per installed package,
named after the package, with what was installed recorded beside it
(<https://pipx.pypa.io/latest/explanation/how-pipx-works.html>).

## Decision

An App is addressed by its canonical distribution name — across `install_app`, `configure_app`,
`start_app`, `stop_app`, `remove_app` and `list_apps` — and that name is its environment's
directory name.

A name a Tool is given is canonicalized after the one-path-segment gate has passed it, so two
spellings of one name address one App. A candidate whose project file declares no name is not a
candidate.

## Consequences

- a user installs `vibepy-todo`, not `todo`. The folder name addresses nothing
- one App is one row and one environment, however it was spelled on the way in
- a project file without `[project].name` offers nothing, where it previously offered a candidate
  with no name at all
- `AppFacts.declared_name` stays, because the name `vibepy_core.serve` is addressed by is the
  declared one, not the distribution
- a stable port per App, when a later milestone needs one, has a stable key to hang on
- the Hub's own UI is unaffected: it keys rows by identity and displays the App's declared name
  and version
- the folder name was rejected. It is the accidental choice the review complains about, and it is
  not metadata at all. The entry-point name was rejected too: a build back-end may add one, so it
  is not statically reliable, and reading it requires installing first — which would leave a
  folder with no visible declaration unaddressable. The declared name is display, not identity
