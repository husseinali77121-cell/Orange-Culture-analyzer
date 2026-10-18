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

2026-10-19 — WHY THIS FILE GREW (diagnosability, not features)
The first CI run that got as far as launching the frozen exe failed with
"exe did not serve a page" and NOTHING else, because the spec builds a
windowed exe (console=False). In a windowed PyInstaller exe sys.stdout and
sys.stderr are None, so every traceback, every Streamlit log line, every
crash message was thrown away — the failure was invisible. So:

  * Frozen runs now redirect stdout/stderr (and faulthandler, for native DLL
    crashes) into a log file: %LOCALAPPDATA%\\Orange-CDSS\\launcher.log, or the
    path in ORANGE_CDSS_LOG. CI sets that variable and prints the file.
  * Any exception during startup is written to that log with a full
    traceback and, on a real desktop, shown in a message box — a lab tech
    gets a readable error instead of a window that silently never appears.
  * `Orange-CDSS.exe --selftest` imports every bundled module, runs the
    bundled Tesseract, and renders a PDF (incl. Arabic) INSIDE the frozen
    exe, then exits 0/1. HTTP 200 on the start page cannot prove any of that.
  * Streamlit is told explicitly that it is NOT in development mode (a
    frozen app's streamlit/ folder has no "site-packages" in its path, which
    is exactly what Streamlit uses to guess "this is a dev checkout"), and to
    skip its file watcher (nothing to watch inside a bundle).
  * Tesseract's folder is now put on PATH. The earlier version only set a
    TESSERACT_CMD variable, which neither pytesseract nor this app ever
    reads — OCR inside the exe would have failed even with the server up.

Environment switches (all optional; used by CI):
    ORANGE_CDSS_LOG          full path of the log file
    ORANGE_CDSS_PORT         preferred port (default 8501)
    ORANGE_CDSS_NO_BROWSER   "1" -> do not open a browser / show dialogs
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
import traceback
import webbrowser

# Keep a module-level reference so the log file object is never garbage
# collected while sys.stdout / sys.stderr point at it.
_LOG_FH = None


def _bundle_root() -> str:
    """PyInstaller extracts bundled data to sys._MEIPASS at runtime; when run
    from source (not frozen), fall back to this file's own directory so the
    launcher also works for local testing before packaging."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _setup_logging() -> str:
    """Send stdout/stderr to a log file when frozen (or when ORANGE_CDSS_LOG
    is set). Returns the log path ("" if no log could be opened)."""
    global _LOG_FH
    path = os.environ.get("ORANGE_CDSS_LOG", "")
    frozen = bool(getattr(sys, "frozen", False))
    if not path and frozen:
        root = (os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP")
                or tempfile.gettempdir())
        path = os.path.join(root, "Orange-CDSS", "launcher.log")
    if not path:
        return ""          # plain `python launcher.py` in a terminal: no-op
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        mode = "w" if (os.path.exists(path) and os.path.getsize(path) > 1_000_000) else "a"
        _LOG_FH = open(path, mode, encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        return ""
    # Windowed exe: stdout/stderr are None. Even if they are not None (a
    # console build), a log file is what we want a lab tech to be able to send.
    sys.stdout = _LOG_FH
    sys.stderr = _LOG_FH
    try:
        import faulthandler
        # Native crashes (a bad DLL in cv2 / GTK / Tesseract) bypass Python's
        # exception machinery entirely; faulthandler is the only thing that
        # records them.
        faulthandler.enable(file=_LOG_FH, all_threads=True)
    except Exception:
        pass
    print(f"\n===== Orange-CDSS launcher {time.strftime('%Y-%m-%d %H:%M:%S')} "
          f"frozen={frozen} pid={os.getpid()} argv={sys.argv[1:]} =====", flush=True)
    return path


def _find_free_port(preferred: int = 8501) -> int:
    """Prefer 8501 (Streamlit's default, least surprising to a lab tech who
    might have used the cloud version before), fall back to any free port if
    something else on the machine already holds it. ORANGE_CDSS_PORT lets CI
    pick a port nothing else on the runner is likely to be using."""
    env_port = os.environ.get("ORANGE_CDSS_PORT", "")
    if env_port.isdigit():
        preferred = int(env_port)
    for port in [preferred] + [p for p in range(8600, 8700) if p != preferred]:
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
    # it (eng.traineddata, ara.traineddata).
    #   * PATH: pytesseract (and anything else) finds "tesseract" through the
    #     normal PATH lookup. This is the part that actually matters.
    #   * TESSDATA_PREFIX: read by Tesseract itself (5.x: the tessdata dir).
    #   * TESSERACT_CMD: NOT read by pytesseract or by this app (verified);
    #     kept only as a convenience for scripts/diagnostics.
    #   * pytesseract.tesseract_cmd: set explicitly below as belt-and-braces.
    tesseract_dir = os.path.join(base, "tesseract")
    tesseract_exe = os.path.join(tesseract_dir, "tesseract.exe")
    if os.path.exists(tesseract_exe):
        os.environ["TESSERACT_CMD"] = tesseract_exe
        os.environ["TESSDATA_PREFIX"] = os.path.join(tesseract_dir, "tessdata")
        os.environ["PATH"] = tesseract_dir + os.pathsep + os.environ.get("PATH", "")
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tesseract_exe
        except Exception as exc:       # not fatal: PATH already covers it
            print(f"[launcher] note: could not set pytesseract.tesseract_cmd: {exc!r}")
    else:
        print(f"[launcher] WARNING: bundled Tesseract not found at {tesseract_exe}")

    # WeasyPrint's PDF rendering depends on the GTK3 runtime (Pango, Cairo,
    # GDK-Pixbuf, HarfBuzz) — these are NOT part of a standard Windows
    # install and are the single highest-risk piece of this bundle (see
    # build-exe.yml's own notes on this). If a gtk3-runtime/ folder is
    # bundled, prepend it to PATH so the DLLs are found the same way they
    # would be if GTK3 Runtime for Windows were installed system-wide, and
    # also tell WeasyPrint directly (its own documented variable).
    gtk_dir = os.path.join(base, "gtk3-runtime", "bin")
    if os.path.isdir(gtk_dir):
        os.environ["PATH"] = gtk_dir + os.pathsep + os.environ.get("PATH", "")
        os.environ.setdefault("WEASYPRINT_DLL_DIRECTORIES", gtk_dir)
    else:
        print(f"[launcher] WARNING: bundled GTK3 runtime not found at {gtk_dir} "
              f"-- PDF generation will not work")

    # Fonts (Noto/Amiri for Arabic shaping, DejaVu, Liberation) — WeasyPrint
    # and the dashboard image renderer both read fonts by path already;
    # nothing else to configure here beyond making sure the fonts/ folder
    # shipped alongside the exe, which build-exe.yml's datas= list handles.

    # Never phone home for usage stats, never prompt for an email on first
    # run — this is a clinical tool on a lab workstation, not a public demo.
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_CLIENT_TOOLBAR_MODE", "minimal")
    # Forced (not setdefault): Streamlit decides "development mode" by
    # looking for "site-packages" in its own file path. Inside a PyInstaller
    # bundle that substring is absent, so Streamlit concludes it is a dev
    # checkout, and in that mode it refuses a custom server.port and tries
    # to proxy a frontend dev server on :3000 instead of serving its bundled
    # static files. A frozen app is never a dev checkout.
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    # Nothing to watch for edits inside a bundle; skip the watcher entirely.
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
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


def _show_fatal(message: str) -> None:
    """On a real Windows desktop, show startup failures in a message box so a
    lab tech sees *something* (a windowed exe otherwise just vanishes). Never
    in CI / headless runs, where a modal box would hang the job."""
    if os.name != "nt" or os.environ.get("CI") or os.environ.get("ORANGE_CDSS_NO_BROWSER"):
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, message[:1500], "Orange CDSS — startup error", 0x10)
    except Exception:
        pass


def _serve(base: str, log_path: str) -> int:
    app_path = os.path.join(base, "streamlit_app.py")
    if not os.path.exists(app_path):
        msg = (f"FATAL: streamlit_app.py not found at {app_path}\n"
               "This usually means the PyInstaller spec's datas= list is out "
               "of date. See orange_cdss.spec.")
        print(msg)
        _show_fatal(msg)
        return 1

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"
    print(f"[launcher] serving {app_path} on {url}", flush=True)

    no_browser = os.environ.get("ORANGE_CDSS_NO_BROWSER") == "1"

    def _open_browser_when_ready() -> None:
        # Streamlit needs a moment to bind its socket; poll rather than
        # guess a fixed sleep. The first launch of a freshly installed bundle
        # is slow (antivirus scans every file once), so allow up to 2 min.
        deadline = time.time() + 120
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    print(f"[launcher] server is accepting connections on {url}", flush=True)
                    if not no_browser:
                        webbrowser.open(url)
                    return
            time.sleep(0.5)
        print(f"[launcher] server did not come up within 120s -- open {url} manually. "
              f"Log: {log_path or '(none)'}", flush=True)

    threading.Thread(target=_open_browser_when_ready, daemon=True).start()

    # Hand off to Streamlit's own CLI exactly as `streamlit run` would --
    # streamlit_app.py itself is completely unmodified by being frozen.
    # Every option is passed as a CLI flag AND (above) as an env var: the
    # flags are what Streamlit's own docs use, the env vars cover any code
    # path that reads config before the flags are parsed.
    sys.argv = [
        "streamlit", "run", app_path,
        "--server.port", str(port),
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
        "--server.fileWatcherType", "none",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]
    from streamlit.web import cli as stcli
    return stcli.main()


def _selftest(base: str) -> int:
    """`Orange-CDSS.exe --selftest`: prove, from INSIDE the frozen exe, that
    the things an HTTP 200 cannot prove actually work. Exit 0 = all critical
    checks passed; 1 = at least one failed (details in the log)."""
    import importlib
    import subprocess

    failures: list = []
    warnings: list = []

    def step(name, fn, critical=True):
        try:
            info = fn()
            print(f"[selftest] OK    {name}" + (f" -- {info}" if info else ""), flush=True)
        except Exception as exc:
            tag = "FAIL" if critical else "WARN"
            print(f"[selftest] {tag}  {name}: {exc!r}", flush=True)
            traceback.print_exc()
            reason = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            (failures if critical else warnings).append((name, reason))

    print(f"[selftest] frozen={getattr(sys, 'frozen', False)} "
          f"python={sys.version.split()[0]} base={base}", flush=True)

    # ── Streamlit itself, one small step per thing that can go wrong ──────
    # (2026-10-19, second run: a single combined "streamlit" check failed and
    # the reason was off-screen. Each part reports on its own now.)
    def chk_st_metadata():
        import importlib.metadata as md
        return f"streamlit {md.version('streamlit')}"       # PackageNotFoundError if dist-info missing
    step("Streamlit package metadata (dist-info)", chk_st_metadata)

    def chk_st_import():
        import streamlit
        return f"{streamlit.__version__} from {streamlit.__file__}"
    step("import streamlit", chk_st_import)

    def chk_st_static():
        import streamlit
        static = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
        if not os.path.exists(static):
            raise FileNotFoundError(f"Streamlit frontend missing from bundle: {static}")
        return static
    step("Streamlit web frontend (static/index.html)", chk_st_static)

    def chk_st_cli():
        from streamlit.web import cli as _cli          # noqa: F401  (what _serve() calls)
        from streamlit.web import bootstrap as _bs     # noqa: F401
        return "streamlit.web.cli and streamlit.web.bootstrap import"
    step("import streamlit.web.cli / bootstrap (what the launcher runs)", chk_st_cli)

    def chk_st_config_env_only():
        # Informational: does the env var ALONE switch development mode off?
        from streamlit import config
        config.get_config_options(force_reparse=True)
        dev = config.get_option("global.developmentMode")
        if dev:
            raise RuntimeError(f"global.developmentMode == {dev!r} with only the env var set "
                               f"(harmless: the launcher also passes the CLI flag)")
        return "env var alone is enough"
    step("developmentMode off via env var alone", chk_st_config_env_only, critical=False)

    def chk_st_config_flags():
        # The exact call `streamlit run` makes, with the exact flags _serve() passes.
        from streamlit import config
        flags = {"global.developmentMode": False, "server.port": 8765,
                 "server.address": "127.0.0.1", "server.headless": True,
                 "server.fileWatcherType": "none"}
        try:
            from streamlit.web import bootstrap
            bootstrap.load_config_options(flags)
        except AttributeError:
            config.get_config_options(force_reparse=True, options_from_flags=flags)
        dev = config.get_option("global.developmentMode")
        if dev:
            raise RuntimeError(f"global.developmentMode == {dev!r} even with the CLI flag")
        return f"launcher flags accepted; developmentMode={dev!r}, port={config.get_option('server.port')}"
    step("Streamlit accepts the launcher's config flags", chk_st_config_flags)

    # ── Third-party imports the app needs ────────────────────────────────
    for mod in ("numpy", "cv2", "PIL", "pytesseract", "arabic_reshaper",
                "bidi.algorithm", "weasyprint"):
        step(f"import {mod}",
             lambda m=mod: getattr(importlib.import_module(m), "__version__", ""))

    def chk_arabic():
        import arabic_reshaper
        from bidi.algorithm import get_display
        shaped = get_display(arabic_reshaper.reshape("مرحبا بالعالم"))
        if not shaped:
            raise RuntimeError("Arabic shaping returned an empty string")
        return f"{len(shaped)} chars"
    step("Arabic shaping (arabic_reshaper + bidi)", chk_arabic)

    # ── Every bundled application module imports cleanly ─────────────────
    skip = {"launcher", "streamlit_app"}
    names = sorted(f[:-3] for f in os.listdir(base)
                   if f.endswith(".py") and f[:-3] not in skip and not f.startswith("test_"))
    for name in names:
        step(f"import app module {name}", lambda n=name: importlib.import_module(n) and "")

    def chk_app_syntax():
        p = os.path.join(base, "streamlit_app.py")
        with open(p, "rb") as fh:
            compile(fh.read(), p, "exec")
        return p
    step("streamlit_app.py present and compiles", chk_app_syntax)

    # ── Tesseract: binary runs, English present (Arabic = warning) ───────
    langs_cache: list = []

    def _tess_exe():
        exe = os.path.join(base, "tesseract", "tesseract.exe")
        if os.path.exists(exe):
            return exe
        import shutil
        found = shutil.which("tesseract")
        if found:
            return found
        raise FileNotFoundError(f"tesseract not found in bundle ({exe}) or on PATH")

    def chk_tess_langs():
        exe = _tess_exe()
        out = subprocess.run(
            [exe, "--list-langs"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=60, text=True, errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if out.returncode != 0:
            raise RuntimeError(f"tesseract --list-langs exit {out.returncode}: {out.stdout[:300]}")
        langs_cache[:] = [ln.strip() for ln in out.stdout.splitlines()[1:] if ln.strip()]
        if "eng" not in langs_cache:
            raise RuntimeError(f"eng.traineddata not found; got {langs_cache}")
        return f"languages: {', '.join(langs_cache)}"
    step("Tesseract binary + eng language", chk_tess_langs)

    def chk_tess_ara():
        if "ara" not in langs_cache:
            raise RuntimeError("ara.traineddata missing -- Arabic OCR will not work")
        return "ara present"
    step("Tesseract Arabic language data", chk_tess_ara, critical=False)

    def chk_ocr():
        import pytesseract
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (700, 160), "white")
        try:
            font = ImageFont.load_default(size=72)
        except TypeError:                       # Pillow < 10.1
            font = ImageFont.load_default()
        ImageDraw.Draw(img).text((20, 30), "ORANGE 123", fill="black", font=font)
        txt = pytesseract.image_to_string(img, lang="eng").strip().upper().replace(" ", "")
        if "ORANGE" not in txt:
            raise RuntimeError(f"OCR of a synthetic image returned {txt!r}")
        return f"read {txt!r}"
    step("OCR end-to-end on a synthetic image (pytesseract)", chk_ocr, critical=False)

    # ── PDF: WeasyPrint + bundled GTK3, Latin and Arabic ─────────────────
    def chk_pdf():
        import weasyprint
        html = ("<html><body><h1>Orange Lab CDSS</h1>"
                "<p dir='rtl'>مرحبا بالعالم</p></body></html>")
        pdf = weasyprint.HTML(string=html).write_pdf()
        if not pdf.startswith(b"%PDF") or len(pdf) < 500:
            raise RuntimeError(f"suspicious PDF ({len(pdf)} bytes)")
        return f"{len(pdf)} bytes"
    step("PDF generation inside the exe (WeasyPrint + GTK3)", chk_pdf)

    print(f"[selftest] SUMMARY: {len(failures)} critical failure(s), "
          f"{len(warnings)} warning(s)", flush=True)
    for name, reason in warnings:
        print(f"[selftest]   warning : {name} -> {reason}", flush=True)
    if failures:
        for name, reason in failures:
            print(f"[selftest]   FAILED  : {name} -> {reason}", flush=True)
        return 1
    print("[selftest] PASSED", flush=True)
    return 0


def main() -> int:
    # Required for frozen Windows apps that (directly or through a library)
    # use multiprocessing: without it a child process re-runs this whole
    # launcher instead of its worker function.
    import multiprocessing
    multiprocessing.freeze_support()

    log_path = _setup_logging()
    try:
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
        if base not in sys.path:
            sys.path.insert(0, base)
        _configure_environment(base)

        if "--selftest" in sys.argv[1:]:
            return _selftest(base)
        return _serve(base, log_path)
    except SystemExit:
        raise
    except BaseException:
        tb = traceback.format_exc()
        print("[launcher] FATAL startup error:\n" + tb, flush=True)
        _show_fatal("The application failed to start.\n\n"
                    f"{tb.strip().splitlines()[-1]}\n\n"
                    f"Details: {log_path or '(no log file)'}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
