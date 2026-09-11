"""Run Studio's board for development: its Web window and the proxy in front of it.

`python -m vibepy_core.serve studio` opens the window and reads its configuration from
standard input; Studio writes the proxy's install configuration as that window
opens, and Traefik is started against it once the file is there. Without the
proxy the board is reachable but the address of every App it starts is not, so
the two are one command here. Stop it with Ctrl-C and both processes go with it.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from fetch_traefik import TOOLS, VERSION

REPO = Path(__file__).resolve().parents[1]
TRAEFIK = TOOLS / (f"traefik-{VERSION}.exe" if sys.platform == "win32" else f"traefik-{VERSION}")


def main() -> int:
    """Serve Studio at `--port`, publish its Apps through the proxy at `--proxy-port`."""
    parser = argparse.ArgumentParser(prog="run_studio")
    parser.add_argument("--root", type=Path, default=REPO / ".studio-dev")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--proxy-port", type=int, default=8080)
    args = parser.parse_args()
    root: Path = args.root.resolve()
    if not TRAEFIK.exists():
        sys.stderr.write(f"{TRAEFIK} is missing; run `make install`\n")
        return 1

    studio = subprocess.Popen(
        [sys.executable, "-m", "vibepy_core.serve", "studio", "--port", str(args.port)],
        stdin=subprocess.PIPE,
        text=True,
    )
    assert studio.stdin is not None
    studio.stdin.write(json.dumps({"root": str(root), "proxy_port": args.proxy_port}))
    studio.stdin.close()

    install_config = root / "traefik.yml"
    proxy: subprocess.Popen[bytes] | None = None
    try:
        while studio.poll() is None and not install_config.exists():
            time.sleep(0.1)
        if studio.poll() is not None:
            return studio.returncode
        proxy = subprocess.Popen([str(TRAEFIK), f"--configFile={install_config}"])
        sys.stderr.write(
            f"Studio board: http://127.0.0.1:{args.port}/  "
            f"Apps: http://<app>.localhost:{args.proxy_port}/\n"
        )
        return studio.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        for process in (proxy, studio):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
