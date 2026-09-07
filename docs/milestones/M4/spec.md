# M4 - NiceGUI Adapter: Design

## Goal

Expose framework Pages through NiceGUI, the Web channel technology.

`docs/roadmap.md` sets the acceptance criteria:

- PageDefinition becomes a Web route
- PageHandler receives PageContext
- Page interaction invokes Tools through ToolRuntime
- dual-channel Todo proof works

## Non-goals

- **Per-Tool channel exposure.** Every Tool in a ToolRegistry is projected onto MCP.
  Deciding that a Tool is hidden from one channel is M14, whose acceptance criteria
  already reserve it: "Tool behavior remains channel-neutral while exposure and
  permission may vary by channel".
- **Running the Web server.** The adapter registers routes; `ui.run()` belongs to the
  runtime lifecycle (M6).
- **AppRuntime and app-scoped state.** M5A. The dual-channel proof shares state through
  one ToolRegistry and one ToolRuntime.
- **Session state on PageContext.** `docs/architecture/page-model.md` assigns session
  state to the Web channel, but nothing in M4 needs it.
- **A Todo sample package.** Todo stays a test fixture, as it is for M3. An importable
  sample app presumes the App Package layer (M9).

Channel selection itself is not a non-goal because it is already free: an App that never
calls `register_pages` has no Web channel, and one for which no MCP server is built has no
Agent channel. The adapters are independent entrypoints.

## Module structure

```text
src/vibepy/adapters/nicegui/
├── __init__.py   # re-exports register_pages
└── web.py        # route projection and validation
```

The package shadows the third-party `nicegui` name the way `adapters/mcp` shadows `mcp`.
Absolute imports resolve to the third-party package, and the symmetry is worth more than
a novel name.

Projection is small enough to live beside registration; no `projection.py` counterpart to
the MCP adapter's until it earns one.

## Public API

```python
def register_pages(*, registry: PageRegistry, runtime: PageRuntime) -> None: ...
```

For every declaration in `registry.definitions()`, register a NiceGUI route:

```python
ui.page(definition.route, title=definition.title)(builder)
```

The builder awaits `runtime.render(definition.name)` and does nothing else. The adapter
never constructs a PageContext: `docs/architecture/page-model.md` gives that to
PageRuntime, and `docs/architecture/runtime.md` keeps context creation out of channels.

The Page is addressed by `name`, not by route, so a route change does not reach
PageRuntime.

## Route validation

`docs/architecture/page-model.md` states that route format is "validated where routes are
registered, not in the core Page model", and that "route uniqueness is therefore validated
where routes are registered". The adapter is that place.

Two new exceptions in `vibepy/errors.py`, both deriving from `VibepyError`:

| Exception | Raised when |
| --- | --- |
| `PageRouteInvalidError` | a route does not begin with `/` |
| `PageRouteConflictError` | two Pages declare the same route |

Every declaration is validated before any route is registered with NiceGUI, so a rejected
registry leaves no half-registered app behind.

Route format validation stops at the leading slash. NiceGUI passes routes to FastAPI,
which owns path-parameter syntax; restating those rules here would create a second
authority that drifts.

## Data flow

```text
Browser -> NiceGUI route -> adapter builder -> PageRuntime.render(name)
        -> PageContext(tools) -> PageHandler builds UI with ui.*

Click   -> PageHandler callback -> ctx.tools.call("create_todo", {...})
        -> ToolRuntime -> Tool -> domain
```

## Error handling

Errors are not translated. `docs/architecture/page-model.md` states that Tool errors reach
the caller of the Page unchanged, and ADR-003 keeps adapters thin. A handler exception
propagates into NiceGUI, which renders its own error page.

The MCP adapter wraps failures in an `is_error` result because the MCP protocol demands a
protocol-level answer to every call. The Web channel makes no such demand, so the same
treatment here would be invention rather than symmetry.

## Testing

### `tests/test_nicegui_adapter.py`

1. a PageDefinition becomes a Web route
2. an invalid route format raises `PageRouteInvalidError`
3. a duplicate route raises `PageRouteConflictError` and registers nothing
4. a PageHandler receives a PageContext carrying a ToolInvoker
5. interaction: `user.open('/todos')`, type, click, `should_see` the new todo

Test 5 uses `nicegui.testing`'s `User` fixture, the official browser-free test surface. It
runs in the same async context as the page builder, so a click reaching a Tool is proven
rather than assumed.

### `tests/test_dual_channel.py`

`docs/architecture/runtime.md` calls this "a constitutional integration test" that "should
remain throughout the project", so it gets its own file rather than living inside an
adapter's tests.

1. an Agent-side MCP call creates todo A
2. a Web-side interaction creates todo B
3. the Web side sees A and B
4. the Agent side sees A and B

Both channels are built over one ToolRegistry and one ToolRuntime. This proves the
channels converge on one backend path; it does not assert that every Tool belongs on every
channel.

### Leak check

Extend M3's AST assertion: `vibepy/page` and `vibepy/tool` import no `nicegui` module,
mirroring the existing check against `mcp`.

## Dependencies

- `nicegui` in `[project].dependencies`. The Web channel is a first-class channel, as MCP
  is.
- the `testing` extra in the dev group, with the pytest plugin enabled in `conftest.py`.

The exact `nicegui.testing` wiring is read from the installed package and the official
documentation during implementation, not recalled.

## Documentation

- `docs/architecture/adapters.md`: describe what the NiceGUI adapter registers, that route
  validation lives here, and that it starts no server.
- ADR-012: the NiceGUI adapter registers routes and does not run the server. This is a
  decision, not a restatement of ADR-010: MCP's process is owned externally and forces the
  split, whereas the Web server does live in the app process, so deferring it to the
  runtime lifecycle is a choice between real alternatives.
