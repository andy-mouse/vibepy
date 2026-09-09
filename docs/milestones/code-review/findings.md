# Code review — consolidated, cross-checked
HEAD 05d6027 · baseline: make lint typecheck test passes (152 tests)
7 reviewers. Every item below was re-verified by the coordinator against the code.

## Verified — coordinator reproduced or read the cited code

### Critical
C1. Hub path traversal — remove_app/install write path
  hub/.../tools/installation.py:159, internals/installer.py:39, models.py:56
  AppName.app_name is an unconstrained str; environment() is a bare join.
  Verified by path resolution (no delete executed):
    '../../victim' -> /victim
    '/etc/passwd'  -> /private/etc/passwd   (absolute path discards root entirely)
  Reviewer reported only the '../..' case; the absolute-path case is worse.
  ADR-024 exposes every Hub Tool on the Agent channel -> model-controlled string reaches rmtree.

### Important — agreed by 2+ axes independently
I1. AppNotDeclared outside the exception hierarchy  (axis3, axis5, axis7)
    serve.py:33 derives from Exception. No code, no category, no errors.md row.
    test_errors.py walks VibepyError.__subclasses__() so it structurally cannot see it.
    Same edge writes JSON+code for every other failure (serve.py:99-102) and prose for this one.
I2. Blocking I/O on the event loop across Hub handlers  (axis3, axis4)
    ~20 sites. to_thread appears exactly twice in the whole repo, one of them installer.py:68
    in the same package — the rule is known and applied once.
I3. Routes outlive the window; three documents say otherwise  (axis2, axis3, axis6, axis7)
    web.py:45 mutates NiceGUI's process-global table; nothing unregisters.
    application.py:38-41 + adapters.md:77-80 + app-model.md state it as a property.
    test_nicegui_adapter.py:1-6 admits the test fixture does the cleanup.
I4. No Agent-channel command exists  (axis6 C1, axis7 I6)
    Verified: no [project.scripts] in any of the 4 pyproject files.
    app-model.md:88-90 and packaging.md say the MCP client launches a command.
    samples/notes (the agent-only sample) is therefore reachable by nobody.
    ADJUDICATION: axis2 called this "a decision ahead of its milestone, not a defect" —
    correct about ADR-010 (a why-document may record a future decision), wrong as a
    verdict, because axes 6/7 judged the architecture docs, which AGENTS.md makes
    current truth. Finding stands against the architecture docs, not against ADR-010.
I5. PageRegistry.definitions() is dead, and 3 places say it is used  (axis2, axis6)
    register_pages iterates definition.pages; definitions() has no non-test caller.
    page-model.md:135-136 and registry.py:29 docstring both assert the adapter uses it.
I6. Duplicate Page name silently serves one handler on two routes  (axis2)
    web.py:34-45 validates route uniqueness only; registry.py:18 overwrites by name.
    Contradicts ADR-012's stated rationale (fail loudly, not disappear silently).
I7. Child process orphaned on cancellation / stdin failure  (axis3, axis4, axis7)
    processes.py:166-177: stdin write sits OUTSIDE the try; _running is populated only
    after readiness. CancelledError or BrokenPipeError -> child neither killed nor owned,
    so aclose() cannot reach it. entry.py:35-36 promises "no child left behind".
I8. config.invalid degrades to an exit code at the Hub boundary  (axis3, axis7)
    serve.py raises inside the lifespan; Processes reports "exited with N";
    Hub returns hub.start_failed. The caller category (retryable) is lost.
I9. Hub publishes a second, category-less error vocabulary  (axis4, axis7)
    models.py:13-18 Diagnostic (code/message/details) vs errors.py ErrorInfo (+category).
    Eight hub.* codes in no table. errors.md is silent on App-defined codes.
I10. Hub state is read-modify-write with no lock and a truncating write  (axis7)
    Verified state.py:61 — write_text in place, no temp+os.replace, no asyncio.Lock,
    while ToolRuntime explicitly permits concurrency. A crash mid-write loses secrets.
I11. Two install identities for one App  (axis4 F8, axis7 I4)
    installation.py:42-48 accepts project name or folder name; :97 names the env after
    whichever was used; :141-151 keys available rows by folder name only.
I12. AGENTS.md restates ~11 facts the architecture docs own  (axis6)
    The one-role rule is breached most heavily by the document that states it.
    See open question Q1 — this needs a rule decision before any file is edited.
I13. No document owns the Hub as current truth  (axis6)
    ~700 lines, 8 Tools, states and codes; M10 promoted 4 lines out of 2045 deleted.
    M11 is specified against "Hub Core state" no document defines.
I14. Two headline AGENTS.md invariants have no executable guard  (axis1, axis2)
    No MCP in the core Tool model / no NiceGUI in the core Page model: true by reading,
    untested. The existing AST leak guards skip vibepy/__init__.py, errors.py, describe.py —
    the package root is exactly where an SDK import would poison every consumer.

### Important — single axis, verified
I15. to_error_info breaks on the framework's own public extension point  (axis1)
     REPRODUCED: to_error_info(VibepyError('x')) -> AttributeError
                 to_error_info(<subclass with own code>) -> KeyError
     VibepyError is exported public API (__init__.py:78). MCP server calls this inside
     `except Exception`, so an app defect becomes the protocol error that clause exists to prevent.
I16. Half-installed env left behind, diagnostic lost (axis4 F4) — purelib() outside the except block.
I17. list_apps raises when a registered source folder has disappeared (axis4 F5);
     hub.source_unreadable already exists for this.
I18. declared_name paired positionally with describe output (axis4 F6) — a mispairing starts a different App.
I19. HeldConfig cannot be fed back into configure_app (axis4 F7) — secrets return as the literal "set".
I20. Web channel error contract untested (axis5) — errors.md says the Web channel translates
     nothing; the channel that promises not to translate is the one never checked.
I21. Three Hub tests assert less than their names claim (axis5 1,2,8) —
     "leaves its data" is vacuous because TodoStore never writes db_path;
     "so a restart needs no one" never restarts and reads STATE_FILE internals.
I22. start_app's `secrets` parameter has no test at all (axis5 3) — the only secret-declaring
     sample (notes) has no Pages and cannot be started.
I23. CI does not run what the Makefile runs (axis5 14) — VERIFIED:
     CI lints `src tests`; Makefile lints `src tests hub samples`. hub/ and samples/ unlinted in CI.
I24. Sample Todo teaches the wrong shape (axis4 F10/F11, axis7 I8) —
     TODO_CONFIG ships a POSIX "/tmp/..." str in a distributed module (paths must be Path,
     macOS+Windows); TodoStore declares db_path and keeps a list; the Page narrows
     Tool results with `assert isinstance`, which python -O strips.
I25. ADR hygiene (axis6) — ADR-006 Accepted and half false (names AppRuntime, deleted by ADR-020,
     still cited live by lifecycle.md:64); ADR-012 Accepted with a wrong Decision signature;
     ADR-003/004/005/006 have no Context section.
I26. Three implemented decisions have no ADR (axis6) — the fastapi/uvicorn dependency +
     ASGI-lifespan Web window (which reversed the M10 spec), `python -m vibepy.serve` as a
     second framework command, and the Hub's Diagnostic/hub.* convention.
I27. architecture.md:18 contradicts packaging.md:132 — VERIFIED. The core-model diagram still
     lists "Manifest / metadata"; packaging.md and ADR-023 say no manifest format exists.
I28. authoring.md documents nothing that exists (axis6) — three capability names now collide
     with shipped Hub Tools; app_status no longer exists.

## Downgraded by cross-check
D1. Published schema vs serialized payload divergence (axis1 #3 Important, axis7 I7 Important)
    -> LATENT, not live. Reviewers proved the mechanism but not an instance.
    VERIFIED: no computed_field and no serialization_alias exists in any output model in the
    repo (the single `alias=` is on projects.py:41, an internal parsing model, not a Tool output).
    Real contract gap, zero current instances. Fix is one argument (mode="serialization") + a test.

## Adjudicated
A1. ADR-010 / missing Agent command — see I4. Axis 2's reading of the ADR is right; the
    finding belongs to the architecture docs, not to the ADR.

## Open questions for the owner — not defects
Q1. AGENTS.md invariants vs architecture-doc ownership. Nearly every invariant IS a contract
    an architecture doc owns, stated imperatively. "The same fact is not stated in two places"
    cannot be satisfied without a carve-out or a cite-don't-restate policy. This must be
    decided before I12 is acted on, or the edit will be undone by the next milestone.
Q2. Tool name validation. Nothing validates a Tool name (empty, whitespace, MCP naming rules);
    projection passes it straight through. tool-model.md does not require it, so per the
    Sources rule this is an open decision rather than a defect.
Q3. Two supported import surfaces (vibepy flat re-export vs vibepy.tool/page/app). Nothing
    imports from `vibepy` itself — the 84-line re-export is unexercised. Worth settling before M12/M18.
Q4. docs/hub-ui-mockup.html has no row in the documentation role table.

## Nothing found
- No Critical in the framework core. Channel neutrality, the single invocation path, ToolContext
  as the only invocation-state carrier, declarations-in-the-registry, and ADR-016's one name
  all hold in code, verified independently by axes 1, 2, 3 and 7.
- No test was found to be fabricated or mock-satisfied.
- The src/vibepy <-> hub distribution boundary is intact in both directions
  (only a dev-group reference, pyproject.toml:26-28).
