# -*- coding: utf-8 -*-
# © Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
r"""modules/ — ABANDONED PARALLEL BUILD. Do not import from application code.

streamlit_app.py imports nothing from this package, and neither does any test.
`compileall` in CI proves these 1,909 lines parse. Nothing proves they are
correct, and they are not.

WHAT HAS DRIFTED, in the direction that matters:

  * modules/mdr.py carries its own predict_esbl() and its own ESBL_PRODUCERS
    list of FIVE organisms. The live list in streamlit_app.py holds eighteen and
    covers Citrobacter, Serratia, Morganella and Providencia. The copy here also
    skips intrinsic-resistance stripping before reading the phenotype, so an
    agent the organism was never susceptible to counts as evidence of a
    mechanism.
  * Every clinical table here predates the 2026-08-01 audit: no taxonomic
    inheritance (Vancomycin passes on E. coli), no aztreonam in the ESBL
    lockdown, no AmpC derepression rule, no beta-lactamase-inhibitor handling
    for MRSA.

The hazard is quiet: import `modules.mdr.predict_esbl` believing it is the
audited function and you get a weaker answer with nothing to indicate anything
is wrong.

This package is NOT made to raise on import, because qc.py — itself a
documented legacy redirect — still re-exports modules.qc. Guard 12 in
.github/workflows/cdss-tests.yml enforces the real invariant instead: no
application module and no test may import from here.

TO REMOVE PROPERLY:

    grep -rn "^from modules\|^import modules" --include=*.py .   # only qc.py
    git rm qc.py                 # the redirect that keeps this alive
    git rm -r modules/ ui/       # 2,858 lines

`ui/` is in the same position: 949 lines, zero importers, no redirect keeping
it alive. `data/` is different — it is still reachable through the
antibiotics.py redirect and must stay until that goes.
"""
