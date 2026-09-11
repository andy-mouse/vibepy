"""The board: every App the Hub knows of, and what can be done to each.

A Page over Tools. It reads `list_apps` and draws; every button invokes one Tool
and redraws; a timer redraws on its own so a child that died or an action taken
elsewhere reaches the screen. The rules of what to draw are `presentation.py`'s,
and what it looks like is `board.css`.
"""

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path

from nicegui import ui

from vibepy_core import Page, PageContext, PageDefinition
from vibepy_studio.consumption.models import (
    AppListing,
    ConfigDescription,
    Installation,
    SourceListing,
)
from vibepy_studio.consumption.pages.presentation import (
    Action,
    RowView,
    row_view,
    save_request,
    sort_rows,
    summary,
)
from vibepy_studio.models import Diagnostic

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
    open_config: dict[str, ConfigDescription] = {}
    """The one row whose configuration panel is open, keyed by app name."""
    missing: dict[str, list[str]] = {}
    busy: list[None] = []
    """One entry per action in flight; the clock skips a redraw while it is not empty."""
    editing: list[tuple[ui.input, str]] = []
    """Each drawn input beside the value its draw seeded it with, refilled by each draw."""
    dialogs = ui.column()
    """Where a confirmation lives: outside the part a redraw rebuilds.

    A dialog raised from inside the refreshable container is deleted the moment
    the timer redraws, and the answer it is waiting for never arrives.
    """

    @asynccontextmanager
    async def working() -> AsyncGenerator[None]:
        """Hold the clock off for the length of one action.

        An action redrawn part-way through loses the elements its own handler
        still has to reach -- the notification it ends with, and the refresh.
        Starting an App takes seconds, which is longer than the clock waits.
        """
        busy.append(None)
        try:
            yield
        finally:
            busy.pop()

    async def call(name: str, payload: dict[str, object]) -> object:
        """Invoke one Tool and tell the user what it said; return the answer."""
        answer = await ctx.tools.invoke(name, payload)
        diagnostic = getattr(answer, "diagnostic", None)
        if isinstance(diagnostic, Diagnostic):
            ui.notify(f"{diagnostic.code}: {diagnostic.message}", type="warning")
        return answer

    async def confirm(question: str, label: str) -> bool:
        """Ask one yes-or-no question in the board's own clothes."""
        with dialogs, ui.dialog() as dialog, ui.element("div").classes("hub-dialog"):
            _text("p", question).style("margin: 0")
            with ui.element("div").classes("hub-dialog-actions"):
                _button("Cancel", "hub-quiet", on_click=lambda: dialog.submit(False))
                # The dialog repeats the word on the button that raised it, so
                # a test reaches the dialog's own answer by a marker.
                _button(
                    label,
                    "hub-primary",
                    marker="dialog-confirm",
                    on_click=lambda: dialog.submit(True),
                )
        answered = bool(await dialog)
        dialogs.clear()
        return answered

    def draw_heading(listed: AppListing) -> None:
        """Say what the board is, and how many Apps are in each state."""
        with ui.element("div").classes("hub-heading-row"):
            with ui.element("div"):
                _text("p", EYEBROW, "hub-eyebrow")
                _text("h1", TITLE)
                _text("p", SUBTITLE, "hub-subtitle")
            with ui.element("div").classes("hub-summary"):
                for count, label in zip(summary(listed.apps), SUMMARY_LABELS, strict=True):
                    with ui.element("div").classes("hub-summary-item"):
                        _text("span", str(count), "hub-summary-value")
                        _text("span", label, "hub-summary-label")

    async def register(path: str | None) -> None:
        """Register one folder of wheels as the package source.

        An empty box is answered here rather than sent: what the Tool would
        raise is `tool.input_invalid`, and an empty input is a presentation
        check, not a business rule.
        """
        if not (path or "").strip():
            ui.notify("Enter a folder path")
            return
        async with working():
            answer = await call("register_package_source", {"path": path})
            if isinstance(answer, SourceListing) and answer.diagnostic is None:
                ui.notify(f"{len(answer.candidates)} apps available from {answer.source}.")
        content.refresh()

    async def unregister() -> None:
        """Forget the package source, once the user has confirmed it."""
        async with working():
            if await confirm(
                "Unregister this package folder? The folder, installed apps, "
                "and app data will not be deleted.",
                "Unregister",
            ):
                await call("remove_package_source", {})
        content.refresh()

    def draw_registry(listed: AppListing) -> None:
        """Draw the source card: a path and Unregister, or a box and Register folder."""
        with ui.element("section").classes("hub-registry"):
            with ui.element("div"):
                _text("span", "Local packages", "hub-registry-label")
                _text(
                    "span",
                    "No folder registered" if listed.source is None else str(listed.source),
                    "hub-registry-value",
                )
            with ui.element("div").classes("hub-registry-actions"):
                if listed.source is None:
                    entry = ui.input(placeholder="package folder")
                    entry.classes("hub-registry-entry").props("dense borderless")
                    # The empty state names a package folder too, so the box is
                    # reached by a marker rather than by its placeholder.
                    entry.mark("package-folder")
                    editing.append((entry, ""))
                    _button(
                        "Register folder", "hub-primary", on_click=lambda: register(entry.value)
                    )
                else:
                    _button("Unregister", "hub-secondary", on_click=unregister)
        if listed.diagnostic is not None:
            with ui.element("div").classes("hub-diagnostic"):
                _text("span", listed.diagnostic.code, "hub-code")
                _text("span", listed.diagnostic.message)

    async def act(action: Action, view: RowView) -> None:
        """Run one row's action, say what happened, and redraw."""
        if action.tool == "describe_config":
            await toggle_config(view)
            return
        async with working():
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
            open_config.pop(view.app_name, None)
            missing.pop(view.app_name, None)
        content.refresh()

    async def toggle_config(view: RowView) -> None:
        """Open this row's configuration panel, or close the open one."""
        async with working():
            if open_config.pop(view.app_name, None) is None:
                described = await call("describe_config", {"app_name": view.app_name})
                if isinstance(described, ConfigDescription):
                    open_config.clear()
                    open_config[view.app_name] = described
            missing.pop(view.app_name, None)
        content.refresh()

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
        redrawing: a redraw reseeds every input from what the Hub holds, which
        never includes a secret and never includes what was just typed.
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
        async with working():
            answer = await call("configure_app", {"app_name": view.app_name, "values": request})
            if getattr(answer, "diagnostic", None) is None:
                ui.notify(f"{view.title} configured.")
            open_config.pop(view.app_name, None)
            missing.pop(view.app_name, None)
        content.refresh()

    def draw_config(view: RowView) -> None:
        """Draw the open row's configuration form."""
        described = open_config[view.app_name]
        lacking = missing.get(view.app_name, [])
        with ui.element("div").classes("hub-config"):
            _text("p", f"What {view.title} requires", "hub-config-head")
            if not described.fields:
                # No fields means nothing a Save could send, so only Cancel is offered.
                _text("p", "Nothing to configure", "hub-config-note")
                with ui.element("div").classes("hub-config-actions"):
                    _button("Cancel", "hub-quiet", on_click=lambda: toggle_config(view))
                return
            _text("p", CONFIG_NOTE, "hub-config-note")
            inputs: dict[str, ui.input] = {}
            rows: dict[str, ui.element] = {}
            for field in described.fields:
                secret = field.type == "secret"
                held = secret and field.name in described.secrets_set
                row = ui.element("div").classes("hub-field")
                if field.name in lacking:
                    row.classes("is-invalid")
                rows[field.name] = row
                with row:
                    with ui.element("label"):
                        _text("span", field.name, "hub-field-name")
                        need = "required" if field.required else "optional"
                        _text("span", f"{field.type} · {need}", "hub-field-type")
                    entry = ui.input(
                        password=secret,
                        placeholder="•••••••• (set)" if held else "",
                        value="" if secret else str(described.values.get(field.name, "")),
                    ).props("dense borderless")
                    # Several rows can declare the same field name, so a test
                    # reaches one row's box by a marker rather than by its label:
                    # the name beside it is a `<span>`, which cannot be typed into.
                    entry.mark(f"field-{view.app_name}-{field.name}")
                    editing.append((entry, str(entry.value)))
                    inputs[field.name] = entry
            error = ui.element("div").classes("hub-config-error")
            with error:
                _text("span", "config.invalid", "hub-code")
                message = _text("span", _lacking_line(lacking))
            error.set_visibility(bool(lacking))
            with ui.element("div").classes("hub-config-actions"):
                _button("Cancel", "hub-quiet", on_click=lambda: toggle_config(view))
                _button(
                    "Save",
                    "hub-primary",
                    on_click=lambda: save(view, described, inputs, rows, error, message),
                )

    def _on_click(action: Action, view: RowView) -> Callable[[], Awaitable[None]]:
        """Bind one button to one row's action, so a loop's variable cannot leak."""
        return lambda: act(action, view)

    def draw_app(view: RowView) -> None:
        """Draw one row: its name, its rail, its buttons, its diagnostic, its form."""
        with ui.element("article").classes("hub-app-row"):
            with ui.element("div"):
                _text("h2", view.title, "hub-app-name")
                with ui.element("div").classes("hub-app-meta"):
                    if view.version is not None:
                        _text("span", f"v{view.version}")
            # The buttons are built before the rail: a rail label and a button
            # can carry the same word ("Configured", "Configure"), and what a
            # reader -- or a test -- reaches for by that word is the button. The
            # stylesheet puts them back in the order the board shows them.
            with ui.element("div").classes("hub-actions"):
                for action in view.actions:
                    style = "hub-primary" if action.primary else "hub-secondary"
                    if action.tool == "remove_app":
                        style = "hub-danger"
                    _button(
                        action.label,
                        style,
                        # Several rows carry the same word, so a test reaches one
                        # row's button by a marker rather than by its label.
                        marker=f"{action.label.lower()}-{view.app_name}",
                        on_click=_on_click(action, view) if action.enabled else None,
                    )
            with ui.element("div").classes("hub-rail"):
                for mark in view.marks:
                    stage = ui.element("div").classes("hub-stage")
                    stage.classes(TONE_CLASSES[mark.tone])
                    with stage:
                        _text("span", mark.symbol, "hub-stage-node")
                        _text("span", mark.label)
            if view.diagnostic is not None:
                with ui.element("div").classes("hub-diagnostic"):
                    _text("span", view.diagnostic.code, "hub-code")
                    _text("span", view.diagnostic.message)
            if view.app_name in open_config:
                draw_config(view)

    def draw_empty(listed: AppListing) -> None:
        """Say why the board is empty: no folder, or a folder with nothing in it."""
        registered = listed.source is not None
        with ui.element("div").classes("hub-empty"), ui.element("div"):
            _text("h2", "No apps found" if registered else "No package folder selected")
            _text(
                "p",
                "This package folder does not contain any compatible VibePy Apps."
                if registered
                else "Choose a package folder above to see available apps.",
            )

    @ui.refreshable
    async def content() -> None:
        editing.clear()
        listed = AppListing.model_validate(await ctx.tools.invoke("list_apps", {}))
        draw_heading(listed)
        draw_registry(listed)
        rows = sort_rows(listed.apps)
        with ui.element("section").classes("hub-board"):
            if not rows:
                draw_empty(listed)
                return
            with ui.element("div").classes("hub-board-head"):
                for label in COLUMN_LABELS:
                    _text("span", label)
            for row in rows:
                draw_app(row_view(row, declares_fields=row.state != "available"))

    def unattended() -> None:
        """Redraw on the clock, unless the user is part-way through a form.

        A redraw rebuilds every element, so one arriving mid-edit takes the
        typing with it. What is on the clock is the state of other windows,
        which can wait until the user is not writing.
        """
        if busy or any(entry.value != seeded for entry, seeded in editing):
            return
        content.refresh()

    with ui.element("div").classes("vibepy-hub"), ui.element("section").classes("hub-shell"):
        with ui.element("header").classes("hub-topbar"), ui.element("div").classes("hub-brand"):
            _text("span", "V\u203a", "hub-brand-mark")
            _text("span", "VibePy Hub")
        with ui.element("main").classes("hub-main"):
            await content()
    ui.timer(REFRESH_SECONDS, unattended)


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
    definition=PageDefinition(name="board", route="/", title="Hub"),
    handler=board,
)
