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

Everything the board does to the operating role's state goes through a Tool, and
a test scripts those by handing the Page runtime its own invoker. One thing does
not: choosing the package folder opens a dialog on the machine Studio runs on,
which is a host operation and not a Tool (ADR-042), so it comes from
`operating/host.py` rather than through `ctx.tools`. `choose_folder`, bound as
this module's own name, is the one seam a test replaces for it.
"""

import logging
from collections.abc import Awaitable, Callable, Sequence
from html import escape
from pathlib import Path
from typing import Protocol

from nicegui import binding, ui

from vibepy_core import ConfigFieldType, Page, PageContext, PageDefinition
from vibepy_core.errors import ErrorInfo
from vibepy_studio.operating.host import FolderDialogFailed, choose_folder
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

REGISTER_LABEL = "Register folder"
CHOOSING_LABEL = "Choosing…"
CHOOSE_TITLE = "Choose the package folder"

SUMMARY_LABELS = ("Available", "Installed", "Running")
COLUMN_LABELS = ("App", "Lifecycle", "Action")


class Binder[ShownT](Protocol):
    """What a holder of shown state offers the elements that show it.

    Each holder binds its own one field, so what a transform is handed is that
    field's type and pyright checks every one of them.
    """

    def text(self, element: ui.html, read: Callable[[ShownT], str], /) -> None:
        """Keep `element`'s text a function of what is shown."""
        ...

    def visibility(self, element: ui.element, read: Callable[[ShownT], bool], /) -> None:
        """Keep whether `element` is on the screen a function of what is shown."""
        ...

    def into(self, target: object, name: str, read: Callable[[ShownT], object], /) -> None:
        """Keep `target`'s `name` a function of what is shown, for what is not an element."""
        ...


@binding.bindable_dataclass
class Shown:
    """The board the screen is currently showing.

    Assigning a board is how a new listing reaches the screen: a bindable field
    propagates to everything bound to it, and only when the value differs, so a
    listing that says what the last one said moves nothing.
    """

    board: BoardView

    def text(self, element: ui.html, read: Callable[[BoardView], str], /) -> None:
        """Keep `element`'s text a function of the board, escaped as it is written."""
        element.bind_content_from(self, "board", backward=lambda view: escape(read(view)))

    def visibility(self, element: ui.element, read: Callable[[BoardView], bool], /) -> None:
        """Keep whether `element` is on the screen a function of the board."""
        element.bind_visibility_from(self, "board", backward=read)

    def into(self, target: object, name: str, read: Callable[[BoardView], object], /) -> None:
        """Keep `target`'s `name` a function of the board, for what is not an element."""
        binding.bind_from(target, name, self, "board", read)


@binding.bindable_dataclass
class RowShown:
    """One row of the board the screen is currently showing.

    A row's elements bind to this rather than to the whole board, so what a row
    shows is a function of its own view and of nothing else.
    """

    view: RowView

    def text(self, element: ui.html, read: Callable[[RowView], str], /) -> None:
        """Keep `element`'s text a function of the row, escaped as it is written."""
        element.bind_content_from(self, "view", backward=lambda view: escape(read(view)))

    def visibility(self, element: ui.element, read: Callable[[RowView], bool], /) -> None:
        """Keep whether `element` is on the screen a function of the row."""
        element.bind_visibility_from(self, "view", backward=read)

    def into(self, target: object, name: str, read: Callable[[RowView], object], /) -> None:
        """Keep `target`'s `name` a function of the row, for what is not an element."""
        binding.bind_from(target, name, self, "view", read)


@binding.bindable_dataclass
class PanelShown:
    """One row's open configuration panel, and the draft being typed into it.

    The draft is state rather than what the inputs happen to hold, so a row the
    board rebuilds draws the panel back with the typing still in it, and a save
    reads what was typed rather than elements that may no longer exist.
    """

    described: ConfigDescription
    draft: dict[str, str]
    lacking: tuple[str, ...] = ()

    def text(self, element: ui.html, read: Callable[[tuple[str, ...]], str], /) -> None:
        """Keep `element`'s text a function of what the panel still lacks."""
        element.bind_content_from(self, "lacking", backward=lambda lacking: escape(read(lacking)))

    def visibility(self, element: ui.element, read: Callable[[tuple[str, ...]], bool], /) -> None:
        """Keep whether `element` is on the screen a function of what the panel still lacks."""
        element.bind_visibility_from(self, "lacking", backward=read)

    def into(self, target: object, name: str, read: Callable[[tuple[str, ...]], object], /) -> None:
        """Keep `target`'s `name` a function of what the panel still lacks."""
        binding.bind_from(target, name, self, "lacking", read)


@binding.bindable_dataclass
class RegistryShown:
    """What the registry card shows that no listing says.

    Whether the operator is being asked for a folder is this tab's own fact: it
    is not the operating role's state, no listing carries it, and a second
    window must not show this one's dialog. It is state all the same, so the
    control that waits on it is bound to it rather than reached into.
    """

    choosing: bool = False

    def into(self, target: object, name: str, read: Callable[[bool], object], /) -> None:
        """Keep `target`'s `name` a function of whether a folder is being chosen."""
        binding.bind_from(target, name, self, "choosing", read)


class Shape:
    """Rebuild one refreshable when the shape it drew changes.

    A binding target rather than something the clock calls: the clock assigns a
    board and nothing else, and rebuilding the part whose *structure* changed is
    one consequence of that assignment like every other. A binding assigns only
    what differs from what the target holds, so this is only ever handed a shape
    the part on the screen was not drawn with.
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
        self._tone = value
        self._stage.classes(replace=f"operating-stage {TONE_CLASSES[value]}".strip())


class Invalid:
    """Mark one configuration field while the panel says a value is missing.

    Like `Tone`: a class list is what NiceGUI publishes no bindable property
    for, so this holds the setter and is bound like any other value.
    """

    def __init__(self, field: ui.element, invalid: bool) -> None:
        """Hold the field to mark, and whether it is marked."""
        self._field = field
        self._invalid = invalid

    @property
    def invalid(self) -> bool:
        """Whether the field is marked as missing a value."""
        return self._invalid

    @invalid.setter
    def invalid(self, value: bool) -> None:
        self._invalid = value
        self._field.classes(add="is-invalid" if value else "", remove="" if value else "is-invalid")


class Busy:
    """Put one button in its working state while what it started is in flight.

    Like `Tone` and `Invalid`: what a plain `<button>` says and whether it is
    disabled are not bindable properties, so this holds the setter and is bound
    like any other value.
    """

    def __init__(self, button: ui.html, label: str, working: str) -> None:
        """Hold the button, what it says at rest, and what it says while working."""
        self._button = button
        self._label = label
        self._working = working
        self._busy = False

    @property
    def busy(self) -> bool:
        """Whether the button is in its working state."""
        return self._busy

    @busy.setter
    def busy(self, value: bool) -> None:
        self._busy = value
        self._button.set_content(escape(self._working if value else self._label))
        if value:
            self._button.props(add="disabled")
        else:
            self._button.props(remove="disabled")


def _text(tag: str, value: str, classes: str = "") -> ui.html:
    """Write one piece of text into the tag the stylesheet dresses it as."""
    element = ui.html(escape(value), tag=tag)
    return element.classes(classes) if classes else element


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
    open_panel: dict[str, PanelShown] = {}
    """The one row whose configuration panel is open, keyed by app name.

    What is typed into the panel lives here rather than in the inputs, so a row
    the board rebuilds draws the panel back with the typing still in it.
    """
    panels: dict[str, Callable[[], object]] = {}
    """What reopens or closes one row's configuration panel, keyed by app name."""
    panel_bound: dict[str, list[object]] = {}
    """The binding targets one row's open panel made, dropped when it is drawn again.

    A panel is drawn again whenever it opens, closes, or the row around it is
    rebuilt; each of those leaves the last draw's targets bound to a panel
    nothing shows any more, and a binding holds what it binds. So the panel
    clears its own, keyed by the row it belongs to, as `rows` clears the set's."""
    bound: list[object] = []
    """The binding targets of the rows now on the screen, dropped when they are."""
    registry_bound: list[object] = []
    """The binding targets of the registry's controls, dropped when they are redrawn."""
    registry = RegistryShown()
    """What the registry card shows that no listing says."""
    dialogs = ui.column()
    """Where a confirmation lives: outside every part a refresh rebuilds."""

    async def listed() -> BoardView:
        """Read the listing and describe the board it makes."""
        return board_view(AppListing.model_validate(await ctx.tools.invoke("list_apps", {})))

    shown = Shown(board=await listed())

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
                        count = _text("span", "", "operating-summary-value")
                        shown.text(count, lambda view, at=index: str(view.counts[at]))
                        _text("span", label, "operating-summary-label")

    async def register() -> None:
        """Ask the operator for a folder with this machine's own dialog, and register it.

        What the dialog answers is a plain argument to the Tool, which is the
        same Tool an agent calls with a path it already knows (ADR-042).
        Cancelling is an answer: nothing is registered and nothing moves.

        A dialog that could not be shown is this machine failing, not a Tool. It
        carries no `ErrorInfo` -- there is no code for it, and inventing one
        would claim a framework contract that does not exist -- so it is said on
        the board's transient line, where `call` already says what a Tool
        answered badly, rather than on the diagnostic line that shows what the
        listing carries.
        """
        registry.choosing = True
        try:
            chosen = await choose_folder(title=CHOOSE_TITLE)
        except FolderDialogFailed as error:
            logger.warning("The folder dialog could not be shown.", exc_info=error)
            ui.notify(f"Could not open the folder dialog: {error}", type="warning")
            return
        finally:
            registry.choosing = False
        if chosen is None:
            return
        answer = await call("register_package_source", {"path": str(chosen)})
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
        binder: Binder[ShownT], read: Callable[[ShownT], ErrorInfo | None]
    ) -> None:
        """Draw the line a diagnostic is written on, shown only while there is one."""
        panel = ui.element("div").classes("operating-diagnostic")
        binder.visibility(panel, lambda state: read(state) is not None)
        with panel:
            code = _text("span", "", "operating-code")
            binder.text(code, lambda state: _said_by(read(state), lambda info: info.code))
            message = _text("span", "")
            binder.text(message, lambda state: _said_by(read(state), lambda info: info.message))

    def draw_registry() -> None:
        """Draw the source card: a path and Unregister, or Register folder.

        Which of the two the card offers is its shape, so that much is
        refreshable; the folder it names is a value, and is bound, as is whether
        the button is waiting on a dialog.
        """
        with ui.element("section").classes("operating-registry"):
            with ui.element("div"):
                _text("span", "Package folder", "operating-registry-label")
                value = _text("span", "", "operating-registry-value")
                shown.text(value, lambda view: view.source)
            with ui.element("div").classes("operating-registry-actions"):

                @ui.refreshable
                def controls() -> None:
                    binding.remove(registry_bound)
                    registry_bound.clear()
                    if shown.board.registered:
                        _button("Unregister", "operating-secondary", on_click=unregister)
                        return
                    # The empty state names a package folder too, so the button
                    # is reached by a marker rather than by what it says.
                    button = _button(
                        REGISTER_LABEL,
                        "operating-primary",
                        marker="register-folder",
                        on_click=register,
                    )
                    working = Busy(button, REGISTER_LABEL, CHOOSING_LABEL)
                    registry.into(working, "busy", lambda choosing: choosing)
                    registry_bound.append(working)

                controls()
                shaped = Shape(controls.refresh, shown.board.registered)
                shown.into(shaped, "shape", lambda view: view.registered)
        draw_diagnostic(shown, lambda view: view.diagnostic)

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

    def redraw_panel(app_name: str, /) -> None:
        """Draw one row's configuration panel again, or forget it if the row has left.

        Every handler that changes a panel ends here, and a handler runs across
        an await: the clock can rebuild the rows while one is in flight, and a
        row the listing no longer carries has no panel to draw and no draft to
        keep.
        """
        redraw = panels.get(app_name)
        if redraw is None:
            open_panel.pop(app_name, None)
            return
        redraw()

    def close_config(app_name: str, /) -> None:
        """Close one row's configuration panel, wherever it was closed from."""
        open_panel.pop(app_name, None)
        redraw_panel(app_name)

    async def toggle_config(view: RowView) -> None:
        """Open this row's configuration panel, or close the open one."""
        if open_panel.pop(view.app_name, None) is None:
            described = await call("describe_config", {"app_name": view.app_name})
            if isinstance(described, ConfigDescription):
                for other in list(open_panel):
                    close_config(other)
                open_panel[view.app_name] = PanelShown(described=described, draft=_draft(described))
        redraw_panel(view.app_name)

    async def save(view: RowView, panel: PanelShown) -> None:
        """Send what the draft holds to `configure_app`, or name what it lacks.

        Both the draft and what it lacks are state, so a save reads what was
        typed rather than elements a rebuild may have taken, and naming what is
        missing reaches the panel's own line through the binding on it.
        """
        request = save_request(panel.described.fields, panel.draft, panel.described.secrets_set)
        if isinstance(request, list):
            panel.lacking = tuple(request)
            return
        answer = await call("configure_app", {"app_name": view.app_name, "values": request})
        if getattr(answer, "diagnostic", None) is None:
            ui.notify(f"{view.title} configured.")
        close_config(view.app_name)
        await reread()

    def draw_config(view: RowView, panel: PanelShown) -> None:
        """Draw the open row's configuration form over the draft it holds."""
        described = panel.described
        with ui.element("div").classes("operating-config"):
            _text("p", f"What {view.title} requires", "operating-config-head")
            if not described.fields:
                # No fields means nothing a Save could send, so only Cancel is offered.
                _text("p", "Nothing to configure", "operating-config-note")
                with ui.element("div").classes("operating-config-actions"):
                    _button("Cancel", "operating-quiet", on_click=lambda: toggle_config(view))
                return
            _text("p", CONFIG_NOTE, "operating-config-note")
            for field in described.fields:
                secret = field.type is ConfigFieldType.SECRET
                held = secret and field.name in described.secrets_set
                row = ui.element("div").classes("operating-field")
                marked = Invalid(row, False)
                panel.into(marked, "invalid", lambda lacking, of=field.name: of in lacking)
                panel_bound[view.app_name].append(marked)
                with row:
                    with ui.element("label"):
                        _text("span", field.name, "operating-field-name")
                        need = "required" if field.required else "optional"
                        _text("span", f"{field.type.value} · {need}", "operating-field-type")
                    entry = ui.input(
                        password=secret,
                        placeholder="•••••••• (set)" if held else "",
                        value=panel.draft.get(field.name, ""),
                    ).props("dense borderless")
                    # What is typed is the draft's, so the box writes into it
                    # and a box drawn again reads it back. A box with nothing in
                    # it holds `None`, and the draft holds that as empty text.
                    entry.bind_value(panel.draft, field.name, forward=_typed)
                    # Several rows can declare the same field name, so a test
                    # reaches one row's box by a marker rather than by its label:
                    # the name beside it is a `<span>`, which cannot be typed into.
                    entry.mark(f"field-{view.app_name}-{field.name}")
            error = ui.element("div").classes("operating-config-error")
            panel.visibility(error, _lacks_anything)
            with error:
                _text("span", "config.invalid", "operating-code")
                message = _text("span", "")
                panel.text(message, _lacking_line)
            with ui.element("div").classes("operating-config-actions"):
                _button("Cancel", "operating-quiet", on_click=lambda: toggle_config(view))
                _button("Save", "operating-primary", on_click=lambda: save(view, panel))

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

    def draw_rail(row: RowShown) -> None:
        """Draw the row's rail: four steps, each bound to the mark it shows."""
        with ui.element("div").classes("operating-rail"):
            for index, mark in enumerate(row.view.marks):
                stage = ui.element("div").classes("operating-stage")
                stage.classes(TONE_CLASSES[mark.tone])
                painted = Tone(stage, mark.tone)
                row.into(painted, "tone", lambda view, at=index: view.marks[at].tone)
                bound.append(painted)
                with stage:
                    symbol = _text("span", mark.symbol, "operating-stage-node")
                    row.text(symbol, lambda view, at=index: view.marks[at].symbol)
                    label = _text("span", mark.label)
                    row.text(label, lambda view, at=index: view.marks[at].label)

    def draw_app(view: RowView) -> None:
        """Draw one row: its name, its rail, its buttons, its diagnostic, its form."""
        row = RowShown(view=view)
        bound.append(row)
        # A row that a listing no longer carries keeps what it last showed: the
        # set of rows is a shape, and the rebuild it asks for is the one that
        # takes this row off the screen.
        shown.into(row, "view", lambda board, held=row: board.row(held.view.app_name) or held.view)
        container = ui.element("article").classes("operating-app-row")
        # A row is reached whole -- by a test asking whether the clock replaced it.
        container.mark(f"row-{view.app_name}")
        with container:
            with ui.element("div"):
                name = _text("h2", view.title, "operating-app-name")
                row.text(name, lambda view: view.title)
                with ui.element("div").classes("operating-app-meta"):
                    version = _text("span", "")
                    row.text(
                        version, lambda view: "" if view.version is None else f"v{view.version}"
                    )
                    row.visibility(version, lambda view: view.version is not None)
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
                row.into(shaped, "shape", lambda view: view.actions)
                bound.append(shaped)
            draw_rail(row)
            draw_diagnostic(row, lambda view: view.diagnostic)

            @ui.refreshable
            def panel() -> None:
                held = panel_bound.setdefault(row.view.app_name, [])
                binding.remove(held)
                held.clear()
                open_here = open_panel.get(row.view.app_name)
                if open_here is not None:
                    draw_config(row.view, open_here)

            panel()
            panels[view.app_name] = panel.refresh

    def draw_empty() -> None:
        """Say why the board is empty: no folder, or a folder with nothing in it.

        Why it is empty is a value, not a shape, so it is bound: unregistering
        the folder under an empty board changes these two lines and rebuilds
        nothing.
        """
        with ui.element("div").classes("operating-empty"), ui.element("div"):
            head = _text("h2", "")
            shown.text(head, _empty_head)
            line = _text("p", "")
            shown.text(line, _empty_line)

    @ui.refreshable
    def rows() -> None:
        """Draw the Apps the board holds; rebuilt only when that set changes."""
        binding.remove(bound)
        bound.clear()
        for held in panel_bound.values():
            binding.remove(held)
        panel_bound.clear()
        panels.clear()
        # An App can leave the listing by a path that is nobody's button -- a
        # wheel removed, the folder unregistered, an uninstall in another
        # window. What it was holding in its panel goes with it.
        for gone in set(open_panel) - set(shown.board.names):
            open_panel.pop(gone)
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
                shown.into(listing_shape, "shape", lambda view: view.names)
    ui.timer(REFRESH_SECONDS, reread)


def _said_by(info: ErrorInfo | None, read: Callable[[ErrorInfo], str], /) -> str:
    """Read one part of a diagnostic, or nothing where there is no diagnostic.

    A hidden line is still bound, and what a binding reads is read whether or
    not the visibility beside it hides the line.
    """
    return "" if info is None else read(info)


def _typed(value: str | None, /) -> str:
    """Read what a box holds as the draft holds it: nothing in it is empty text."""
    return "" if value is None else value


def _draft(described: ConfigDescription, /) -> dict[str, str]:
    """Seed a panel's draft: what the operating role holds, and nothing for a secret."""
    return {
        field.name: ""
        if field.type is ConfigFieldType.SECRET
        else str(described.values.get(field.name, ""))
        for field in described.fields
    }


def _empty_head(view: BoardView, /) -> str:
    """Head the empty board with what is missing: a folder, or Apps in one."""
    return "No apps found" if view.registered else "No package folder selected"


def _empty_line(view: BoardView, /) -> str:
    """Say what to do about an empty board."""
    return (
        "This package folder does not contain any compatible VibePy Apps."
        if view.registered
        else "Choose a package folder above to see available apps."
    )


def _lacks_anything(lacking: Sequence[str], /) -> bool:
    """Say whether a panel has anything to name as missing."""
    return bool(lacking)


def _lacking_line(lacking: Sequence[str], /) -> str:
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
