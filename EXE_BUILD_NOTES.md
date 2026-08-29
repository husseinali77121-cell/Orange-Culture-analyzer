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
