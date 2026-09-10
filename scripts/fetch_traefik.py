"""Fetch the pinned Traefik binary this repository's tests run against.

Traefik ships one static binary per platform, so the proxy the tests use is the
proxy a user runs. `make install` puts it in `.tools/`, which is not tracked.
"""

import hashlib
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "v3.7.12"
RELEASE = f"https://github.com/traefik/traefik/releases/download/{VERSION}"
TOOLS = Path(__file__).resolve().parents[1] / ".tools"


def asset() -> tuple[str, str]:
    """The archive for this platform, and the name of the binary inside it.

    The extracted file is named for the version it is, so raising `VERSION`
    fetches rather than leaving every warm checkout on the binary it already
    had -- which is the situation `make install` exists to prevent.
    """
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
    if sys.platform == "win32":
        return f"traefik_{VERSION}_windows_{arch}.zip", "traefik.exe"
    if sys.platform == "darwin":
        return f"traefik_{VERSION}_darwin_{arch}.tar.gz", "traefik"
    return f"traefik_{VERSION}_linux_{arch}.tar.gz", "traefik"


def expected(archive: str, /) -> str:
    """The digest the release publishes for this archive."""
    with urllib.request.urlopen(f"{RELEASE}/traefik_{VERSION}_checksums.txt") as answer:
        published = answer.read().decode()
    for line in published.splitlines():
        digest, _, name = line.partition("  ")
        if name.strip() == archive:
            return digest
    raise SystemExit(f"{archive} is not in the published checksums")


def main() -> None:
    archive, binary = asset()
    target = TOOLS / f"{Path(binary).stem}-{VERSION}{Path(binary).suffix}"
    if target.exists():
        return
    TOOLS.mkdir(parents=True, exist_ok=True)
    downloaded = TOOLS / archive
    try:
        urllib.request.urlretrieve(f"{RELEASE}/{archive}", downloaded)
        if hashlib.sha256(downloaded.read_bytes()).hexdigest() != expected(archive):
            raise SystemExit(f"{archive} does not match its published digest")
        if archive.endswith(".zip"):
            with zipfile.ZipFile(downloaded) as held:
                held.extract(binary, TOOLS)
        else:
            with tarfile.open(downloaded) as held:
                held.extract(binary, TOOLS, filter="data")
    finally:
        # Whatever happened -- a digest that did not match, an interrupted
        # download, an archive that would not open -- no half-fetched archive
        # is left for the next run to find.
        downloaded.unlink(missing_ok=True)
    (TOOLS / binary).replace(target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    main()
