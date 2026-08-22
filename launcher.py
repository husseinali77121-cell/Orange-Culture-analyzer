#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""launcher.py — Orange Lab Microbiology CDSS, desktop entry point.

WHAT THIS IS
PyInstaller cannot package "streamlit run streamlit_app.py" directly — there
is no such thing as a compiled Streamlit app; Streamlit is a local web server
that a browser connects to. This script IS the .exe: it starts that server
programmatically, points it at the bundled copy of streamlit_app.py, and
opens the default browser to it. The user sees a desktop app (double-click,
window opens); underneath, it's still Streamlit, unchanged — the architecture
recommended when this was first discussed: don't rewrite the UI, wrap it.

    double-click Orange-CDSS.exe
        -> this script starts a LOCAL streamlit server (127.0.0.1, random-ish
           free port, headless, no external network listener)
        -> opens the browser to it automatically
        -> streamlit_app.py runs exactly as it does today, unmodified

WHY A LAUNCHER AND NOT JUST BUNDLING streamlit_app.py DIRECTLY
Two things streamlit_app.py currently discovers at import time by walking
its own directory (Tesseract via pytesseract's default PATH lookup, fonts via
relative paths) need to instead be pointed at PyInstaller's extraction
directory (sys._MEIPASS) when frozen. Rather than scatter frozen-vs-dev
branching through the 7,600-line app file, this launcher sets the handful of
environment variables that make the bundled binaries discoverable BEFORE the
app ever imports pytesseract/weasyprint, then hands off to Streamlit's own
CLI entry point unchanged.

OFFLINE BY DESIGN
No step here requires network access: the server binds to localhost only,
Tesseract/tessdata/fonts are read from the local bundle, and this app's
guideline data (clinical_data.py, abx_guidelines.py, guideline_registry.py,
organism_profile.py) is Python source shipped inside the executable, not
fetched at runtime. The one exception a lab should know about: this repo's
sibling projects (HVMS, pricing/invoicing, Send-Out) use the GitHub Contents
API for persistence — this app does not; nothing here calls out to GitHub.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser


def _bundle_root() -> str:
    """PyInstaller extracts bundled data to sys._MEIPASS at runtime; when run
    from source (not frozen), fall back to this file's own directory so the
    launcher also works for local testing before packaging."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _find_free_port(preferred: int = 8501) -> int:
    """Prefer 8501 (Streamlit's default, least surprising to a lab tech who
    might have used the cloud version before), fall back to any free port if
    something else on the machine already holds it."""
    for port in [preferred] + list(range(8600, 8700)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free local port found for the CDSS server")


def _configure_environment(base: str) -> None:
    """Point every native dependency at the bundled copy, BEFORE anything
    imports pytesseract/weasyprint/streamlit. Order matters: os.environ must
    be set before those modules resolve their own binary/data paths."""

    # Tesseract OCR — bundled at tesseract/tesseract.exe with tessdata/ beside
    # it (eng.traineddata, ara.traineddata). pytesseract reads this env var
    # directly rather than searching PATH, which keeps this fully offline and
    # independent of whatever (if anything) is installed system-wide.
    tesseract_dir = os.path.join(base, "tesseract")
    tesseract_exe = os.path.join(tesseract_dir, "tesseract.exe")
    if os.path.exists(tesseract_exe):
        os.environ["TESSERACT_CMD"] = tesseract_exe
        os.environ["TESSDATA_PREFIX"] = os.path.join(tesseract_dir, "tessdata")

    # WeasyPrint's PDF rendering depends on the GTK3 runtime (Pango, Cairo,
    # GDK-Pixbuf, HarfBuzz) — these are NOT part of a standard Windows
    # install and are the single highest-risk piece of this bundle (see
    # build-exe.yml's own notes on this). If a gtk3-runtime/ folder is
    # bundled, prepend it to PATH so the DLLs are found the same way they
    # would be if GTK3 Runtime for Windows were installed system-wide.
    gtk_dir = os.path.join(base, "gtk3-runtime", "bin")
    if os.path.isdir(gtk_dir):
        os.environ["PATH"] = gtk_dir + os.pathsep + os.environ.get("PATH", "")

    # Fonts (Noto/Amiri for Arabic shaping, DejaVu, Liberation) — WeasyPrint
    # and the dashboard image renderer both read fonts by path already;
    # nothing else to configure here beyond making sure the fonts/ folder
    # shipped alongside the exe, which build-exe.yml's datas= list handles.

    # Never phone home for usage stats, never prompt for an email on first
    # run — this is a clinical tool on a lab workstation, not a public demo.
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("STREAMLIT_CLIENT_TOOLBAR_MODE", "minimal")
    # Bind to localhost only -- this is a single-workstation desktop tool,
    # not a server meant to be reachable from the lab's network.
    os.environ.setdefault("STREAMLIT_SERVER_ADDRESS", "127.0.0.1")

    # Read by streamlit_app.py to show the "🟢 OFFLINE -- Local Clinical
    # Engine" badge near the top of the page -- reassurance for a lab tech
    # that the app is not silently expecting an internet connection it
    # doesn't have. Not set when run from source (`python launcher.py`
    # during development), only when actually frozen by PyInstaller.
    if getattr(sys, "frozen", False):
        os.environ["ORANGE_CDSS_OFFLINE_MODE"] = "1"


def main() -> int:
    base = _bundle_root()
    # streamlit_app.py loads commercial_names.txt via a bare relative path
    # (load_commercial_names(filepath="commercial_names.txt")), which resolves
    # against the process's CURRENT WORKING DIRECTORY -- not necessarily
    # sys._MEIPASS, and definitely not guaranteed to be this exe's own folder
    # depending on how the user launched it (double-click vs. a shortcut with
    # a different "Start in" directory vs. a taskbar pin). Without this, the
    # app can silently run with COMMERCIAL_NAMES = {} depending on launch
    # method -- a working-when-tested, broken-when-shipped class of bug.
    os.chdir(base)
    _configure_environment(base)

    app_path = os.path.join(base, "streamlit_app.py")
    if not os.path.exists(app_path):
        print(f"FATAL: streamlit_app.py not found at {app_path}")
        print("This usually means the PyInstaller spec's datas= list is out "
              "of date. See orange_cdss.spec.")
        return 1

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    def _open_browser_when_ready() -> None:
        # Streamlit needs a moment to bind its socket; poll rather than
        # guess a fixed sleep, so this launcher isn't slower than it needs
        # to be on a fast machine or too eager on a slow one.
        deadline = time.time() + 30
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    webbrowser.open(url)
                    return
            time.sleep(0.3)
        print(f"Server did not come up within 30s -- open {url} manually.")

    threading.Thread(target=_open_browser_when_ready, daemon=True).start()

    # Hand off to Streamlit's own CLI exactly as `streamlit run` would --
    # streamlit_app.py itself is completely unmodified by being frozen.
    sys.argv = [
        "streamlit", "run", app_path,
        "--server.port", str(port),
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    from streamlit.web import cli as stcli
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())
