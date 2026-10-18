# EXE Build Notes — Orange Lab Microbiology CDSS (Offline Desktop)

## What exists now

| File | Purpose |
|---|---|
| `launcher.py` | The actual .exe entry point — starts a local Streamlit server pointed at the bundled `streamlit_app.py`, opens the browser, sets env vars so Tesseract/GTK3/fonts resolve to the bundle instead of a system install. |
| `orange_cdss.spec` | PyInstaller build spec. Bundles every application `.py` module as a loose file (required — see the spec's own header comment for why Streamlit needs this, not the normal frozen-import mechanism), plus `tesseract/`, `gtk3-runtime/`, `fonts/` if present. |
| `.github/workflows/build-exe.yml` | Runs on `windows-latest` (the only place a `.exe` can actually be built — PyInstaller does not cross-compile). Stages Tesseract, the GTK3 runtime, and fonts; runs a Windows pass of the clinical-engine tests first; builds; smoke-tests that the exe actually serves a page; uploads the result as a downloadable Actions artifact. |

**This was built and verified from a Linux sandbox with no Windows environment and no network access.** Every piece above compiles and is internally consistent, and the clinical-engine logic it wraps is the same code the 21-guard `cdss-tests.yml` suite already covers — but nobody has run `pyinstaller orange_cdss.spec` yet. The first real signal on whether this actually produces a working `.exe` will be the first run of `build-exe.yml` on GitHub's Windows runners.

## How to get the exe

1. Push this to GitHub (or just push `.github/workflows/build-exe.yml` — the `paths:` filter triggers it on changes to the app files too).
2. Actions tab → "Build Windows EXE (offline desktop)" → wait (~15-25 min, most of it is downloading/installing Tesseract and GTK3 on the runner).
3. Download the `Orange-CDSS-Windows` artifact from that run → unzip → `Orange-CDSS.exe` is inside, alongside its `_internal/` folder (PyInstaller's onedir layout — keep them together, don't move just the exe).

No local Windows machine needed. If you *do* want to build locally on Windows instead: install Tesseract-OCR-Windows and the GTK3 Runtime for Windows yourself, stage them into `tesseract/` and `gtk3-runtime/` next to this spec (same layout the workflow produces), then `pip install pyinstaller weasyprint` and `pyinstaller orange_cdss.spec --clean`.

## 2026-08-22 update — the first real run found a bug, now fixed

The first actual push to GitHub Actions failed at "Download Tesseract-OCR for Windows" with a confusing PowerShell parse error. Root cause: `github.com/UB-Mannheim/tesseract` does not publish its Windows installer as a GitHub Release asset at all — it's hosted on Mannheim University's own server instead — so the `releases/latest/download/...` URL this step used returned GitHub's own HTML page (which `Invoke-WebRequest` saved as `tesseract-setup.exe` with no error), and PowerShell then choked trying to run HTML as an installer.

Fixed by switching that step to Chocolatey (`choco install tesseract -y`) — pre-installed on `windows-latest` runners specifically for this kind of case, since it resolves wherever the package actually lives instead of this workflow needing to track it. The GTK3 step turned out to already point at a correct, real asset URL (pinned to a specific release tag, not `/latest/`) — it just never got a chance to run because the step before it failed first. Both downloads (and the font downloads) now also check for a valid binary header (`MZ` for `.exe`, `<` for accidental HTML) immediately after downloading, so if a URL ever goes stale again the build fails with a one-line "this URL served HTML, not a binary" error at the exact step, instead of a confusing failure two steps later.

### Second run: `-Encoding Byte` and a Unicode console crash

Two more real, narrow bugs surfaced across the next two runs, both fixed:

- **`-Encoding Byte` was removed in PowerShell 7** (what `shell: pwsh` actually runs on `windows-latest`), so the MZ-header/font-header validation added above broke immediately with "'Byte' is not a supported encoding name". Replaced every occurrence with `[System.IO.File]::ReadAllBytes(...)`, which works identically on Windows PowerShell 5.1 and PowerShell 7+.
- **`UnicodeEncodeError: 'charmap' codec can't encode character '\u2717'`** — Windows' default console codepage cannot represent the checkmarks/emoji this codebase's test suites print (`✗`, `✓`, status icons). Fixed at the job level with `env: PYTHONIOENCODING: "utf-8"`, which protects every Python invocation in the job rather than needing each test file's print statements edited individually.

Also expanded per a second-opinion audit's findings: the pre-build test step now runs all 16 suites (was 5), and GTK3/PDF staging failures now hard-fail the build instead of warning-and-continuing — plus an actual PDF-generation smoke test (not just an HTTP 200 check) using the staged GTK3 DLLs.

### Fourth run: `hasattr(st, "secrets")` and a Windows-only permission check

Two more real, narrow issues, both fixed — and the first one only became visible once the test suite got far enough for real Streamlit (installed via pip earlier in this same step) to actually import `streamlit_app.py`:

- **`StreamlitSecretNotFoundError`** — `hasattr(st, "secrets")` only proves the attribute exists (always true); accessing it (even via `.get()`) raises when no `secrets.toml` file exists anywhere, which is exactly the CI's condition (no lab-specific config is ever committed) and is *correct* — the bug was one unwrapped `st.secrets.get(...)` call among six, the other five already `try/except`-wrapped. Fixed by wrapping the sixth the same way.
- **`test_modules.py`'s file-permission check** — expected `os.stat(...).st_mode` to read `600` after `auth_service.py` calls `os.chmod(path, 0o600)`. Python's own docs say `os.chmod()` on Windows can only toggle the read-only flag, not real POSIX permission bits, so this reads `666` on every Windows machine regardless of the app code (which is correct and unchanged). The test is now platform-aware: skipped on Windows with an explicit, honest note that the auth store is NOT actually access-restricted there (real fix would need NTFS ACLs via `pywin32`/`icacls`, not attempted) — not silently glossed over.

### Fifth run: GTK3 silent install used a combined `-ArgumentList` string

The GTK3 staging step ran `Start-Process ... -ArgumentList "/S /D=$PWD\gtk3-install" -Wait` — a single combined string. `Start-Process` is documented to sometimes pass a combined argument string through as ONE token rather than splitting it, which NSIS installers (like this one) do not reliably parse as two separate switches. No exception was thrown either way, so the step reported success while `gtk3-install\bin` never actually existed — the PDF smoke test three steps later was the first thing to notice, exactly as designed (that gate existing is why this got caught before shipping, not despite it).

**Fixed two ways:**
1. Arguments now passed as a proper array (`-ArgumentList @("/S")`), the form `Start-Process` is documented to handle correctly.
2. Dropped the `/D=` redirect entirely and used only the officially-documented, confirmed-working switch (winget and the installer's own wingetly listing both document `/S` alone for this exact installer) — reading the DLLs from the installer's real default location (`%ProgramFiles%\GTK3-Runtime Win64\bin`) instead of trying to redirect it.
3. Added explicit post-install validation — exit code check, directory-exists check, and a DLL-count check (a real install has 50+; anything under 20 throws immediately with the actual count) — so a silent, empty "success" like this one cannot happen again undetected. If the GTK3 step ever goes green now, `gtk3-runtime/bin` genuinely has the DLLs in it.

## 2026-10-19 update — the exe built, but did not serve a page (sixth run)

**What the run showed.** Everything up to and including "Build with PyInstaller" went green (so GTK3 staging, the PDF smoke test and the PyInstaller build itself are fine). The step "Smoke test — exe starts and serves a page" then failed after ~2 minutes: nothing answered on `127.0.0.1:8501`. The ~2-minute duration (30 polls x ~4 s) means the port was simply never opened — the exe either crashed at startup or hung before binding.

**Why that was impossible to diagnose.** `orange_cdss.spec` builds a *windowed* exe (`console=False`). In a windowed PyInstaller exe `sys.stdout` / `sys.stderr` are `None`, so every traceback and every Streamlit log line was discarded. The smoke test's "see build log above" pointed at a log that did not exist.

**Root cause: not confirmed.** This was fixed from a Linux sandbox again; nobody has seen the exe's own error yet. What was done instead is (a) remove every cause that is known to produce exactly this symptom, and (b) make the *next* failure — if there is one — explain itself. Candidates, most likely first:

1. **Streamlit's web frontend / package metadata not in the bundle.** Without `streamlit/static/` the server answers 404 (the smoke test needs HTTP 200); without the `streamlit-*.dist-info` folder `importlib.metadata.version("streamlit")` raises at startup. Spec now uses `collect_all("streamlit")` + `copy_metadata("streamlit")`.
2. **Streamlit thinking it is in development mode.** It decides that by looking for `site-packages` in its own file path, which a PyInstaller bundle does not have. In that mode a custom `server.port` is rejected and the frontend is expected from a dev server on :3000. The launcher already set the env var; it now also passes `--global.developmentMode false` and `--server.fileWatcherType none` as flags.
3. **pandas excluded in the spec.** Unused by this repo, but a hard dependency of Streamlit itself. Removed from `excludes`.
4. **No stdout/stderr in a windowed exe** — can crash code that writes to them, and hides every error. Streams are now redirected to a log file (see below).
5. **Too little patience.** A first launch of a ~300-500 MB bundle on a CI runner is slow (antivirus scans every file once). 60 s was tight; the smoke test now waits up to 4 minutes but fails immediately if the process dies.

**A separate bug found on the way (would have broken OCR even with the server up).** The launcher exported a `TESSERACT_CMD` variable and its comments said pytesseract reads it. It does not — pytesseract finds `tesseract` through `PATH` (or `pytesseract.pytesseract.tesseract_cmd`), and the app never sets either. The bundled Tesseract folder is now put on `PATH` and `tesseract_cmd` is set explicitly. `TESSDATA_PREFIX` already pointed at the `tessdata` folder, which is correct for Tesseract 5.x.

**New in `launcher.py`**
- Frozen runs log stdout/stderr (plus `faulthandler`, for native DLL crashes) to `%LOCALAPPDATA%\Orange-CDSS\launcher.log`, or to the path in `ORANGE_CDSS_LOG`. **If the exe ever "does nothing" on a lab PC, that file is the first thing to look at.**
- Any startup exception is logged with a full traceback and, on a real desktop, shown in a message box.
- `Orange-CDSS.exe --selftest` — runs *inside* the frozen exe: Streamlit metadata + frontend present + not in dev mode; imports of numpy / cv2 / PIL / pytesseract / arabic_reshaper / bidi / weasyprint; every bundled application module imports; Tesseract runs and has `eng` (missing `ara` is a warning); a real OCR round-trip on a synthetic image (warning only); a PDF with Arabic text is rendered through the bundled GTK3. Exit code 0/1.
- `ORANGE_CDSS_PORT`, `ORANGE_CDSS_NO_BROWSER`, `multiprocessing.freeze_support()`, and a 120 s (was 30 s) wait before opening the browser.

**New in `orange_cdss.spec`:** `collect_all` for streamlit, weasyprint, pyphen, tinycss2, cssselect2, tinyhtml5/html5lib, pydyf, fontTools, arabic_reshaper, bidi, cv2 and pytesseract (a package that is not installed is skipped with a note, not an error); app modules also passed as hidden imports so PyInstaller traces *their* imports (stdlib modules such as `difflib` that only the app uses); pandas no longer excluded.

**New in `build-exe.yml`** (after "Build with PyInstaller"):
1. **Verify bundle contents** — fails with the exact missing path (`streamlit\static\index.html`, `tesseract\tesseract.exe`, `gtk3-runtime\bin` with >= 20 DLLs, the Streamlit dist-info, ...).
2. **Frozen self-test** — runs `--selftest` and prints its log.
3. **Smoke test** — private port 8765, 4-minute deadline, stops early if the exe exits, prints the exe's log on success *and* failure.
4. **Upload exe logs** (`if: always()`) — the two log files are kept as the `Orange-CDSS-exe-logs` artifact even when a step fails.

**How to read the next run.** Open the failing step and read the block between `===== exe ... log =====` and `===== end of log =====`. If the log says "the exe wrote no log file at all", the process died before Python started — look for a missing Visual C++ runtime or a blocked DLL, not at the app. If "Verify bundle contents" fails, the message names the missing file and the fix belongs in `orange_cdss.spec`. If the self-test fails on a single line (for example `PDF generation inside the exe`), that line is the whole task.

**Still unverified (unchanged):** everything in the manual checklist below, in particular Arabic text shaping in the PDF and fonts. The bundled `fonts/` folder is staged, but nothing here proves WeasyPrint/Pango on Windows actually *finds* Amiri/Noto from it — check an Arabic PDF by eye on the first working build.

## The one thing most likely to need a second pass: WeasyPrint + GTK3

PDF generation (`weasyprint`) needs the GTK3 runtime (Pango, Cairo, GDK-Pixbuf, HarfBuzz) — not a Windows-native dependency. This has historically been the hardest part of shipping WeasyPrint on Windows, full stop, independent of this specific app. The workflow stages it via a silent install of a community-maintained GTK3-for-Windows installer and copies the DLLs out; if that installer's URL or internal layout has changed since this was written, that step (and only that step) will fail or silently produce an incomplete `gtk3-runtime/bin`.

**How you'll know:** the build itself will likely still succeed (PyInstaller doesn't verify DLLs work, just that files exist), but PDF report generation inside the exe will fail or hang. The smoke test in the workflow only proves the app *starts* — it does not generate a PDF.

**If this happens, in order of effort:**
1. Check the GTK3 staging step's log in the Actions run — did it download/install successfully? Try the URL manually.
2. Install GTK3 Runtime for Windows on any Windows machine, copy `C:\Program Files\GTK3-Runtime Win64\bin\*.dll` into this repo's `gtk3-runtime/bin/` folder directly, commit it (yes, committing DLLs is unusual, but it removes this entire failure class going forward — weigh that against repo size), and drop the download step from the workflow.
3. Last resort: swap the PDF backend from WeasyPrint to something with a cleaner Windows story (e.g. `fpdf2`, which `orange_qc_control` already uses successfully for PDF generation with Arabic/Unicode support) for the EXE build specifically. This is a real code change, not a packaging tweak — flagging it as the fallback, not proposing it now.

## Manual verification checklist (do this once, on the actual built exe)

The automated smoke test only proves the server starts. These need a human, once, on a real Windows machine:

- [ ] Double-click `Orange-CDSS.exe` from a fresh folder (not the build machine) — does the browser open automatically?
- [ ] Upload a real antibiogram image — does OCR detect drugs? (Tests Tesseract bundling.)
- [ ] Generate a PDF report — does it render, and is Arabic text shaped correctly (connected letters, not disconnected glyphs)? (Tests GTK3 + font bundling together — the single riskiest combination in this whole build.)
- [ ] Disconnect from the internet entirely, repeat both steps above — confirms nothing silently depends on network access.
- [ ] Check the page header shows the 🟢 Offline badge.
- [ ] Close the window / end the process — does it shut down cleanly, or does a Python process linger?

## What deliberately was not attempted

- **Code signing.** An unsigned `.exe` will trigger a Windows SmartScreen warning on first run. Fine for internal lab use; worth revisiting before distributing to other labs (see the earlier discussion about commercializing this).
- **An installer (Setup.exe / MSI).** The current output is a folder (`Orange-CDSS/` with the exe and its `_internal/` data inside) — copy the whole folder, don't just take the `.exe`. A proper installer (Start Menu entry, uninstaller) is a reasonable next step once the folder-based build is confirmed working, not before.
- **An app icon.** `orange_cdss.spec` has `icon=None` — drop an `.ico` file in and update that one line whenever there's a logo to use.
