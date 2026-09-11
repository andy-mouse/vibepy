"""Writing a file whole, so that nothing reads half of one.

Two of the Hub's files are read by something other than the Hub while the Hub
is writing them: its state file, which a second window reads, and the routing
files, which the proxy watches. Both need the same guarantee, and it was
written twice before it was written here -- once with a staged name unique to
the write and once without, which is what re-deriving one argument in two
places does.
"""

import logging
import os
import stat
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

OWNER_ONLY_FILE = stat.S_IRUSR | stat.S_IWUSR
OWNER_ONLY_DIRECTORY = stat.S_IRWXU


def write_whole(path: Path, text: str, /, *, staging: Path, owner_only: bool = False) -> None:
    """Replace `path` with `text`, or leave what was already there.

    The text is written to a file in `staging` and moved into place, because
    `os.replace` overwrites the destination and the rename is atomic where POSIX
    requires it (<https://docs.python.org/3/library/os.html#os.replace>). No
    reader sees a partial file, and a write that fails leaves the previous
    contents where they were.

    `staging` is the caller's to name, because where it is safe to stage is the
    caller's fact: a routing file is staged outside the directory the proxy
    watches, so a file the provider was never meant to read does not appear
    there at all. The staged name belongs to this write, so two writers of one
    destination cannot take each other's file -- the Hub serializes no Tool
    invocation.

    `owner_only` restricts the file and the directory it lands in to their
    owner, which is what a file holding secrets needs. `os.chmod` carries these
    bits on POSIX; on Windows it sets only the read-only flag, so a directory
    there is protected by its own access control instead.
    """
    pending = staging / f".{path.name}.{uuid4().hex}.pending"
    pending.write_text(text, encoding="utf-8")
    if owner_only and os.name != "nt":
        os.chmod(path.parent, OWNER_ONLY_DIRECTORY)
        os.chmod(pending, OWNER_ONLY_FILE)
    try:
        os.replace(pending, path)
    except OSError:
        pending.unlink(missing_ok=True)
        raise
