"""The desktop dialogs Studio's own process opens on the machine it runs on.

A browser page cannot answer with a filesystem path, and Studio runs on the
operator's machine, so the process that serves the page is the one that shows
the dialog. ADR-042, in `docs/decisions/`, says why that is where this belongs
rather than in the NiceGUI adapter or the Page model.

macOS asks Standard Additions, whose `choose folder` returns an alias and whose
`POSIX path of` yields the path
(<https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/PromptforaFileorFolder.html>);
cancelling raises AppleScript's user-canceled error, number -128.

Windows asks the Common Item Dialog, which Microsoft documents call by call:
`CoInitializeEx` with `COINIT_APARTMENTTHREADED` initializes the thread that
shows it
(<https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-coinitializeex>),
`CoCreateInstance` makes `CLSID_FileOpenDialog`
(<https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-cocreateinstance>),
`IFileDialog::SetOptions` with `FOS_PICKFOLDERS` makes it "an Open dialog that
offers a choice of folders rather than files" and `FOS_FORCEFILESYSTEM` keeps
the answer to items that have a path
(<https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-ifileopendialog>,
<https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/ne-shobjidl_core-_fileopendialogoptions>),
`IFileDialog::SetTitle` names it, `IFileDialog::Show` returns
`HRESULT_FROM_WIN32(ERROR_CANCELLED)` when the operator closes it
(<https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifiledialog-show>),
`IFileDialog::GetResult` yields an `IShellItem` whose
`GetDisplayName(SIGDN_FILESYSPATH)` is the path
(<https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ishellitem-getdisplayname>),
and `CoTaskMemFree` releases the string the callee allocated
(<https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-cotaskmemfree>).
Microsoft is the authority for every one of those; the vtable arithmetic below
is ours, because `ctypes` carries no declaration of these interfaces.
"""

import asyncio
import logging
import subprocess
import sys
from pathlib import PurePath

logger = logging.getLogger(__name__)


class FolderDialogFailed(Exception):
    """The dialog could not be shown, or was shown and did not answer.

    Cancelling is not this: an operator who closes the dialog has answered, and
    `choose_folder` says so with `None`.
    """


class PlatformUnsupported(FolderDialogFailed):
    """This platform has no folder dialog here.

    Its own type because a caller answers it differently: nothing went wrong on
    the machine, Studio simply does not target it (ADR-042).
    """

    def __init__(self, platform: str, /) -> None:
        """Record the `sys.platform` that has no branch."""
        super().__init__(f"No folder dialog for platform {platform!r}.")
        self.platform = platform


CANCELLED = "-128"
"""AppleScript's user-canceled error number, as `osascript` writes it to standard error."""


def _applescript_string(text: str, /) -> str:
    """Return `text` as an AppleScript string literal, backslash and quote escaped.

    The title reaches the script as source, so it is escaped where it is built
    rather than trusted to contain nothing.
    """
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _choose_folder_on_macos(title: str, /) -> PurePath | None:
    """Show `choose folder` through `osascript` and return what it printed."""
    script = f"POSIX path of (choose folder with prompt {_applescript_string(title)})"
    done = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        if CANCELLED in done.stderr:
            return None
        raise FolderDialogFailed(f"osascript failed: {done.stderr.strip()}")
    chosen = done.stdout.strip()
    if not chosen:
        raise FolderDialogFailed("osascript answered with no path.")
    return PurePath(chosen)


if sys.platform == "win32":
    # Everything below names a symbol that exists only on Windows, so it is
    # written inside the platform test rather than imported at the top: on macOS
    # this block is unreachable and is neither run nor typechecked, and Windows
    # CI is what checks it.
    import ctypes
    from typing import Any

    _CLSID_FILE_OPEN_DIALOG = "{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}"
    _IID_IFILE_OPEN_DIALOG = "{D57C7288-D4AD-4768-BE02-9D969532D960}"
    _CLSCTX_INPROC_SERVER = 0x1
    _COINIT_APARTMENTTHREADED = 0x2
    _FOS_PICKFOLDERS = 0x00000020
    _FOS_FORCEFILESYSTEM = 0x00000040
    _SIGDN_FILESYSPATH = 0x80058000
    _CANCELLED_HRESULT = -2147023673
    """`HRESULT_FROM_WIN32(ERROR_CANCELLED)`, 0x800704C7, as a signed long."""

    # Vtable slots. The first three are `IUnknown`'s, so a slot on either
    # interface counts from three in the order its documentation lists it.
    _RELEASE = 2
    _SET_OPTIONS = 9
    _SET_TITLE = 17
    _SHOW = 3
    _GET_RESULT = 20
    _GET_DISPLAY_NAME = 5

    class _Guid(ctypes.Structure):
        """`GUID`, as `guiddef.h` lays it out."""

        _fields_ = (
            ("data1", ctypes.c_ulong),
            ("data2", ctypes.c_ushort),
            ("data3", ctypes.c_ushort),
            ("data4", ctypes.c_ubyte * 8),
        )

    def _com_call(interface: "ctypes.c_void_p", slot: int, /, *arguments: Any) -> int:
        """Call slot `slot` of `interface`'s vtable and return the `HRESULT`.

        `ctypes` declares no COM interface, so the vtable is walked by hand: a
        COM interface pointer points at a pointer to an array of function
        pointers. Each argument must be a `ctypes` instance, because its type is
        what the call's prototype is built from.

        This is the one function here that is typed with `Any`. Everything a
        `ctypes` prototype produces is dynamic, and keeping it in one three-line
        function is what stops that from spreading.
        """
        table: Any = ctypes.cast(interface, ctypes.POINTER(ctypes.c_void_p))
        methods: Any = ctypes.cast(ctypes.c_void_p(table[0]), ctypes.POINTER(ctypes.c_void_p))
        prototype: Any = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, *(type(argument) for argument in arguments)
        )
        return int(prototype(methods[slot])(interface, *arguments))

    def _checked(result: int, call: str, /) -> None:
        """Raise unless `result` is a success `HRESULT`."""
        if result < 0:
            raise FolderDialogFailed(f"{call} failed with HRESULT 0x{result & 0xFFFFFFFF:08X}.")

    def _show_folder_dialog(title: str, /) -> str | None:
        """Show the Common Item Dialog in folder-picking mode on this thread.

        The seam a test replaces: everything below it is the platform, and
        everything above it is ours.
        """
        ole32: Any = ctypes.WinDLL("ole32")
        _checked(ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED), "CoInitializeEx")
        try:
            clsid = _guid(ole32, _CLSID_FILE_OPEN_DIALOG)
            iid = _guid(ole32, _IID_IFILE_OPEN_DIALOG)
            dialog = ctypes.c_void_p()
            _checked(
                ole32.CoCreateInstance(
                    ctypes.byref(clsid),
                    None,
                    _CLSCTX_INPROC_SERVER,
                    ctypes.byref(iid),
                    ctypes.byref(dialog),
                ),
                "CoCreateInstance",
            )
            try:
                _checked(
                    _com_call(
                        dialog,
                        _SET_OPTIONS,
                        ctypes.c_ulong(_FOS_PICKFOLDERS | _FOS_FORCEFILESYSTEM),
                    ),
                    "IFileDialog::SetOptions",
                )
                _checked(
                    _com_call(dialog, _SET_TITLE, ctypes.c_wchar_p(title)),
                    "IFileDialog::SetTitle",
                )
                shown = _com_call(dialog, _SHOW, ctypes.c_void_p(None))
                if shown == _CANCELLED_HRESULT:
                    return None
                _checked(shown, "IFileDialog::Show")
                item = ctypes.c_void_p()
                _checked(
                    _com_call(dialog, _GET_RESULT, ctypes.pointer(item)),
                    "IFileOpenDialog::GetResult",
                )
                try:
                    return _display_name(ole32, item)
                finally:
                    _com_call(item, _RELEASE)
            finally:
                _com_call(dialog, _RELEASE)
        finally:
            ole32.CoUninitialize()

    def _display_name(ole32: Any, item: "ctypes.c_void_p", /) -> str:
        """Return the filesystem path of `item`, freeing the string COM allocated."""
        buffer = ctypes.c_wchar_p()
        _checked(
            _com_call(
                item, _GET_DISPLAY_NAME, ctypes.c_ulong(_SIGDN_FILESYSPATH), ctypes.pointer(buffer)
            ),
            "IShellItem::GetDisplayName",
        )
        try:
            chosen = buffer.value
        finally:
            ole32.CoTaskMemFree(buffer)
        if not chosen:
            raise FolderDialogFailed("IShellItem::GetDisplayName answered with no path.")
        return chosen

    def _guid(ole32: Any, text: str, /) -> "ctypes.Structure":
        """Parse a registry-format GUID into the 16 bytes COM takes."""
        parsed = _Guid()
        _checked(ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(parsed)), text)
        return parsed

    def _choose_folder_on_windows(title: str, /) -> PurePath | None:
        """Show the dialog and return the chosen folder, or `None` if it was cancelled."""
        chosen = _show_folder_dialog(title)
        return None if chosen is None else PurePath(chosen)


async def choose_folder(*, title: str) -> PurePath | None:
    """Ask the operator for a folder with this platform's own dialog.

    `title` names the dialog. The answer is the chosen folder, or `None` when the
    operator cancelled — which is an answer, not a failure. Raises
    `PlatformUnsupported` where Studio has no dialog, and `FolderDialogFailed`
    when the platform's own dialog did not work.

    The dialog is modal and holds its thread until the operator is done, so it
    runs in one of `asyncio`'s.
    """
    if sys.platform == "darwin":
        return await asyncio.to_thread(_choose_folder_on_macos, title)
    if sys.platform == "win32":
        return await asyncio.to_thread(_choose_folder_on_windows, title)
    raise PlatformUnsupported(sys.platform)
