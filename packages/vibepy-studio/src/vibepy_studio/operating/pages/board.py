"""The board: every App the operating role knows of, and what can be done to each.

A Page over Tools. It reads `list_apps` into one view value and binds every
element that shows something to it; a timer reads the listing again and assigns
what it read, so a child that died or an action taken elsewhere reaches the
screen without anything being drawn a second time. NiceGUI has no virtual DOM:
an element deleted and built again is a Vue component destroyed and built again,
losing focus, scroll and animation, so what changes value is bound and only what
changes *shape* -- the set of rows, the set of a row's buttons, the registry's
controls, an open configuration panel -- is behind a `@ui.refreshable`.

The rules of what to draw are `presentation.py`'s, and what it looks like is
`board.css`.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html import escape
from pathlib import Path

from nicegui import binding, ui

from vibepy_core import ConfigFieldType, Page, PageContext, PageDefinition
from vibepy_core.errors import ErrorCategory, ErrorInfo
from vibepy_studio.operating.models import (
    AppListing,
    ConfigDescription,
    Installation,
    SourceListing,
)
from vibepy_studio.operating.pages.presentation import (
    Action,
    BoardView,
    RowView,
    board_view,
    save_request,
)

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 3.0

STYLESHEET = Path(__file__).with_name("board.css").read_text(encoding="utf-8")
"""The board's stylesheet, scoped to the board's root element."""

EYEBROW = "App control board"
TITLE = "Your apps"
SUBTITLE = "Install, configure, and run your team's apps from one place."
CONFIG_NOTE = (
    "Declared by the App itself. A secret is write-only: it is stored and never shown back."
)
TONE_CLASSES = {
    "done": "is-done",
    "live": "is-live",
    "required": "is-required",
    "update": "is-update",
    "plain": "",
}
"""What each rail tone looks like. `presentation.py` decides the tone; this only paints it."""

SUMMARY_LABELS = ("Available", "Installed", "Running")
COLUMN_LABELS = ("App", "Lifecycle", "Action")


@binding.bindable_dataclass
class Shown:
    """The board the screen is currently showing.

    Assigning a board is how a new listing reaches the screen: a bindable field
    propagates to everything bound to it, and only when the value differs, so a
    listing that says what the last one said moves nothing.
    """

    board: BoardView


@binding.bindable_dataclass
class RowShown:
    """One row of the board the screen is currently showing.

    A row's elements bind to this rather than to the whole board, so what a row
    shows is a function of its own view and of nothing else.
    """

    view: RowView


class Shape:
    """Rebuild one refreshable when the shape it drew changes.

    A binding target rather than something the clock calls: the clock assigns a
    board and nothing else, and rebuilding the part whose *structure* changed is
    one consequence of that assignment like every other. Assigning the shape it
    already has rebuilds nothing.
    """

    def __init__(self, refresh: Callable[[], object], drawn: object) -> None:
        """Hold what rebuilds the part, and the shape it was drawn with."""
        self._refresh = refresh
        self._drawn = drawn

    @property
    def shape(self) -> object:
        """The shape the part now on the screen was drawn with."""
        return self._drawn

    @shape.setter
    def shape(self, value: object) -> None:
        if value == self._drawn:
            return
        self._drawn = value
        self._refresh()


class Tone:
    """Paint one rail step in the tone its mark says.

    A class list is the one thing a NiceGUI element does not publish as a
    bindable property, so this holds the setter and is bound like any value.
    """

    def __init__(self, stage: ui.element, tone: str) -> None:
        """Hold the step to paint, and the tone it was painted in."""
        self._stage = stage
        self._tone = tone

    @property
    def tone(self) -> str:
        """The tone the step is painted in."""
        return self._tone

    @tone.setter
    def tone(self, value: str) -> None:
        if value == self._tone:
            return
        self._tone = value
        self._stage.classes(replace=f"operating-stage {TONE_CLASSES[value]}".strip())


def _text(tag: str, value: str, classes: str = "") -> ui.html:
    """Write one piece of text into the tag the stylesheet dresses it as."""
    element = ui.html(escape(value), tag=tag)
    return element.classes(classes) if classes else element


@dataclass(frozen=True)
class _Bound[ShownT]:
    """One thing the screen reads from: the object that holds it, and under which name.

    Every element that shows a value is bound through one of these, so what the
    element shows stays a function of the state and never of a redraw.
    """

    source: object
    name: str

    def text(self, element: ui.html, read: Callable[[ShownT], str]) -> None:
        """Keep `element`'s text a function of what is shown, escaped as it is written."""
        element.bind_content_from(
            self.source, self.name, backward=lambda shown: escape(read(shown))
        )

    def visibility(self, element: ui.element, read: Callable[[ShownT], bool]) -> None:
        """Keep whether `element` is on the screen a function of what is shown."""
        element.bind_visibility_from(self.source, self.name, backward=read)

    def into(self, target: object, name: str, read: Callable[[ShownT], object]) -> None:
        """Keep `target`'s `name` a function of what is shown, for what is not an element."""
        binding.bind_from(target, name, self.source, self.name, read)


def _button(
    label: str,
    style: str,
    /,
    *,
    on_click: Callable[[], object] | None = None,
    marker: str | None = None,
) -> ui.html:
    """Draw one button; no handler means the button is disabled.

    A plain `<button>` rather than a `ui.button`: the stylesheet dresses the
    element itself, and a Quasar button would arrive already dressed.
    """
    button = _text("button", label, style).props("type=button")
    if marker is not None:
        button.mark(marker)
    if on_click is None:
        button.props("disabled")
    else:
        button.on("click", on_click)
    return button


async def board(ctx: PageContext) -> None:
    """Draw the board and keep it current."""
    ui.add_css(STYLESHEET)
    open_config: dict[str, ConfigDescription] = {}
    """The one row whose configuration panel is open, keyed by app name."""
    missing: dict[str, list[str]] = {}
    panels: dict[str, Callable[[], object]] = {}
    """What reopens or closes one row's configuration panel, keyed by app name."""
    bound: list[object] = []
    """The binding targets of the rows now on the screen, dropped when they are."""
    dialogs = ui.column()
    """Where a confirmation lives: outside every part a refresh rebuilds."""

    async def listed() -> BoardView:
        """Read the listing and describe the board it makes."""
        return board_view(AppListing.model_validate(await ctx.tools.invoke("list_apps", {})))

    shown = Shown(board=await listed())
    on_board = _Bound[BoardView](source=shown, name="board")
    """What the parts that show the whole board read from."""

    async def reread() -> None:
        """Put what `list_apps` says now on the screen."""
        shown.board = await listed()

    async def call(name: str, payload: dict[str, object]) -> object:
        """Invoke one Tool and tell the user what it said; return the answer."""
        answer = await ctx.tools.invoke(name, payload)
        diagnostic = getattr(answer, "diagnostic", None)
        if isinstance(diagnostic, ErrorInfo):
            ui.notify(f"{diagnostic.code}: {diagnostic.message}", type="warning")
        return answer

    async def confirm(question: str, label: str) -> bool:
        """Ask one yes-or-no question in the board's own clothes."""
        with dialogs, ui.dialog() as dialog, ui.element("div").classes("operating-dialog"):
            _text("p", question).style("margin: 0")
            with ui.element("div").classes("operating-dialog-actions"):
                _button("Cancel", "operating-quiet", on_click=lambda: dialog.submit(False))
                # The dialog repeats the word on the button that raised it, so
                # a test reaches the dialog's own answer by a marker.
                _button(
                    label,
                    "operating-primary",
                    marker="dialog-confirm",
                    on_click=lambda: dialog.submit(True),
                )
        answered = bool(await dialog)
        dialogs.clear()
        return answered

    def draw_heading() -> None:
        """Say what the board is, and how many Apps are in each state."""
        with ui.element("div").classes("operating-heading-row"):
            with ui.element("div"):
                _text("p", EYEBROW, "operating-eyebrow")
                _text("h1", TITLE)
                _text("p", SUBTITLE, "operating-subtitle")
            with ui.element("div").classes("operating-summary"):
                for index, label in enumerate(SUMMARY_LABELS):
                    with ui.element("div").classes("operating-summary-item"):
                        count = _text(
                            "span", str(shown.board.counts[index]), "operating-summary-value"
                        )
                        on_board.text(count, lambda view, at=index: str(view.counts[at]))
                        _text("span", label, "operating-summary-label")

    async def register(path: str | None) -> None:
        """Register one folder of wheels as the package source.

        An empty box is answered here rather than sent: what the Tool would
        raise is `tool.input_invalid`, and an empty input is a presentation
        check, not a business rule.
        """
        if not (path or "").strip():
            ui.notify("Enter a folder path")
            return
        answer = await call("register_package_source", {"path": path})
        if isinstance(answer, SourceListing) and answer.diagnostic is None:
            ui.notify(f"{len(answer.candidates)} apps available from {answer.source}.")
        await reread()

    async def unregister() -> None:
        """Forget the package source, once the user has confirmed it."""
        if await confirm(
            "Unregister this package folder? The folder, installed apps, "
            "and app data will not be deleted.",
            "Unregister",
        ):
            await call("remove_package_source", {})
        await reread()

    def draw_diagnostic[ShownT](
        bound: _Bound[ShownT], read: Callable[[ShownT], ErrorInfo | None]
    ) -> None:
        """Draw the line a diagnostic is written on, shown only while there is one."""
        panel = ui.element("div").classes("operating-diagnostic")
        bound.visibility(panel, lambda shown: read(shown) is not None)
        with panel:
            code = _text("span", "", "operating-code")
            bound.text(code, lambda shown: _diagnostic(read(shown)).code)
            message = _text("span", "")
            bound.text(message, lambda shown: _diagnostic(read(shown)).message)

    def draw_registry() -> None:
        """Draw the source card: a path and Unregister, or a box and Register folder.

        Which of the two the card offers is its shape, so that much is
        refreshable; the folder it names is a value, and is bound.
        """
        with ui.element("section").classes("operating-registry"):
            with ui.element("div"):
                _text("span", "Local packages", "operating-registry-label")
                value = _text("span", shown.board.source, "operating-registry-value")
                on_board.text(value, lambda view: view.source)
            with ui.element("div").classes("operating-registry-actions"):

                @ui.refreshable
                def controls() -> None:
                    if shown.board.registered:
                        _button("Unregister", "operating-secondary", on_click=unregister)
                        return
                    entry = ui.input(placeholder="package folder")
                    entry.classes("operating-registry-entry").props("dense borderless")
                    # The empty state names a package folder too, so the box is
                    # reached by a marker rather than by its placeholder.
                    entry.mark("package-folder")
                    _button(
                        "Register folder",
                        "operating-primary",
                        on_click=lambda: register(entry.value),
                    )

                controls()
                shaped = Shape(controls.refresh, shown.board.registered)
                on_board.into(shaped, "shape", lambda view: view.registered)
        draw_diagnostic(on_board, lambda view: view.diagnostic)

    async def act(action: Action, view: RowView) -> None:
        """Run one row's action, say what happened, and read the listing again."""
        if action.tool == "describe_config":
            await toggle_config(view)
            return
        if action.tool == "remove_app" and not await confirm(
            f"Uninstall {view.title}? App data will be retained.", "Uninstall"
        ):
            return
        payload: dict[str, object] = {"app_name": view.app_name}
        if action.tool == "start_app":
            payload["secrets"] = {}
        answer = await call(action.tool, payload)
        if getattr(answer, "diagnostic", None) is None:
            ui.notify(f"{view.title} {_said(action.tool, answer)}")
        close_config(view.app_name)
        await reread()

    def close_config(app_name: str, /) -> None:
        """Close one row's configuration panel, wherever it was closed from."""
        open_config.pop(app_name, None)
        missing.pop(app_name, None)
        if app_name in panels:
            panels[app_name]()

    async def toggle_config(view: RowView) -> None:
        """Open this row's configuration panel, or close the open one."""
        if open_config.pop(view.app_name, None) is None:
            described = await call("describe_config", {"app_name": view.app_name})
            if isinstance(described, ConfigDescription):
                for other in list(open_config):
                    close_config(other)
                open_config[view.app_name] = described
        missing.pop(view.app_name, None)
        panels[view.app_name]()

    async def save(
        view: RowView,
        described: ConfigDescription,
        inputs: dict[str, ui.input],
        rows: dict[str, ui.element],
        lacking: ui.element,
        message: ui.html,
    ) -> None:
        """Send what the form holds to `configure_app`, or name what it lacks.

        Naming what it lacks writes into the panel's own line rather than
        rebuilding the panel: a rebuild reseeds every input from what the
        operating role holds, which never includes a secret and never includes
        what was just typed.
        """
        entered = {name: str(entry.value) for name, entry in inputs.items()}
        request = save_request(described.fields, entered, described.secrets_set)
        if isinstance(request, list):
            missing[view.app_name] = request
            message.content = escape(_lacking_line(request))
            lacking.set_visibility(True)
            for name, row in rows.items():
                row.classes(add="is-invalid" if name in request else "", remove="is-invalid")
            return
        answer = await call("configure_app", {"app_name": view.app_name, "values": request})
        if getattr(answer, "diagnostic", None) is None:
            ui.notify(f"{view.title} configured.")
        close_config(view.app_name)
        await reread()

    def draw_config(view: RowView) -> None:
        """Draw the open row's configuration form."""
        described = open_config[view.app_name]
        lacking = missing.get(view.app_name, [])
        with ui.element("div").classes("operating-config"):
            _text("p", f"What {view.title} requires", "operating-config-head")
            if not described.fields:
                # No fields means nothing a Save could send, so only Cancel is offered.
                _text("p", "Nothing to configure", "operating-config-note")
                with ui.element("div").classes("operating-config-actions"):
                    _button("Cancel", "operating-quiet", on_click=lambda: toggle_config(view))
                return
            _text("p", CONFIG_NOTE, "operating-config-note")
            inputs: dict[str, ui.input] = {}
            rows: dict[str, ui.element] = {}
            for field in described.fields:
                secret = field.type is ConfigFieldType.SECRET
                held = secret and field.name in described.secrets_set
                row = ui.element("div").classes("operating-field")
                if field.name in lacking:
                    row.classes("is-invalid")
                rows[field.name] = row
                with row:
                    with ui.element("label"):
                        _text("span", field.name, "operating-field-name")
                        need = "required" if field.required else "optional"
                        _text("span", f"{field.type.value} · {need}", "operating-field-type")
                    entry = ui.input(
                        password=secret,
                        placeholder="•••••••• (set)" if held else "",
                        value="" if secret else str(described.values.get(field.name, "")),
                    ).props("dense borderless")
                    # Several rows can declare the same field name, so a test
                    # reaches one row's box by a marker rather than by its label:
                    # the name beside it is a `<span>`, which cannot be typed into.
                    entry.mark(f"field-{view.app_name}-{field.name}")
                    inputs[field.name] = entry
            error = ui.element("div").classes("operating-config-error")
            with error:
                _text("span", "config.invalid", "operating-code")
                message = _text("span", _lacking_line(lacking))
            error.set_visibility(bool(lacking))
            with ui.element("div").classes("operating-config-actions"):
                _button("Cancel", "operating-quiet", on_click=lambda: toggle_config(view))
                _button(
                    "Save",
                    "operating-primary",
                    on_click=lambda: save(view, described, inputs, rows, error, message),
                )

    def _on_click(action: Action, row: RowShown) -> Callable[[], Awaitable[None]]:
        """Bind one button to one row's action, so a loop's variable cannot leak.

        The row is reached through what it currently shows, so a button acts on
        the App as the last listing left it.
        """
        return lambda: act(action, row.view)

    def draw_actions(row: RowShown) -> None:
        """Draw the buttons this row's state offers."""
        for action in row.view.actions:
            style = "operating-primary" if action.primary else "operating-secondary"
            if action.tool == "remove_app":
                style = "operating-danger"
            _button(
                action.label,
                style,
                # Several rows carry the same word, so a test reaches one
                # row's button by a marker rather than by its label.
                marker=f"{action.label.lower()}-{row.view.app_name}",
                on_click=_on_click(action, row) if action.enabled else None,
            )

    def draw_rail(row: RowShown, on_row: _Bound[RowView]) -> None:
        """Draw the row's rail: four steps, each bound to the mark it shows."""
        with ui.element("div").classes("operating-rail"):
            for index, mark in enumerate(row.view.marks):
                stage = ui.element("div").classes("operating-stage")
                stage.classes(TONE_CLASSES[mark.tone])
                painted = Tone(stage, mark.tone)
                on_row.into(painted, "tone", lambda view, at=index: view.marks[at].tone)
                bound.append(painted)
                with stage:
                    symbol = _text("span", mark.symbol, "operating-stage-node")
                    on_row.text(symbol, lambda view, at=index: view.marks[at].symbol)
                    label = _text("span", mark.label)
                    on_row.text(label, lambda view, at=index: view.marks[at].label)

    def draw_app(view: RowView) -> None:
        """Draw one row: its name, its rail, its buttons, its diagnostic, its form."""
        row = RowShown(view=view)
        bound.append(row)
        # A row that a listing no longer carries keeps what it last showed: the
        # set of rows is a shape, and the rebuild it asks for is the one that
        # takes this row off the screen.
        on_row = _Bound[RowView](source=row, name="view")
        on_board.into(
            row, "view", lambda board, held=row: board.row(held.view.app_name) or held.view
        )
        container = ui.element("article").classes("operating-app-row")
        # A row is reached whole -- by a test asking whether the clock replaced it.
        container.mark(f"row-{view.app_name}")
        with container:
            with ui.element("div"):
                name = _text("h2", view.title, "operating-app-name")
                on_row.text(name, lambda view: view.title)
                with ui.element("div").classes("operating-app-meta"):
                    version = _text("span", f"v{view.version}" if view.version else "")
                    on_row.text(version, lambda view: f"v{view.version}")
                    on_row.visibility(version, lambda view: view.version is not None)
            # The buttons are built before the rail: a rail label and a button
            # can carry the same word ("Configured", "Configure"), and what a
            # reader -- or a test -- reaches for by that word is the button. The
            # stylesheet puts them back in the order the board shows them.
            with ui.element("div").classes("operating-actions"):

                @ui.refreshable
                def buttons() -> None:
                    draw_actions(row)

                buttons()
                shaped = Shape(buttons.refresh, view.actions)
                on_row.into(shaped, "shape", lambda view: view.actions)
                bound.append(shaped)
            draw_rail(row, on_row)
            draw_diagnostic(on_row, lambda view: view.diagnostic)

            @ui.refreshable
            def panel() -> None:
                if row.view.app_name in open_config:
                    draw_config(row.view)

            panel()
            panels[view.app_name] = panel.refresh

    def draw_empty() -> None:
        """Say why the board is empty: no folder, or a folder with nothing in it."""
        registered = shown.board.registered
        with ui.element("div").classes("operating-empty"), ui.element("div"):
            _text("h2", "No apps found" if registered else "No package folder selected")
            _text(
                "p",
                "This package folder does not contain any compatible VibePy Apps."
                if registered
                else "Choose a package folder above to see available apps.",
            )

    @ui.refreshable
    def rows() -> None:
        """Draw the Apps the board holds; rebuilt only when that set changes."""
        binding.remove(bound)
        bound.clear()
        panels.clear()
        if not shown.board.rows:
            draw_empty()
            return
        with ui.element("div").classes("operating-board-head"):
            for label in COLUMN_LABELS:
                _text("span", label)
        for view in shown.board.rows:
            draw_app(view)

    with (
        ui.element("div").classes("vibepy-operating"),
        ui.element("section").classes("operating-shell"),
    ):
        with (
            ui.element("header").classes("operating-topbar"),
            ui.element("div").classes("operating-brand"),
        ):
            _text("span", "V\u203a", "operating-brand-mark")
            _text("span", "VibePy Studio")
        with ui.element("main").classes("operating-main"):
            draw_heading()
            draw_registry()
            with ui.element("section").classes("operating-board"):
                rows()
                listing_shape = Shape(rows.refresh, shown.board.names)
                on_board.into(listing_shape, "shape", lambda view: view.names)
    ui.timer(REFRESH_SECONDS, reread)


_NO_DIAGNOSTIC = ErrorInfo(code="", message="", category=ErrorCategory.EXECUTION)
"""What a diagnostic's bound line reads while there is no diagnostic to read."""


def _diagnostic(info: ErrorInfo | None, /) -> ErrorInfo:
    """Give a diagnostic to write, whether or not there is one.

    A hidden line is still bound, and what a binding reads is read before the
    visibility that hides it is.
    """
    return _NO_DIAGNOSTIC if info is None else info


def _lacking_line(lacking: list[str]) -> str:
    """Name the required fields a save left empty, or say nothing."""
    if not lacking:
        return ""
    noun = "field" if len(lacking) == 1 else "fields"
    return f"Missing required {noun}: {', '.join(lacking)}"


def _said(tool: str, answer: object) -> str:
    """Say what one Tool's success was, in the words the spec gives it."""
    if tool == "update_app":
        # The version is the one just installed, so it is read from the answer
        # through the Tool's own output model rather than from the old row.
        return f"updated to v{Installation.model_validate(answer).app.distribution_version}."
    return {
        "install_app": "installed.",
        "start_app": "is running.",
        "stop_app": "stopped.",
        "remove_app": "uninstalled.",
    }[tool]


BOARD = Page(
    definition=PageDefinition(
        name="board",
        route="/",
        title="Studio",
        tools=frozenset(
            {
                "list_apps",
                "install_app",
                "update_app",
                "remove_app",
                "start_app",
                "stop_app",
                "describe_config",
                "configure_app",
                "register_package_source",
                "remove_package_source",
            }
        ),
    ),
    handler=board,
)
