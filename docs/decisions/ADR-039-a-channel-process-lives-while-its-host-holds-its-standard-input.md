# ADR-039: A channel process lives while its host holds its standard input

Status: Accepted

## Context

ADR-020 places a channel's runtime inside its host's window: there is no state in which an App is
constructed but not running, and a control plane that stops a channel stops its process. ADR-017
has the agent platform end the Agent channel process — the MCP stdio transport ends a server by
closing its standard input and terminating the subprocess.

The Web channel process did not obey either. Studio started it with `stdin=DEVNULL`, and nothing
bound the child's life to the window that started it. A Studio that died without cleanup — killed,
crashed, or a machine that went down — left a served App running: the next Studio reported that
App `installed`, could not stop it, could not start it because its port was held, and the proxy
still routed to a process nobody owned. That is precisely the state ADR-020 says does not exist.

Two models exist for binding a child's life to its host. Re-adoption keeps a record of the child
and reclaims it after a restart — Docker's live-restore, systemd's cgroups — and needs persisted
child identity plus a way to observe a process the observer did not start.
`vibepy_studio/operating/internals/processes.py` already rules that out: only a parent observes
its own children, and Python's `subprocess` documents no way to observe an arbitrary pid; pid
polling additionally races pid reuse and asks a child to know its parent. Linkage instead ties the
child to a live connection and lets it leave when the connection ends — the LSP client's
`processId`, MCP stdio, Erlang's process links.

## Decision

A channel process its host starts lives while that host holds its standard input.

Studio holds the write end of a pipe to the child for as long as its window is open, and tells
`serve` the rule with `--until-stdin-closes`; on end-of-file the command ends the server through
its normal shutdown. `docs/architecture/packaging.md` owns the command and the flag.

The flag is explicit because the rule belongs to the launcher, not to the command. A process
manager hands a service `/dev/null` as standard input — systemd's `StandardInput=` defaults to
null, as does `nohup` — so a command that ended on end-of-file unconditionally would end
immediately under the deployment an operator is most likely to choose. The party holding the pipe
says so; nothing is inferred from what standard input happens to be.

Rejected: **re-adoption across a restart**, for the reason above; **pid watching**, which races
pid reuse and inverts who observes whom; **a platform facility** (job objects, cgroups,
`prctl(PR_SET_PDEATHSIG)`), each of which exists on one platform and would put a branch where one
rule suffices.

## Consequences

- No platform branch. A process that terminates for any reason has its handles closed by the
  operating system on both platforms Studio runs on, so the child sees end-of-file whether its
  host exited, crashed or was killed. PEP 446 makes the pipe non-inheritable, so no other child
  Studio starts holds an App alive.
- The Web and Agent channel processes obey one rule, arrived at from two directions: the MCP
  client's and Studio's. A reader learns one lifetime rule for a channel process, not two.
- `serve` still reads no configuration from standard input. What it gained is a lifetime, not a
  second configuration channel, and ADR-033 remains the only one.
- A Studio that restarts finds no child to re-adopt, because there is none running: the state the
  gap produced cannot occur, rather than being repaired after the fact.
- `stop_app` is unchanged and remains how a running App is stopped deliberately. Closing the pipe
  is what happens when nobody is there to do that.
