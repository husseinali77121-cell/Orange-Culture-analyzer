# -*- coding: utf-8 -*-
# © Dr. Hussein Ali — Orange Lab, 6 October City, Egypt
# Microbiology CDSS — All Rights Reserved
r"""qc.py — legacy import path. Contains no logic of its own.

This file used to be a near-copy of modules/qc.py, and the copies had diverged in
the worst possible direction: the guard that stops run_ast_qc() raising NameError
on AST_QC_RULES existed HERE, in the copy nothing imported, and had never been
carried across to modules/qc.py, which ui/dashboard.py calls on every analysis.
The dead file was correct and the live one crashed on every call.

Kept as a redirect for the same reason as antibiotics.py — a zip cannot express a
deletion and this repository is deployed by extracting archives, so a file that
has to be removed by hand tends to survive. There is nothing here to diverge now.

AST_QC_RULES is deliberately NOT re-exported: modules/qc.py no longer keeps a
rule list of its own, it delegates to ast_qa_engine.run_ast_qa_engine (13 check
families). Anything that imported the old name wanted the rules, and the rules
now live in ast_qa_engine.

    grep -rn "^import qc$" --include=*.py .          # expect no hits
    grep -rn "^from qc import" --include=*.py .      # expect no hits
    git rm qc.py
"""
from __future__ import annotations

from modules.qc import (  # noqa: F401
    QA_ENGINE_AVAILABLE,
    get_startup_validation_issues,
    run_ast_qc,
)

__all__ = ["run_ast_qc", "get_startup_validation_issues", "QA_ENGINE_AVAILABLE"]
