# ADR-038: Isolation between installed Apps is against accidents, not adversaries

Status: Accepted

## Context

`docs/architecture/packaging.md` states that an App is installed into an environment of its own,
and called that a contract rather than a guarantee. As of 2026-09-13 four things stood between
that contract and what the operating role did: the child interpreter ran without `-I`, so the
user's site-packages and stray `PYTHON*` variables reached an App; the child inherited Studio's
current directory, so every App writing a relative path wrote into one folder; an App's folder
*was* its environment, so it had no place that survived an update; and Studio's death left its
children running.

Closing them needs an answer to a question the invariant never asked: what is the isolation
*for*? The two readings lead to different products, and only one of them is reachable from where
Studio stands.

Processes of one user account are one security principal. On POSIX, same-uid processes reach each
other through `ptrace`, `/proc/<pid>/environ` and `ps -E`; on Windows, a process of the same logon
session opens another with `OpenProcess`. Nothing a launcher does with paths, working directories
or interpreter flags changes that, because none of it is a privilege boundary. The hosts that do
separate local applications from one another take one of two routes, and both change what the
host is: a principal per application — Android's per-app uid, systemd's `DynamicUser=` — or a
sandbox with a filesystem and network view of its own. The hosts of Studio's own kind — pipx,
conda, Homebrew services — run trusted code in per-application environments under one user and
draw the line where this record draws it. The sources are the two process models -- POSIX
(same uid: `ptrace`, `/proc/<pid>/environ`, `ps -E`) and Windows (same logon session:
`OpenProcess`) -- Android's per-app uid and systemd's `DynamicUser=` for the one class of host,
and pipx, conda and Homebrew services for the other.

Studio installs what an operator chose to install, from a wheelhouse that operator registered.

## Decision

Isolation between installed Apps is against accidents, not adversaries.

What it is against is the class of failure that arises between Apps an operator trusts and did
not intend to collide: dependency conflicts, import-name collisions, path collisions, a crash in
one App reaching another, and a process outliving the host that started it. Those are the
failures the installation model, isolated mode, the per-App folder and ADR-039's lifetime rule
remove, and `docs/architecture/packaging.md` owns what is enforced and how.

It is not a security boundary between mutually distrusting Apps. Studio does not attempt one, and
does not describe what it does as one.

Rejected: **a principal or a sandbox per App** — the mechanism that would make the boundary real,
and a different product. It changes installation, configuration, the proxy's reach and what an
operator must grant, and none of that is an increment on a local host that installs wheels.
**Per-App resource limits** — no mechanism is common to macOS and Windows, and a limit kept on one
platform only is a claim that is false where it is not kept.

## Consequences

- An App can reach another App's loopback port, read another App's folder, and read a secret in
  another App's environment. Each follows from one principal, and each is a consequence of this
  decision rather than a gap left in it.
- ADR-033's channel — configuration through the environment — is as private as the user account
  is, and no more. A secret is protected from other users by file access control, not from the
  user's own processes.
- CPU and memory limits are not part of isolation. Bounding how long one invocation may run is a
  separate concern with its own owner in `docs/roadmap.md`.
- Where a guarantee cannot be enforced it is written as a contract with its keeper named, which
  is why `docs/architecture/packaging.md`'s invariant table says what keeps each row rather than
  claiming all four alike.
- A boundary between distrusting Apps, should it ever be wanted, is a new record superseding this
  one, and a different shape of product beneath it.
