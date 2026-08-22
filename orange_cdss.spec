# orange_cdss.spec — PyInstaller build spec, Orange Lab Microbiology CDSS
#
# Built and run on windows-latest by .github/workflows/build-exe.yml, which
# is also where Tesseract/GTK3/fonts get staged into the local folders this
# spec expects (tesseract/, gtk3-runtime/, fonts/ — see that workflow for
# exactly where each comes from). This file assumes those folders already
# exist relative to it when PyInstaller runs; it does not download anything
# itself.
#
# Run locally (Windows, after staging the three folders above by hand):
#   pip install pyinstaller
#   pyinstaller orange_cdss.spec --clean
#
# WHY A .spec FILE AND NOT A ONE-LINE `pyinstaller launcher.py`:
# Streamlit does not get frozen the normal PyInstaller way. streamlit_app.py
# and every sibling module it imports (ast_qa_engine.py, clinical_data.py,
# organism_profile.py, ...) must exist as REAL, LOOSE .py FILES on disk next
# to each other inside the bundle — Streamlit's CLI opens streamlit_app.py by
# filesystem path and execs it, and that exec then does normal `import
# ast_qa_engine`-style imports that need real files to find, not PyInstaller's
# compiled-into-the-exe module cache. So every application module is listed
# under `datas` below (bundled as loose files) in addition to being picked up
# by PyInstaller's own import analysis for their third-party dependencies.

import os

block_cipher = None
ROOT = os.path.dirname(os.path.abspath(SPEC))

# ── Application source: every non-test .py module, as LOOSE files ──────────
# (see the note above for why these are `datas`, not left to Analysis alone)
APP_MODULES = [
    "streamlit_app.py",
    "launcher.py",
    "abx_guidelines.py",
    "ast_consistency.py",
    "ast_panel_completeness.py",
    "ast_qa_engine.py",
    "ast_reportability.py",
    "auth_service.py",
    "clinical_data.py",
    "clinical_matrix.py",
    "clinical_utils.py",
    "guideline_registry.py",
    "ocr_parsing.py",
    "organism_profile.py",
    "pathogenicity.py",
    "report_service.py",
    "safety_gate.py",
    "scenario_matrix.py",
    "specimen_organism_map.py",
]

datas = [(m, ".") for m in APP_MODULES if os.path.exists(os.path.join(ROOT, m))]
datas.append(("commercial_names.txt", "."))

# Tesseract (binary + English/Arabic tessdata), GTK3 runtime (WeasyPrint's
# PDF rendering dependency — see build-exe.yml for why this is the highest-
# risk single piece of this bundle), and fonts. Staged by the CI workflow
# before this spec runs; included here only if actually present, so a local
# test build without them still produces a runnable (if OCR/PDF-limited) exe
# rather than failing the whole build over a missing font folder.
for folder, dest in (("tesseract", "tesseract"), ("gtk3-runtime", "gtk3-runtime"),
                     ("fonts", "fonts")):
    src = os.path.join(ROOT, folder)
    if os.path.isdir(src):
        for dirpath, _, filenames in os.walk(src):
            rel = os.path.relpath(dirpath, ROOT)
            for fn in filenames:
                datas.append((os.path.join(dirpath, fn), rel))

hiddenimports = [
    # Modules imported inside try/except ImportError blocks in
    # streamlit_app.py -- PyInstaller's static analysis usually catches
    # these anyway, but listed explicitly so a build never silently drops
    # one of the AST QC modules over an analysis edge case.
    "ast_reportability", "ast_consistency", "ast_panel_completeness",
    "ast_qa_engine", "guideline_registry",
    # Streamlit's own runtime pulls in a lot dynamically; the ones below are
    # the ones known to occasionally get missed by PyInstaller's hooks.
    "streamlit.web.cli",
    "streamlit.runtime.scriptrunner.magic_funcs",
    "pytesseract", "cv2", "PIL", "weasyprint",
    "arabic_reshaper", "bidi", "bidi.algorithm",
]

a = Analysis(
    ["launcher.py"],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Explicitly NOT bundled -- see requirements.txt's own note: these
        # were declared but never imported anywhere in the app, and only
        # widen the exe for nothing. Excluding them here (rather than just
        # not installing them) protects against PyInstaller pulling one in
        # transitively through some other package's optional dependency.
        "fpdf", "pandas", "sklearn", "reportlab",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Orange-CDSS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX + antivirus false-positives on lab workstations
    console=False,       # windowed -- the browser tab IS the UI
    icon=None,            # add an .ico path here once Hussein has one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Orange-CDSS",
)
