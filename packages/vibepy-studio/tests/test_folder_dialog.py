"""Asking the operator for a folder: what the platform answered, as Studio answers it.

The dialog itself is a modal window waiting for a person, so no test opens one.
What is tested is the seam on each platform -- `osascript` on macOS, the COM
call on Windows -- and the branch that has neither.
"""

import subprocess
import sys

import pytest

from vibepy_studio.operating.internals import (
    FolderDialogFailed,
    PlatformUnsupported,
    choose_folder,
    dialogs,
)

macos_only = pytest.mark.skipif(sys.platform != "darwin", reason="Standard Additions is macOS's")
windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="the Common Item Dialog is Windows'"
)


def _osascript(
    monkeypatch: pytest.MonkeyPatch, *, returncode: int, stdout: str = "", stderr: str = ""
) -> list[list[str]]:
    """Replace `osascript` with a recorded answer, and collect what it was asked."""
    asked: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        asked.append(command)
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return asked


@macos_only
async def test_the_chosen_folder_is_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    _osascript(monkeypatch, returncode=0, stdout="/Users/op/wheels\n")

    assert str(await choose_folder(title="Pick")) == "/Users/op/wheels"


@macos_only
async def test_cancelling_is_an_answer_and_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _osascript(monkeypatch, returncode=1, stderr="execution error: User canceled. (-128)")

    assert await choose_folder(title="Pick") is None


@macos_only
async def test_a_dialog_that_failed_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _osascript(monkeypatch, returncode=1, stderr="execution error: Not authorised. (-1743)")

    with pytest.raises(FolderDialogFailed):
        await choose_folder(title="Pick")


@macos_only
async def test_an_empty_answer_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _osascript(monkeypatch, returncode=0, stdout="\n")

    with pytest.raises(FolderDialogFailed):
        await choose_folder(title="Pick")


@macos_only
async def test_a_title_holding_a_quote_stays_one_applescript_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A title reaches the script as source, so it is escaped rather than trusted."""
    asked = _osascript(monkeypatch, returncode=0, stdout="/tmp\n")

    await choose_folder(title='the "wheels" folder \\ here')

    script = asked[0][-1]
    assert script == (
        'POSIX path of (choose folder with prompt "the \\"wheels\\" folder \\\\ here")'
    )


@windows_only
async def test_the_windows_dialogs_path_is_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    def chosen(title: str) -> str | None:
        return "C:\\wheels"

    monkeypatch.setattr(dialogs, "_show_folder_dialog", chosen)

    assert str(await choose_folder(title="Pick")) == "C:\\wheels"


@windows_only
async def test_a_cancelled_windows_dialog_answers_with_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def cancelled(title: str) -> str | None:
        return None

    monkeypatch.setattr(dialogs, "_show_folder_dialog", cancelled)

    assert await choose_folder(title="Pick") is None


@windows_only
async def test_a_windows_dialog_that_failed_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(title: str) -> str | None:
        raise FolderDialogFailed("IFileDialog::Show failed with HRESULT 0x80004005.")

    monkeypatch.setattr(dialogs, "_show_folder_dialog", refuse)

    with pytest.raises(FolderDialogFailed):
        await choose_folder(title="Pick")


async def test_a_platform_studio_does_not_target_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(PlatformUnsupported) as raised:
        await choose_folder(title="Pick")

    assert raised.value.platform == "linux"
