"""The board: every App the Hub knows of, and what can be done to each.

A Page over Tools. It reads `list_apps` and draws; every button invokes one Tool
and redraws; a timer redraws on its own so a child that died or an action taken
elsewhere reaches the screen. The rules of what to draw are `presentation.py`'s.
"""

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from nicegui import ui

from vibepy_core import Page, PageContext, PageDefinition
from vibepy_hub.models import (
    AppListing,
    ConfigDescription,
    Diagnostic,
    Installation,
    SourceListing,
)
from vibepy_hub.pages.presentation import (
    Action,
    RowView,
    row_view,
    save_request,
    sort_rows,
    summary,
)

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 3.0


async def board(ctx: PageContext) -> None:
    """Draw the board and keep it current."""
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

    def draw_summary(listed: AppListing) -> None:
        """Say how many Apps are available, installed and running."""
        available, installed, running = summary(listed.apps)
        with ui.row().classes("items-center gap-6"):
            ui.label("Hub").classes("text-xl")
            ui.label(f"{available} available · {installed} installed · {running} running")
        if listed.diagnostic is not None:
            ui.label(f"{listed.diagnostic.code}: {listed.diagnostic.message}").classes(
                "text-negative"
            )

    async def register(path: str | None) -> None:
        """Register one folder of wheels as the package source."""
        async with working():
            answer = await call("register_package_source", {"path": path or ""})
            if isinstance(answer, SourceListing) and answer.diagnostic is None:
                ui.notify(f"{len(answer.candidates)} apps available from {answer.source}.")
        content.refresh()

    async def unregister() -> None:
        """Forget the package source, once the user has confirmed it."""
        async with working():
            with dialogs, ui.dialog() as dialog, ui.card():
                ui.label(
                    "Unregister this package folder? The folder, installed apps, "
                    "and app data will not be deleted."
                )
                with ui.row():
                    ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
                    ui.button("Unregister", on_click=lambda: dialog.submit(True))
            if await dialog:
                await call("remove_package_source", {})
            dialogs.clear()
        content.refresh()

    def draw_source(listed: AppListing) -> None:
        """Draw the source card: a path and Unregister, or an input and Register."""
        with ui.card().classes("w-full"), ui.row().classes("items-center gap-4"):
            if listed.source is None:
                entry = ui.input(label="package folder").classes("grow")
                editing.append((entry, ""))
                ui.button("Register", on_click=lambda: register(entry.value))
            else:
                ui.label(str(listed.source)).classes("grow")
                ui.button("Unregister", on_click=unregister).props("flat")

    async def act(action: Action, view: RowView) -> None:
        """Run one row's action, say what happened, and redraw."""
        if action.tool == "describe_config":
            await toggle_config(view)
            return
        async with working():
            if action.tool == "remove_app" and not await confirm_uninstall(view):
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

    async def confirm_uninstall(view: RowView) -> bool:
        """Ask before an App leaves the machine."""
        with dialogs, ui.dialog() as dialog, ui.card():
            ui.label(f"Uninstall {view.title}? App data will be retained.")
            with ui.row():
                ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
                ui.button("Uninstall", on_click=lambda: dialog.submit(True))
        confirmed = bool(await dialog)
        dialogs.clear()
        return confirmed

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
        lacking: ui.label,
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
            lacking.text = _lacking_line(request)
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
        with ui.card().classes("w-full"):
            if not described.fields:
                ui.label("Nothing to configure")
                ui.button("Cancel", on_click=lambda: toggle_config(view)).props("flat")
                return
            inputs: dict[str, ui.input] = {}
            for field in described.fields:
                secret = field.type == "secret"
                held = secret and field.name in described.secrets_set
                entry = ui.input(
                    label=field.name,
                    password=secret,
                    placeholder="•••••••• (set)" if held else "",
                    value="" if secret else str(described.values.get(field.name, "")),
                ).classes("w-full")
                editing.append((entry, str(entry.value)))
                inputs[field.name] = entry
                ui.label(f"{field.type} · {'required' if field.required else 'optional'}").classes(
                    "text-xs"
                )
            lacking = ui.label(_lacking_line(missing.get(view.app_name, [])))
            lacking.classes("text-negative")
            with ui.row():
                ui.button("Cancel", on_click=lambda: toggle_config(view)).props("flat")
                ui.button("Save", on_click=lambda: save(view, described, inputs, lacking))

    def _on_click(action: Action, view: RowView) -> Callable[[], Awaitable[None]]:
        """Bind one button to one row's action, so a loop's variable cannot leak."""
        return lambda: act(action, view)

    def draw_app(view: RowView) -> None:
        """Draw one row: its title, its rail, its buttons, its diagnostic."""
        with ui.card().classes("w-full"):
            # The buttons are drawn before the rail: a rail label and a button
            # can carry the same word ("Configured", "Configure"), and what a
            # reader -- or a test -- reaches for by that word is the button.
            with ui.row().classes("w-full items-center gap-4"):
                ui.label(view.title).classes("text-lg")
                if view.version is not None:
                    ui.label(f"v{view.version}")
                ui.space()
                for action in view.actions:
                    button = ui.button(action.label, on_click=_on_click(action, view))
                    if not action.primary:
                        button.props("flat")
                    if not action.enabled:
                        button.disable()
            with ui.row().classes("items-center gap-3"):
                for mark in view.marks:
                    label = ui.label(f"{mark.symbol} {mark.label}")
                    if mark.done:
                        label.classes("text-positive")
            if view.diagnostic is not None:
                ui.label(f"{view.diagnostic.code}: {view.diagnostic.message}").classes(
                    "text-negative"
                )
            if view.app_name in open_config:
                draw_config(view)

    @ui.refreshable
    async def content() -> None:
        editing.clear()
        listed = AppListing.model_validate(await ctx.tools.invoke("list_apps", {}))
        draw_summary(listed)
        draw_source(listed)
        rows = sort_rows(listed.apps)
        if not rows:
            ui.label("No apps found" if listed.source is not None else "No folder registered")
            return
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
