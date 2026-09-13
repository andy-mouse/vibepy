# ADR-042: The package folder is chosen with the operating system's folder dialog

Status: Proposed

## Context

The board asks the operator for one filesystem path: the folder of wheels the operating role
reads to decide what can be installed and what has a newer version. It asked for it as a text
box, and a typed path is the one input a file manager exists to avoid — a typo, a quoted drag,
a path relative to a working directory the operator cannot see.

A browser page cannot supply a path. MDN states that `Window.showDirectoryPicker()` resolves to a
`FileSystemDirectoryHandle`, that it is available only in a secure context, and that it is not
Baseline — Firefox and Safari do not implement it
(<https://developer.mozilla.org/en-US/docs/Web/API/Window/showDirectoryPicker>). A handle is not a
path, and a handle cannot be turned into one; NiceGUI's FAQ says the same of `ui.upload`, which
hands the server bytes and a name. So the page is not where this question can be answered,
whatever is put on it.

Studio runs on the operator's own machine — ADR-040 installs it there and the Hub appears in that
machine's browser. The process that serves the page is therefore the process that can show a
window on that machine's desktop. That makes choosing a folder a host operation of the operating
role: something Studio's process does with the computer it is installed on, in the same family as
starting a child process or writing under the Studio root, and not a concern of the NiceGUI
adapter or of the Page model, neither of which knows there is a desktop.

Both platforms Studio targets publish the dialog and publish which call is the current one:

- Windows: `IFileOpenDialog` with `FOS_PICKFOLDERS`, documented as "Present an Open dialog that
  offers a choice of folders rather than files", available since Windows Vista
  (<https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-ifileopendialog>,
  <https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/ne-shobjidl_core-_fileopendialogoptions>).
  Microsoft's own page for the older `SHBrowseForFolder` recommends the Common Item Dialog in its
  place for Vista and later
  (<https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shbrowseforfoldera>).
- macOS: Standard Additions' `choose folder`, whose result is an alias and whose path is taken
  with `POSIX path of`
  (<https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/PromptforaFileorFolder.html>).
  An operator who cancels raises AppleScript's user-canceled error, number -128.

## Decision

The board's package folder is chosen with the operating system's own folder dialog, opened by
Studio's own process, and Studio stays a browser-served Web channel.

Choosing a folder is a *host operation* of the operating role: what it does with the machine it
runs on, as against its core, which is the state its Tools act on. The two are separate because
they have different callers — a Tool handler reaches the core through its ToolContext, and
nothing may reach the core any other way (ADR-024), while a host operation is reached by the Web
implementation directly. It answers with a path or with nothing, because cancelling is an answer
and not a failure.

A host operation is not a Tool, and the operating role's Web implementation calls it directly.
A Tool is channel-neutral (ADR-001), and this is not: a Tool that opens a modal window on the
server's desktop means nothing to an agent on the other end of an MCP connection, and the only
way to make it mean something would be to have it behave differently per channel, which is the
one thing a Tool must not do. Nor is it business state: nothing about an App changes because a
dialog was shown, so ADR-002's rule that a Page does not bypass a Tool for a state change is not
in play. What the operator picked becomes an argument to the Tool that registers the wheelhouse,
and that Tool is channel-neutral as it was — an agent passes the path it already knows.

Rejected: **NiceGUI's native mode**, which changes how Studio's window opens and couples the way
the operator sees Studio to a decision ADR-040 has taken but not yet built; **a folder browser
rendered in the page**, which is not the operating system's dialog — it would be a second file
manager to build, to make keyboard-reachable and to keep correct on two platforms, and it would
still be worse than the one already on the machine; **keeping the text box**, which is the
problem.

## Consequences

- The dialog is a window of the Studio process and appears beside the browser, not inside it. An
  operator who has moved the browser to another machine does not see it; that is a consequence of
  Studio being a local application, which ADR-040 already decided.
- There is a platform branch, and it is explicit. Two platforms are two branches with a named
  failure for a third; no registry and no indirection until a third platform exists.
- No headless run can exercise the dialog: it is a modal window waiting for a person. The seam
  between Studio and the platform is what the suite tests, and the dialog itself is verified by
  hand once per platform. A gate that stays green is therefore not evidence that the dialog
  opens.
- No start folder is set on either platform: the dialog opens where the operating system opens
  it, which is the folder the operator last used there. That is the file dialog's own convention,
  and setting a folder — the home folder was considered — would add a call that can fail before
  the dialog is shown, for a start the operator would leave on the first click.
- Linux is out of scope until Studio targets it, and asking for it there fails by name rather
  than by a missing binary or an empty result.
